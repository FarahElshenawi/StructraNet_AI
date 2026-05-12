"""
Structranet AI — AI Agent  (V3.1)

Translates a natural language request into a validated GNS3Project.

Two-step pipeline (replaces the single giant LLM call):
  Step 1: LLM → TopologyRequest (nodes + logical connections, NO port numbers)
  Step 2: port_assigner.py → Link objects with correct adapter/port numbers
  Step 3: hw_config.inject_hardware_config → slot/adapter expansion
  Step 4: Pydantic validation (hard errors, no silent fixes)
  Step 5: If errors → feed them back to LLM and retry (max 3 attempts)

The LLM prompt is now ~80 lines instead of 250.  The LLM only needs to decide
WHAT connects to WHAT — not how to compute adapter/port numbers.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from hw_config import inject_hardware_config
from llm_utils import _call_with_retry, _extract_json, _get_client
from port_assigner import build_topology_from_request
from schema import (
    GNS3Project, TopologyRequest, validate_topology_request, validate_topology,
)

load_dotenv()
logger = logging.getLogger("structranet.ai_agent")

DEFAULT_MODEL = os.getenv("AI_MODEL", "openrouter/owl-alpha")
MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "8192"))
MAX_RETRIES = 3


# ═══════════════════════════════════════════════════════════════════════════════
#  Step 1 prompt: nodes + connections only
# ═══════════════════════════════════════════════════════════════════════════════

# Hardware port limits — shown to LLM only to prevent topologically impossible
# designs (e.g. 10 links to a c7200).  Port NUMBERS are not the LLM's concern.
_DYNAMIPS_MAX_LINKS = {
    "c7200": 3, "c3745": 6, "c3725": 6, "c3660": 5,
    "c3640": 4, "c3620": 4, "c2691": 6, "c2600": 2, "c1700": 2,
}
_SINGLE_LINK_TYPES = {"vpcs", "traceng", "nat"}


def _build_step1_prompt(devices: list[dict]) -> str:
    inventory = [
        {"name": d["name"], "type": d["gns3_type"],
         "category": d.get("category", ""), "max_links": d.get("port_count")}
        for d in devices
    ]

    # Build per-device link-limit lines
    limit_lines = []
    for d in devices:
        gtype = d["gns3_type"]
        name = d["name"]
        pc = d.get("port_count")
        if gtype in _SINGLE_LINK_TYPES:
            limit_lines.append(f"  - {name} ({gtype}): MAX 1 link. Insert a switch if more needed.")
        elif gtype == "dynamips":
            platform = name.lower()
            max_l = _DYNAMIPS_MAX_LINKS.get(platform, 3)
            limit_lines.append(
                f"  - {name} (dynamips): MAX {max_l} total links (PCI bus limit). "
                f"Use Core-SW + Router-on-a-Stick if you need more subnets."
            )
        elif pc is not None:
            limit_lines.append(f"  - {name} ({gtype}): MAX {pc} links.")

    limit_text = "\n".join(limit_lines) or "  (counts unavailable — be conservative)"
    inv_json = json.dumps(inventory, indent=2)

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

OUTPUT: A JSON object matching this schema exactly:
{{
  "name": "<project name>",
  "nodes": [
    {{"node_id": "R1", "name": "R1-Main", "node_type": "dynamips",
      "template_name": "<exact inventory name>", "compute_id": "local"}}
  ],
  "connections": [
    {{"from_node": "R1", "to_node": "SW1", "link_type": "ethernet"}}
  ]
}}

Respond with ONLY the JSON object. No markdown fences. No explanation."""


def _call_step1(
    user_request: str,
    devices: list[dict],
    previous_errors: list[str] = None,
) -> Optional[TopologyRequest]:
    """Call the LLM to generate nodes + connections."""
    client = _get_client()
    prompt = _build_step1_prompt(devices)

    messages = [{"role": "system", "content": prompt}]

    if previous_errors:
        error_text = "\n".join(f"  - {e}" for e in previous_errors)
        messages.append({
            "role": "user",
            "content": (
                f"{user_request}\n\n"
                f"PREVIOUS ATTEMPT FAILED WITH THESE ERRORS — fix them:\n{error_text}"
            ),
        })
    else:
        messages.append({"role": "user", "content": user_request})

    schema_json = json.dumps(TopologyRequest.model_json_schema(), indent=2)
    messages[0]["content"] += f"\n\nJSON Schema:\n{schema_json}"

    raw_text = ""
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
            return None

        raw_text = response.choices[0].message.content or ""
        clean = _extract_json(raw_text)
        data = json.loads(clean)
        result = TopologyRequest.model_validate(data)
        logger.info("Step 1 succeeded: %d nodes, %d connections",
                    len(result.nodes), len(result.connections))
        return result

    except Exception as e:
        logger.warning("Step 1 failed: %s", e)
        if raw_text:
            logger.debug("Raw output: %s", raw_text[:500])
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Main generation pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def generate_network_topology(
    user_request: str, devices: list[dict]
) -> Optional[GNS3Project]:
    """
    Generate a GNS3Project from a natural language request.

    Pipeline:
      1. LLM generates TopologyRequest (nodes + connections, NO port numbers)
      2. port_assigner.py assigns adapter/port numbers deterministically
      3. Pydantic validation (hard errors)
      4. If errors → feed back to LLM and retry (max MAX_RETRIES times)
    """
    previous_errors: list[str] = []

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("Generation attempt %d/%d", attempt, MAX_RETRIES)

        # Step 1: LLM generates nodes + logical connections
        topo_request = _call_step1(user_request, devices, previous_errors or None)
        if topo_request is None:
            logger.error("LLM call failed on attempt %d", attempt)
            continue

        # Step 2: Validate the topology request
        req_errors = validate_topology_request(topo_request.model_dump())
        if req_errors:
            logger.warning("TopologyRequest validation failed: %s", req_errors)
            previous_errors = req_errors
            continue

        # Step 3: Deterministic port assignment
        try:
            project_dict = build_topology_from_request(topo_request)
        except ValueError as e:
            logger.warning("Port assignment failed: %s", e)
            previous_errors = [str(e)]
            continue

        # Step 4: Validate the full topology
        topo_errors = validate_topology(project_dict)
        if topo_errors:
            logger.warning("Topology validation failed: %s", topo_errors)
            # Feed errors back to LLM — but note: port errors are code bugs,
            # not LLM errors.  Only feed back structural errors (node/link counts,
            # connectivity, etc.)
            structural_errors = [
                e for e in topo_errors
                if "port_assigner.py" not in e
            ]
            previous_errors = structural_errors or topo_errors
            continue

        # All good
        logger.info("Generation succeeded on attempt %d", attempt)
        try:
            return GNS3Project.model_validate(project_dict)
        except Exception as e:
            logger.error("Final model_validate failed: %s", e)
            previous_errors = [str(e)]
            continue

    logger.error("All %d generation attempts failed", MAX_RETRIES)
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Post-generation: hardware injection + save
# ═══════════════════════════════════════════════════════════════════════════════

def process_and_save_topology(
    raw_topology: GNS3Project, output_file: str
) -> Optional[GNS3Project]:
    """Run hardware injection and save to disk.

    Steps:
      1. Pydantic model → dict
      2. inject_hardware_config() — expands slots/adapters/ports_mapping
      3. Re-validate through Pydantic
      4. Save JSON to output_file
      5. Return enriched GNS3Project
    """
    raw_dict = raw_topology.model_dump()
    enriched_dict = inject_hardware_config(raw_dict)

    try:
        result = GNS3Project.model_validate(enriched_dict)
    except Exception as e:
        logger.error("Re-validation after hardware injection failed: %s", e)
        return None

    try:
        out = Path(output_file)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        logger.info("Topology saved to %s", out)
    except OSError as e:
        logger.error("Failed to save topology: %s", e)
        return None

    return result
