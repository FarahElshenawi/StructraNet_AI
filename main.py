"""
Structranet AI — Grand Orchestrator (Main Entry Point)  V4.0

Offline export pipeline with interactive pause-and-resume loop:
  [1/6] Load catalog
  [2/6] User input + Preflight
  [3/6] Phase 1 — AI topology  (LOOP: pause → Edit or Continue)
  [4/6] Hardware injection + Node enrichment + Image manifest
  [5/6] Phase 2 — Software configs
  [6/6] GNS3 Export & Validation

V4.0 additions over V3.3:
  1. Interactive Phase 1 Checkpoint Loop (Requirement 3)
       After every Phase 1 generation the pipeline PAUSES and presents
       the AI's chain-of-thought + node/link summary to the user.
       The user can type "c" to continue to Phase 2, or "e" to supply
       edit feedback that is appended to chat history before re-running
       Phase 1.  The loop runs until the user approves the design or
       --max-edits is exhausted.

  2. Chain-of-Thought display (Requirement 2)
       The thinking_text returned by generate_network_topology() is
       printed in a clearly delimited box before asking for approval.

  3. Image Verification Manifest (Requirement 1)
       generate_image_manifest() is called immediately after
       process_and_save_topology() and writes output/image_manifest.txt.

  4. Rich node context (Requirement 4)
       _enrich_nodes() is called inside process_and_save_topology()
       (ai_agent.py) so the enriched dict flows into Phase 2 and export
       without any additional wiring here.

  5. Multi-Turn Chat History (Requirement 5)
       SessionState carries chat_history across Edit loop iterations.
       The accumulated history is passed to generate_network_topology()
       on every call so the LLM refines rather than restarts.

New CLI flags:
  --max-edits N     Maximum number of Edit iterations (default: 5)
  --auto-continue   Skip the interactive checkpoint (non-interactive runs)
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

from ai_agent import (
    SessionState,
    generate_image_manifest,
    generate_network_topology,
    process_and_save_topology,
)
from appliance_catalog import load_catalog
from config_agent import run_phase2
from constants.hardware import DYNAMIPS_MAX_PORTS
from gns3_exporter import convert as export_gns3project
from gns3project_validator import GNS3ProjectValidator
from preflight import (
    PreflightProfile,
    check_topology_compatibility,
    collect_profile_interactive,
    filter_inventory_by_profile,
    load_profile,
    profile_to_dict,
    save_profile,
)
from schema import GNS3Project

logger = logging.getLogger("structranet.main")

OUTPUT_DIR = os.getenv("STRUCTRANET_OUTPUT_DIR", "output")

# ─── Display helpers ─────────────────────────────────────────────────────────

_SEP = "=" * 70
_SEP_THIN = "-" * 70


def _print_box(title: str, body: str) -> None:
    print(f"\n{_SEP}")
    print(f"  {title}")
    print(_SEP_THIN)
    for line in body.splitlines():
        print(f"  {line}")
    print(_SEP)


def _print_thinking(thinking_text: str) -> None:
    if not thinking_text.strip():
        return
    _print_box("AI CHAIN-OF-THOUGHT (Architectural Reasoning)", thinking_text)


def _print_topology_summary(topology_dict: Dict[str, Any]) -> None:
    """Print a concise node + link table for the checkpoint display."""
    topo = topology_dict.get("topology", {})
    nodes = topo.get("nodes", [])
    links = topo.get("links", [])

    lines: List[str] = [
        f"Nodes ({len(nodes)}):",
        f"  {'ID':<12} {'Name':<22} {'Type':<18} {'Template':<25} {'Links'}",
        "  " + "-" * 80,
    ]

    # Count links per node
    link_counts: Dict[str, int] = {}
    for link in links:
        for ep in link.get("nodes", []):
            nid = ep.get("node_id", "")
            link_counts[nid] = link_counts.get(nid, 0) + 1

    for node in nodes:
        nid = node.get("node_id", "")
        name = node.get("name", "")
        ntype = node.get("node_type", "")
        template = node.get("template_name", "")
        lc = link_counts.get(nid, 0)
        lines.append(f"  {nid:<12} {name:<22} {ntype:<18} {template:<25} {lc}")

    lines.append("")
    lines.append(f"Links ({len(links)}):")
    for i, link in enumerate(links):
        eps = link.get("nodes", [])
        if len(eps) >= 2:
            a = eps[0].get("node_id", "?")
            b = eps[1].get("node_id", "?")
            ltype = link.get("link_type", "ethernet")
            lines.append(f"  [{i+1:02d}] {a} <--({ltype})--> {b}")

    _print_box("PHASE 1 DRAFT TOPOLOGY", "\n".join(lines))


# ─── CLI Arguments ────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Structranet AI — Natural Language to GNS3 Topology"
    )
    parser.add_argument("--request", "-r", type=str, default=None,
                        help="Network description (skips interactive prompt)")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Output JSON file path")
    parser.add_argument("--catalog", type=str, default=None,
                        help="Path to custom appliance catalog JSON overlay")
    parser.add_argument("--profile", type=str, default=None,
                        help="Path to preflight environment profile JSON")
    parser.add_argument("--no-phase2", action="store_true",
                        help="Skip Phase 2 (software configuration generation)")
    parser.add_argument("--project-output", type=str, default=None,
                        help="Output .gns3project path")
    parser.add_argument("--no-validate", action="store_true",
                        help="Skip .gns3project structural validation")
    parser.add_argument("--configs", type=str, default=None, metavar="DIR",
                        help="Export raw configs to DIR for pre-GNS3 review")
    parser.add_argument("--yes", action="store_true",
                        help="Auto-approve all interactive checkpoints (alias for --auto-continue)")
    parser.add_argument("--auto-continue", action="store_true",
                        help="Skip interactive checkpoint loop (non-interactive mode)")
    parser.add_argument("--max-edits", type=int, default=5,
                        help="Maximum number of Edit loop iterations (default: 5)")
    parser.add_argument(
        "--security-profile",
        choices=["none", "basic", "enterprise"],
        default=None,
        help="Apply automated security hardening (default: none)",
    )
    return parser.parse_args()


# ─── Catalog → Inventory Adapter ─────────────────────────────────────────────

_DYNAMIPS_MAX_PORTS = DYNAMIPS_MAX_PORTS
_SINGLE_PORT_TYPES = {"vpcs", "traceng", "nat"}
_MAX_EXPANDABLE_PORTS = {
    "iou": 16, "qemu": 8, "docker": 8,
    "virtualbox": 8, "vmware": 10,
    "ethernet_switch": 128, "ethernet_hub": 128,
}


def catalog_to_inventory(catalog: dict) -> List[Dict[str, Any]]:
    inventory = []
    for name, props in catalog.items():
        ntype = props.get("node_type", "")
        entry: Dict[str, Any] = {
            "name": name,
            "gns3_type": ntype,
            "category": props.get("category", ""),
        }
        if ntype in _SINGLE_PORT_TYPES:
            entry["port_count"] = 1
        elif ntype == "dynamips":
            platform = props.get("platform", "").lower()
            entry["port_count"] = _DYNAMIPS_MAX_PORTS.get(platform, 3)
        elif ntype == "iou":
            eth = props.get("ethernet_adapters", 0)
            ser = props.get("serial_adapters", 0)
            entry["port_count"] = eth * 4 + ser * 4
        elif ntype in _MAX_EXPANDABLE_PORTS:
            entry["port_count"] = _MAX_EXPANDABLE_PORTS[ntype]
        inventory.append(entry)
    return inventory


# ─── Design Review helper ─────────────────────────────────────────────────────

def _build_design_review(
    topology_dict: Dict[str, Any],
    profile: PreflightProfile,
    compatibility_issues: List[str],
) -> tuple[List[str], List[str]]:
    topo = topology_dict.get("topology", {})
    nodes = topo.get("nodes", [])
    links = topo.get("links", [])

    counts_by_type: Dict[str, int] = {}
    for n in nodes:
        ntype = str(n.get("node_type", "unknown"))
        counts_by_type[ntype] = counts_by_type.get(ntype, 0) + 1

    node_types = sorted(counts_by_type)
    thoughts = [
        f"Designed topology with {len(nodes)} node(s) and {len(links)} link(s).",
        "Node type mix: " + ", ".join(
            f"{k}={v}" for k, v in sorted(counts_by_type.items())
        ),
    ]

    assumptions: List[str] = []
    if "dynamips" in node_types:
        assumptions.append(
            "Dynamips images/templates on your machine match the selected catalog names."
        )
    if "iou" in node_types:
        assumptions.append("IOU is available and licensed on your environment.")
    if "qemu" in node_types:
        assumptions.append("Required QEMU images exist on your machine.")
    if "docker" in node_types:
        assumptions.append("Docker is available and integrated with GNS3.")
    if not assumptions:
        assumptions.append(
            "Built-in and selected node types are available on your machine."
        )
    if not str(profile.gns3_version).startswith("2.2"):
        assumptions.append(
            f"GNS3 version '{profile.gns3_version}' may behave differently "
            "than expected 2.2.x."
        )
    if compatibility_issues:
        assumptions.extend(compatibility_issues)

    return thoughts, assumptions


# ─── Interactive Phase 1 Checkpoint Loop ──────────────────────────────────────

def _checkpoint_loop(
    state: SessionState,
    user_request: str,
    filtered_inventory: List[Dict[str, Any]],
    blocked_types: set,
    profile: PreflightProfile,
    phase1_file: str,
    manifest_file: str,
    auto_continue: bool,
    max_edits: int,
) -> Optional[GNS3Project]:
    """Run Phase 1 in a pause-and-resume loop.

    The loop:
      1. Calls generate_network_topology() (with accumulated chat history).
      2. Displays the chain-of-thought and the draft topology table.
      3. Pauses and asks: Continue / Edit.
      4a. Continue → process_and_save_topology(), generate manifest, return.
      4b. Edit     → capture feedback, append to history, loop.

    Returns the enriched GNS3Project on approval, or None on failure.
    """
    for edit_num in range(max_edits + 1):
        if edit_num == 0:
            current_request = user_request
        else:
            # edit feedback was already appended to state.chat_history
            current_request = user_request  # the original request is anchor

        print(f"\n{'─'*70}")
        if edit_num == 0:
            print("[3/6] Phase 1 — AI generating logical topology...")
        else:
            print(f"[3/6] Phase 1 — Re-generating topology (Edit iteration {edit_num}/{max_edits})...")

        result, thinking_text, updated_history = generate_network_topology(
            current_request,
            filtered_inventory,
            disallowed_node_types=blocked_types,
            security_profile=profile.security_profile,
            chat_history=state.chat_history,
        )

        # Always persist the updated history
        state.chat_history = updated_history
        state.thinking_text = thinking_text
        state.iteration = edit_num + 1

        if result is None:
            print("[ERR] AI generation failed. Check your API key and model config.")
            if edit_num < max_edits:
                retry = input(
                    "  Generation failed. Try again? [Y/n] "
                ).strip().lower()
                if retry not in ("n", "no"):
                    continue
            return None

        print(
            f"  Generated {len(result.topology.nodes)} node(s), "
            f"{len(result.topology.links)} link(s)"
        )

        # ── Display chain-of-thought ─────────────────────────────────────────
        _print_thinking(thinking_text)

        # Convert to dict for display (pre-hardware-injection)
        raw_dict = result.model_dump()
        _print_topology_summary(raw_dict)

        # ── Checkpoint pause ─────────────────────────────────────────────────
        if auto_continue:
            print("  [auto-continue] Proceeding without interactive checkpoint.")
            decision = "c"
        else:
            print("\n  What would you like to do?")
            print("    [C] Continue  — accept this design and proceed to Phase 2")
            print("    [E] Edit      — provide feedback and regenerate")
            print("    [Q] Quit      — abort pipeline")
            decision = input("\n  Your choice [C/e/q]: ").strip().lower() or "c"

        if decision in ("q", "quit"):
            print("  Pipeline aborted by user.")
            sys.exit(0)

        if decision in ("e", "edit"):
            if edit_num >= max_edits:
                print(
                    f"\n[WARN] Maximum edit iterations ({max_edits}) reached. "
                    "Proceeding with current design."
                )
            else:
                feedback = input(
                    "\n  Describe your changes (be specific about nodes/links/topology):\n  > "
                ).strip()
                if feedback:
                    # Append user feedback as a new user turn so the LLM sees it
                    # as a continuation of the existing conversation
                    state.chat_history.append({
                        "role": "user",
                        "content": (
                            f"Please modify the topology based on this feedback: {feedback}\n"
                            "Return the complete updated design in the same CoT JSON envelope format."
                        ),
                    })
                    print(f"  Feedback recorded. Re-running Phase 1 (iteration {edit_num + 1})...")
                    continue
                else:
                    print("  No feedback entered — treating as Continue.")

        # ── Approved: inject hardware + enrich + patch ───────────────────────
        print("\n[4/6] Phase 1 — Injecting hardware, enriching nodes, patching VLANs...")
        enriched = process_and_save_topology(result, phase1_file)
        if enriched is None:
            print("[ERR] Hardware injection failed. Check logs above.")
            if not auto_continue:
                retry = input("  Try editing the design? [Y/n] ").strip().lower()
                if retry not in ("n", "no"):
                    state.chat_history.append({
                        "role": "user",
                        "content": (
                            "The hardware injection step failed for the last design. "
                            "Please simplify the topology or reduce the number of links per router."
                        ),
                    })
                    continue
            return None

        print(f"  Hardware-injected topology saved to: {phase1_file}")
        state.topology_dict = enriched.model_dump()

        # ── Image manifest ────────────────────────────────────────────────────
        print("  Generating image verification manifest...")
        manifest_path = generate_image_manifest(
            state.topology_dict,
            profile.normalized_template_image_map,
            manifest_file,
        )
        print(f"  Image manifest: {manifest_path}")
        _print_image_manifest_summary(state.topology_dict, profile.normalized_template_image_map)

        return enriched

    # Fell through all edit iterations
    print(f"\n[WARN] Edit limit ({max_edits}) exhausted — using last generated design.")
    if state.topology_dict:
        try:
            return GNS3Project.model_validate(state.topology_dict)
        except Exception:
            pass
    return None


def _print_image_manifest_summary(
    topology_dict: Dict[str, Any],
    template_image_map: Dict[str, str],
) -> None:
    """Print a compact image readiness summary inline (full file written separately)."""
    from ai_agent import _APPLIANCE_NODE_TYPES, _BUILTIN_NODE_TYPES  # noqa: PLC0415

    topo = topology_dict.get("topology", {})
    nodes = topo.get("nodes", [])
    missing = [
        f"{n.get('node_id')}/{n.get('template_name')}"
        for n in nodes
        if n.get("node_type") in _APPLIANCE_NODE_TYPES
        and n.get("template_name") not in template_image_map
    ]
    if missing:
        print(f"\n  ⚠  {len(missing)} node(s) have no image mapping:")
        for m in missing:
            print(f"     {m}")
        print("  → Update preflight template_image_map or verify manually before import.")
    else:
        print("  ✓  All appliance nodes have image mappings.")


# ─── Main Pipeline ────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(name)s [%(levelname)s] %(message)s"
    )

    auto_continue = args.yes or args.auto_continue

    print(_SEP)
    print("  Structranet AI — Natural Language to GNS3 Topology JSON")
    print("  (Topology + Hardware + Software Config + Interactive Review)")
    print(_SEP + "\n")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── [1/6] Load catalog ───────────────────────────────────────────────────
    print("[1/6] Loading appliance catalog...")
    catalog = load_catalog(args.catalog)
    inventory = catalog_to_inventory(catalog)
    if not inventory:
        print("[ERR] No appliances in catalog. Add entries to appliance_catalog.py.")
        sys.exit(1)
    print(
        f"  Found {len(inventory)} appliance(s): "
        f"{', '.join(d['name'] for d in inventory)}"
    )

    # ── [2/6] User input + Preflight ─────────────────────────────────────────
    print(f"\n[2/6] Describe the network you want.")
    print(f"  Available: {', '.join(d['name'] for d in inventory)}")
    if args.request:
        user_request = args.request
        print(f"  Request: {user_request}")
    else:
        user_request = input("\n  > ")
    if not user_request.strip():
        print("[ERR] No input. Exiting.")
        sys.exit(1)

    if args.profile:
        try:
            profile = load_profile(args.profile)
            print(f"\n[Preflight] Loaded profile: {args.profile}")
        except Exception as exc:
            print(f"[ERR] Failed to load profile '{args.profile}': {exc}")
            sys.exit(1)
    else:
        profile = collect_profile_interactive()
        profile_path = os.path.join(OUTPUT_DIR, "preflight_profile.json")
        save_profile(profile, profile_path)
        print(f"[Preflight] Profile saved to: {profile_path}")

    if getattr(args, "security_profile", None):
        profile.security_profile = args.security_profile
        print(
            f"[Preflight] Security Profile enforced via CLI: "
            f"{profile.security_profile.upper()}"
        )

    filtered_inventory, blocked_types = filter_inventory_by_profile(inventory, profile)
    if not filtered_inventory:
        print("[ERR] Profile blocks all available node types in inventory.")
        sys.exit(1)
    if len(filtered_inventory) != len(inventory):
        print(
            f"[Preflight] Filtering unsupported types: "
            f"{', '.join(sorted(blocked_types))}"
        )

    # ── [3+4/6] Interactive Phase 1 Checkpoint Loop ──────────────────────────
    phase1_file = os.path.join(OUTPUT_DIR, "_topology.json")
    manifest_file = os.path.join(OUTPUT_DIR, "image_manifest.txt")
    state = SessionState(last_request=user_request)

    enriched = _checkpoint_loop(
        state=state,
        user_request=user_request,
        filtered_inventory=filtered_inventory,
        blocked_types=blocked_types,
        profile=profile,
        phase1_file=phase1_file,
        manifest_file=manifest_file,
        auto_continue=auto_continue,
        max_edits=args.max_edits,
    )

    if enriched is None:
        print("[ERR] Phase 1 could not produce an approved topology.")
        sys.exit(1)

    topo_dict = enriched.model_dump()

    # ── Compatibility + design review ─────────────────────────────────────────
    compatibility_issues = check_topology_compatibility(topo_dict, profile)
    if compatibility_issues:
        print("\n[Compatibility] Found environment issues:")
        for issue in compatibility_issues:
            print(f"  - {issue}")
        if profile.strict_validation:
            print("[ERR] Aborting due to strict preflight validation.")
            sys.exit(1)
        print("[WARN] Continuing (strict_validation=false).")

    thoughts, assumptions = _build_design_review(
        topo_dict, profile, compatibility_issues
    )
    print("\n[Design Review]")
    for t in thoughts:
        print(f"  - {t}")
    print("  Assumptions / risks:")
    for a in assumptions:
        print(f"    * {a}")

    # ── [5/6] Phase 2 — Software configuration ───────────────────────────────
    final_file = args.output or os.path.join(OUTPUT_DIR, "final_topology.json")

    if args.no_phase2:
        print("\n[5/6] Phase 2 — SKIPPED (--no-phase2 flag set)")
        final_dict = topo_dict
        with open(final_file, "w", encoding="utf-8") as f:
            json.dump(final_dict, f, indent=2)
        print(f"  Phase 1 output saved as final: {final_file}")
    else:
        print(
            "\n[5/6] Phase 2 — Generating software configurations (IP/routing/startup)..."
        )
        final_dict = run_phase2(
            phase1_file, final_file, security_profile=profile.security_profile
        )
        if final_dict is None:
            print(
                "[WARN] Phase 2 failed — falling back to Phase 1 topology "
                "(no software configs)."
            )
            final_dict = topo_dict
            with open(final_file, "w", encoding="utf-8") as f:
                json.dump(final_dict, f, indent=2)
            print(f"  Phase 1 topology saved as final: {final_file}")
        else:
            print(f"  Phase 2 complete. Final topology saved to: {final_file}")

    node_count = len(final_dict.get("topology", {}).get("nodes", []))
    link_count = len(final_dict.get("topology", {}).get("links", []))
    configured = sum(
        1
        for n in final_dict.get("topology", {}).get("nodes", [])
        if n.get("properties") and any(
            k in n["properties"]
            for k in ("startup_config_content", "startup_script", "start_command")
        )
    )
    print(
        f"\n  Summary: {node_count} node(s), {link_count} link(s), "
        f"{configured} node(s) with software configs"
    )
    print(f"  Output: {final_file}")

    if not auto_continue:
        confirm = input(
            "\nDesign looks ready. Proceed with GNS3 export and validation? [Y/n] "
        ).strip().lower()
        if confirm in ("n", "no"):
            print("Stopped before export at your request.")
            sys.exit(0)

    # ── [6/6] Export + Validate ───────────────────────────────────────────────
    print("\n[6/6] Exporting portable GNS3 project (.gns3project)...")
    project_output = args.project_output
    if not project_output:
        final_stem = Path(final_file).stem
        project_output = os.path.join(OUTPUT_DIR, f"{final_stem}.gns3project")

    config_review_dir = args.configs
    if config_review_dir is None:
        config_review_dir = os.path.join(OUTPUT_DIR, "configs_review")

    try:
        project_path = export_gns3project(
            final_dict,
            project_output,
            image_map=profile.normalized_template_image_map,
            config_review_dir=config_review_dir,
        )
        print(f"  Export complete: {project_path}")
    except Exception as exc:
        print(f"[ERR] Export failed: {exc}")
        sys.exit(1)

    validator_ok = None
    if args.no_validate:
        print("  Validation skipped (--no-validate)")
    else:
        print("  Running structural validator...")
        validator = GNS3ProjectValidator(project_path, verbose=False)
        validator_ok = validator.validate()
        if validator_ok:
            print("  Validator result: PASS")
        else:
            print("[ERR] Validator result: FAIL (see issues above)")

    # ── Generation report ─────────────────────────────────────────────────────
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "request": user_request,
        "profile": profile_to_dict(profile),
        "phase1_iterations": state.iteration,
        "phase2_skipped": bool(args.no_phase2),
        "compatibility_issues": compatibility_issues,
        "design_review": {"thoughts": thoughts, "assumptions": assumptions},
        "last_thinking": state.thinking_text,
        "outputs": {
            "phase1_json": phase1_file,
            "final_json": final_file,
            "gns3project": project_path,
            "image_manifest": manifest_file,
        },
        "validator": {
            "skipped": bool(args.no_validate),
            "passed": validator_ok,
        },
    }
    report_path = os.path.join(OUTPUT_DIR, "generation_report.json")
    with open(report_path, "w", encoding="utf-8") as rf:
        json.dump(report, rf, indent=2)
    print(f"  Generation report: {report_path}")

    if validator_ok is False:
        sys.exit(1)


if __name__ == "__main__":
    main()