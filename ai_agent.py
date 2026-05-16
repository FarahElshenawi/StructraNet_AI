"""
Structranet AI — AI Agent  (V4.0)

Translates a natural language request into a validated GNS3Project.

V4.0 additions over V3.3:
  1. Chain-of-Thought (CoT) envelope
       The LLM now returns a two-key JSON object:
         { "thinking": "<step-by-step reasoning>", "topology": { <TopologyRequest> } }
       _call_step1() unpacks the envelope; validation is applied only to
       the inner "topology" key, so the existing Pydantic gates are untouched.

  2. Multi-turn chat history
       generate_network_topology() accepts an optional `chat_history` list
       (standard OpenAI message dicts).  On every call the history is
       prepended to the messages array so the LLM refines the existing
       design instead of starting from scratch.  The function returns
       (result, updated_history, thinking_text) so callers can accumulate
       turns across the interactive Edit loop.

  3. Rich node context
       process_and_save_topology() calls _enrich_nodes() after hardware
       injection.  This post-processor adds underscore-prefixed metadata
       fields to each node's properties dict:
         _interfaces        – computed interface name list (from context_builder)
         _hardware_summary  – human-readable slot/adapter summary string
         _security_role     – forwarded from topology-phase LLM security_role
         _zone              – forwarded from topology-phase LLM zone field
         _image_required    – True for appliance types, False for built-ins
       These keys are intentionally outside the Phase 2 safe-merge whitelist
       (SOFTWARE_CONFIG_KEYS) so they can never be accidentally overwritten.

  4. Image Verification Manifest
       generate_image_manifest() runs post-Phase-1.  It cross-references
       every node's template_name against the preflight profile's
       template_image_map and writes a human-readable image_manifest.txt
       to the output directory.

All existing behaviour (port assigner, hardware injection, VLAN patching,
Pydantic validation, retry loop, security profiles) is preserved.
"""

from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from dotenv import load_dotenv

from constants.ai import DYNAMIPS_MAX_LINKS, MAX_RETRIES, SINGLE_LINK_TYPES
from constants.gns3 import VLAN_PATCHED_KEY
from hw_config import inject_hardware_config
from llm_utils import _call_with_retry, _extract_json, _get_client
from port_assigner import build_topology_from_request
from schema import (
    GNS3Project,
    TopologyRequest,
    validate_topology,
    validate_topology_request,
)
from security_prompts import get_topology_security_prompt
from topology_finalizer import apply_switch_port_patches

load_dotenv()
logger = logging.getLogger("structranet.ai_agent")

DEFAULT_MODEL = os.getenv("AI_MODEL", "openrouter/owl-alpha")
MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "8192"))

# Node types that never need a disk image
_BUILTIN_NODE_TYPES: frozenset = frozenset(
    ["vpcs", "ethernet_switch", "ethernet_hub", "cloud", "nat",
     "traceng", "frame_relay_switch", "atm_switch"]
)
_APPLIANCE_NODE_TYPES: frozenset = frozenset(
    ["dynamips", "iou", "qemu", "docker", "virtualbox", "vmware"]
)


# ═══════════════════════════════════════════════════════════════════════════════
#  Session State
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SessionState:
    """Carries all mutable pipeline state across interactive Edit loop turns.

    Attributes
    ----------
    chat_history    OpenAI message list (accumulated across Edit iterations).
    topology_dict   The most recent hardware-injected topology dict.
    thinking_text   The most recent CoT reasoning text from the LLM.
    iteration       How many Phase-1 generation attempts have run.
    last_request    The original user request string (never mutated by edits).
    """
    chat_history: List[Dict[str, str]] = field(default_factory=list)
    topology_dict: Optional[Dict[str, Any]] = None
    thinking_text: str = ""
    iteration: int = 0
    last_request: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
#  Step 1 prompt builder  (CoT envelope)
# ═══════════════════════════════════════════════════════════════════════════════

def _build_step1_prompt(
    devices: List[Dict[str, Any]],
    security_profile: str = "none",
) -> str:
    inventory = [
        {
            "name": d["name"],
            "type": d["gns3_type"],
            "category": d.get("category", ""),
            "max_links": d.get("port_count"),
        }
        for d in devices
    ]

    limit_lines: List[str] = []
    for d in devices:
        gtype = d["gns3_type"]
        name = d["name"]
        pc = d.get("port_count")
        if gtype in SINGLE_LINK_TYPES:
            limit_lines.append(
                f"  - {name} ({gtype}): MAX 1 link. Insert a switch if more needed."
            )
        elif gtype == "dynamips":
            platform = name.lower()
            max_l = DYNAMIPS_MAX_LINKS.get(platform, 3)
            limit_lines.append(
                f"  - {name} (dynamips): MAX {max_l} total links (PCI bus limit). "
                f"Use Core-SW + Router-on-a-Stick if you need more subnets."
            )
        elif pc is not None:
            limit_lines.append(f"  - {name} ({gtype}): MAX {pc} links.")

    limit_text = "\n".join(limit_lines) or "  (counts unavailable — be conservative)"
    inv_json = json.dumps(inventory, indent=2)
    security_block = get_topology_security_prompt(security_profile)

    schema_json = json.dumps(TopologyRequest.model_json_schema(), indent=2)

    return f"""You are the Core Architect Agent for Structranet AI.
Translate the user's natural language request into a network topology.

IMPORTANT: You produce ONLY the logical design — which devices connect to which.
DO NOT produce adapter numbers, port numbers, or any port assignments.
Those are computed automatically by the system after you respond.

AVAILABLE HARDWARE (use ONLY these):
{inv_json}

LINK LIMITS (do NOT exceed):
{limit_text}

RULES:
1. ZERO HALLUCINATION: Only use device names from the inventory above.
2. node_type must be a GNS3 literal: dynamips, qemu, vpcs, ethernet_switch,
   ethernet_hub, docker, iou, cloud, traceng, frame_relay_switch, atm_switch,
   virtualbox, vmware, nat.
3. template_name must be the exact inventory name (e.g. "c7200", "Switch").
4. name is a human-readable label (e.g. "R1-Edge", "Core-SW1", "PC1").
5. node_id is a short unique key (e.g. "R1", "SW1", "PC1").
6. DO NOT assign port numbers — just list connections as "from_node → to_node".
7. No two connections may link the same pair of nodes (no parallel links).
8. Every node must be reachable from every other node (fully connected graph).
9. VPCS/TraceNG/NAT nodes may have AT MOST 1 connection. Use a switch if more needed.
10. If a router needs more subnet switches than its link limit allows, use the
    Core-SW + Router-on-a-Stick pattern (router → 1 core switch → N access switches).
11. link_type is "ethernet" (default) or "serial" (for WAN router-to-router links).
12. If a device isn't available, substitute with the closest available match.
{security_block}

CHAIN-OF-THOUGHT REQUIREMENT:
Before writing the topology JSON, you MUST reason step-by-step about:
  a) Which device types best fit the request and why.
  b) How many of each device is needed.
  c) How the devices connect (topology pattern: star, ring, hierarchical, etc.).
  d) Any VLAN / security / redundancy considerations.
  e) Any link-limit constraints you are working around.

OUTPUT FORMAT — return a SINGLE JSON object with exactly two top-level keys:

{{
  "thinking": "<your step-by-step architectural reasoning as a plain string>",
  "topology": {{
    "name": "<project name>",
    "nodes": [
      {{"node_id": "R1", "name": "R1-Main", "node_type": "dynamips",
        "template_name": "<exact inventory name>", "compute_id": "local"}}
    ],
    "connections": [
      {{"from_node": "R1", "to_node": "SW1", "link_type": "ethernet"}}
    ]
  }}
}}

The "topology" value must conform exactly to this JSON Schema:
{schema_json}

Respond with ONLY the JSON object. No markdown fences. No explanation outside the JSON."""


# ═══════════════════════════════════════════════════════════════════════════════
#  Step 1 LLM call  (unpacks CoT envelope)
# ═══════════════════════════════════════════════════════════════════════════════

def _call_step1(
    user_request: str,
    devices: List[Dict[str, Any]],
    security_profile: str = "none",
    chat_history: Optional[List[Dict[str, str]]] = None,
    previous_errors: Optional[List[str]] = None,
) -> Tuple[Optional[TopologyRequest], str, List[Dict[str, str]]]:
    """Call the LLM for Phase 1 topology generation.

    Returns
    -------
    (TopologyRequest | None, thinking_text, updated_history)
    """
    client = _get_client()
    system_content = _build_step1_prompt(devices, security_profile=security_profile)

    # Build message list: system → history → new user message
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_content}]

    if chat_history:
        messages.extend(chat_history)

    if previous_errors:
        error_text = "\n".join(f"  - {e}" for e in previous_errors)
        user_content = (
            f"{user_request}\n\n"
            f"PREVIOUS ATTEMPT FAILED WITH THESE ERRORS — fix them:\n{error_text}"
        )
    else:
        user_content = user_request

    messages.append({"role": "user", "content": user_content})

    raw_text = ""
    thinking_text = ""
    updated_history = list(chat_history or [])

    try:
        def _call():
            return client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=messages,
                max_tokens=MAX_TOKENS,
                response_format={"type": "json_object"},
            )

        response = _call_with_retry(_call)
        if not response or not response.choices:
            logger.error("LLM returned empty response")
            return None, "", updated_history

        raw_text = response.choices[0].message.content or ""
        clean = _extract_json(raw_text)
        outer = json.loads(clean)

        # ── Unpack CoT envelope ──────────────────────────────────────────────
        thinking_text = outer.get("thinking", "")
        topology_data = outer.get("topology")

        if topology_data is None:
            # Graceful fallback: maybe the LLM returned the topology at the top level
            # (skipped the envelope).  Attempt to validate directly.
            logger.warning(
                "CoT envelope missing 'topology' key — attempting direct parse"
            )
            topology_data = outer

        result = TopologyRequest.model_validate(topology_data)

        # Accumulate chat history for multi-turn continuity.
        # Append the user turn ONLY if the last entry isn't already a user
        # message (callers like _checkpoint_loop pre-append edit feedback).
        if not updated_history or updated_history[-1].get("role") != "user":
            updated_history.append({"role": "user", "content": user_content})
        updated_history.append({"role": "assistant", "content": raw_text})

        logger.info(
            "Step 1 succeeded: %d nodes, %d connections",
            len(result.nodes),
            len(result.connections),
        )
        return result, thinking_text, updated_history

    except Exception as e:
        logger.warning("Step 1 failed: %s", e)
        if raw_text:
            logger.debug("Raw output (first 600 chars): %s", raw_text[:600])
        return None, thinking_text, updated_history


# ═══════════════════════════════════════════════════════════════════════════════
#  Node enrichment  (Requirement 4 — Rich Node Context)
# ═══════════════════════════════════════════════════════════════════════════════

def _build_hardware_summary(node: Dict[str, Any]) -> str:
    """Return a compact human-readable string describing installed hardware."""
    ntype = node.get("node_type", "")
    props = node.get("properties", {})
    parts: List[str] = []

    if ntype == "dynamips":
        platform = props.get("platform", node.get("template_name", "unknown"))
        ram = props.get("ram", "?")
        parts.append(f"platform={platform} ram={ram}MB")
        for slot_num in range(7):
            key = f"slot{slot_num}"
            mod = props.get(key)
            if mod:
                parts.append(f"{key}={mod}")
    elif ntype == "iou":
        eth = props.get("ethernet_adapters", "?")
        ser = props.get("serial_adapters", "?")
        parts.append(f"ethernet_adapters={eth} serial_adapters={ser}")
    elif ntype in ("qemu", "docker", "virtualbox", "vmware"):
        adapters = props.get("adapters", "?")
        parts.append(f"adapters={adapters}")
        ram = props.get("ram")
        if ram:
            parts.append(f"ram={ram}MB")
    elif ntype in ("ethernet_switch", "ethernet_hub"):
        pm = props.get("ports_mapping", [])
        parts.append(f"ports={len(pm)}")
        trunk_count = sum(1 for p in pm if p.get("type") == "dot1q")
        if trunk_count:
            parts.append(f"trunk_ports={trunk_count}")
    else:
        parts.append(ntype)

    return " | ".join(parts) if parts else ntype


def _enrich_nodes(topology_dict: Dict[str, Any]) -> None:
    """Add underscore-prefixed metadata to each node's properties dict.

    Called AFTER hw_config.inject_hardware_config() so slot/adapter data
    is already present.  The enrichment keys are intentionally outside
    SOFTWARE_CONFIG_KEYS so Phase 2 safe-merge never touches them.
    """
    # Import here to avoid circular imports at module load time
    from context_builder import _resolve_all_interfaces  # noqa: PLC0415

    topo = topology_dict.get("topology", {})
    nodes = topo.get("nodes", [])
    links = topo.get("links", [])

    for node in nodes:
        ntype = node.get("node_type", "")
        props = node.setdefault("properties", {})

        # _interfaces: list of canonical interface names
        try:
            iface_list = _resolve_all_interfaces(node)
        except Exception:
            iface_list = []
        props["_interfaces"] = iface_list

        # _hardware_summary: compact slot/adapter string
        props["_hardware_summary"] = _build_hardware_summary(node)

        # _image_required: True for appliance types
        props["_image_required"] = ntype in _APPLIANCE_NODE_TYPES

        # _security_role / _zone: forwarded from topology-phase LLM extra fields
        # (The LLM may include these as top-level node fields for enterprise profiles)
        if "security_role" in node and "_security_role" not in props:
            props["_security_role"] = node["security_role"]
        if "zone" in node and "_zone" not in props:
            props["_zone"] = node["zone"]
        if "vlan_id" in node and "_vlan_id" not in props:
            props["_vlan_id"] = node["vlan_id"]

        # _link_count: how many links are connected to this node
        nid = node.get("node_id", "")
        link_count = sum(
            1
            for link in links
            for ep in link.get("nodes", [])
            if ep.get("node_id") == nid
        )
        props["_link_count"] = link_count

    logger.info("Node enrichment complete (%d node(s))", len(nodes))


# ═══════════════════════════════════════════════════════════════════════════════
#  Image Verification Manifest  (Requirement 1)
# ═══════════════════════════════════════════════════════════════════════════════

def generate_image_manifest(
    topology_dict: Dict[str, Any],
    template_image_map: Dict[str, str],
    output_path: str,
) -> str:
    """Write image_manifest.txt cross-referencing each node against the image map.

    Parameters
    ----------
    topology_dict       Hardware-injected topology dict.
    template_image_map  Mapping from template_name to IOS image filename.
    output_path         Destination file path for image_manifest.txt.

    Returns
    -------
    Absolute path of the written manifest file.
    """
    topo = topology_dict.get("topology", {})
    nodes = topo.get("nodes", [])

    lines: List[str] = [
        "=" * 70,
        "  STRUCTRANET AI — IMAGE VERIFICATION MANIFEST",
        "=" * 70,
        "",
        f"  Nodes: {len(nodes)}",
        f"  Images in map: {len(template_image_map)}",
        "",
        f"  {'Node ID':<12} {'Name':<20} {'Template':<25} Status / Image File",
        "  " + "-" * 66,
    ]

    missing: List[str] = []

    for node in nodes:
        nid = node.get("node_id", "?")
        name = node.get("name", "?")
        ntype = node.get("node_type", "")
        template = node.get("template_name", "")

        if ntype in _BUILTIN_NODE_TYPES:
            status = "✓  Built-in — no image required"
        elif ntype in _APPLIANCE_NODE_TYPES:
            if template in template_image_map:
                image_file = template_image_map[template]
                status = f"✓  {image_file}"
            else:
                status = "⚠  NOT IN IMAGE MAP — verify manually"
                missing.append(f"  {nid} / {template}")
        else:
            status = "–  Unknown type"

        lines.append(f"  {nid:<12} {name:<20} {template:<25} {status}")

    lines.append("")

    if missing:
        lines += [
            "  ⚠  MISSING IMAGE MAPPINGS (add to preflight profile or catalog):",
            *[f"    {m}" for m in missing],
            "",
        ]
    else:
        lines.append("  ✓  All appliance nodes have image mappings.")

    lines += [
        "",
        "  Action: verify each image file exists in your GNS3 images directory",
        "  before importing the .gns3project.",
        "=" * 70,
    ]

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    abs_path = str(out.resolve())
    logger.info("Image manifest written to %s", abs_path)
    return abs_path


# ═══════════════════════════════════════════════════════════════════════════════
#  Main generation pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def generate_network_topology(
    user_request: str,
    devices: List[Dict[str, Any]],
    disallowed_node_types: Optional[Set[str]] = None,
    security_profile: str = "none",
    chat_history: Optional[List[Dict[str, str]]] = None,
) -> Tuple[Optional[GNS3Project], str, List[Dict[str, str]]]:
    """Generate a validated GNS3Project from a natural language request.

    Returns
    -------
    (GNS3Project | None, thinking_text, updated_chat_history)

    The caller is responsible for accumulating chat_history across Edit
    loop iterations and passing the updated list on the next call.
    """
    previous_errors: List[str] = []
    disallowed = {t.lower() for t in (disallowed_node_types or set())}
    current_history = list(chat_history or [])
    latest_thinking = ""

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("Generation attempt %d/%d", attempt, MAX_RETRIES)

        topo_request, thinking_text, current_history = _call_step1(
            user_request,
            devices,
            security_profile=security_profile,
            chat_history=current_history,
            previous_errors=previous_errors or None,
        )
        if thinking_text:
            latest_thinking = thinking_text

        if topo_request is None:
            logger.error("LLM call failed on attempt %d", attempt)
            continue

        req_errors = validate_topology_request(topo_request.model_dump())
        if not req_errors and disallowed:
            disallowed_hits = [
                f"node '{n.node_id}' uses disallowed node_type '{n.node_type}'"
                for n in topo_request.nodes
                if str(n.node_type).lower() in disallowed
            ]
            if disallowed_hits:
                req_errors = [
                    "Environment compatibility violation: "
                    + "; ".join(disallowed_hits)
                ]

        if req_errors:
            logger.warning("TopologyRequest validation failed: %s", req_errors)
            previous_errors = req_errors
            continue

        try:
            project_dict = build_topology_from_request(topo_request)
        except ValueError as e:
            logger.warning("Port assignment failed: %s", e)
            previous_errors = [str(e)]
            continue

        topo_errors = validate_topology(project_dict)
        if topo_errors:
            logger.warning("Topology validation failed: %s", topo_errors)
            structural_errors = [
                e for e in topo_errors if "port_assigner.py" not in e
            ]
            previous_errors = structural_errors or topo_errors
            continue

        logger.info("Generation succeeded on attempt %d", attempt)
        try:
            return (
                GNS3Project.model_validate(project_dict),
                latest_thinking,
                current_history,
            )
        except Exception as e:
            logger.error("Final model_validate failed: %s", e)
            previous_errors = [str(e)]
            continue

    logger.error("All %d generation attempts failed", MAX_RETRIES)
    return None, latest_thinking, current_history


# ═══════════════════════════════════════════════════════════════════════════════
#  Post-generation: hardware injection + enrichment + VLAN patching + save
# ═══════════════════════════════════════════════════════════════════════════════

def process_and_save_topology(
    raw_topology: GNS3Project,
    output_file: str,
) -> Optional[GNS3Project]:
    """Run hardware injection, node enrichment, VLAN patching, and save to disk.

    Node enrichment (_enrich_nodes) runs after hardware injection so all slot
    and adapter data is already present when we compute _hardware_summary and
    _interfaces.  Enrichment metadata is stored under underscore-prefixed keys
    and is invisible to the Phase 2 safe-merge whitelist.
    """
    raw_dict = raw_topology.model_dump()

    # 1. Hardware slot/adapter/ports_mapping expansion
    enriched = inject_hardware_config(raw_dict)

    # 2. Rich node metadata (interfaces, hardware summary, security roles)
    _enrich_nodes(enriched)

    # 3. VLAN trunk/access port patching
    apply_switch_port_patches(enriched)
    enriched[VLAN_PATCHED_KEY] = True
    logger.info("Switch VLAN port patches applied in process_and_save_topology")

    # 4. Re-validate (Pydantic ignores unknown underscore fields by default)
    try:
        result = GNS3Project.model_validate(enriched)
    except Exception as e:
        logger.error("Re-validation after hardware injection failed: %s", e)
        return None

    # 5. Persist
    try:
        out = Path(output_file)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        logger.info("Topology saved to %s", out)
    except OSError as e:
        logger.error("Failed to save topology: %s", e)
        return None

    return result