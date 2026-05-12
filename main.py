"""
Structranet AI — Grand Orchestrator (Main Entry Point)

Offline export pipeline:
  [1/5] Load catalog       → appliance_catalog.load_catalog (static appliance definitions)
  [2/5] User input         → CLI / interactive prompt
  [3/5] AI topology        → ai_agent.generate_network_topology (Phase 1: structure, properties={})
  [4/5] Hardware injection → ai_agent.process_and_save_topology (Phase 1: slots, adapters, ports_mapping)
  [5/5] Software configs   → config_agent.run_phase2           (Phase 2: IPs, routing, startup scripts)

Output: final_topology.json ready for .gns3project export.

Supported flags:
  --no-phase2              → Skip Phase 2 (software config generation)
  --catalog PATH           → Custom appliance catalog JSON overlay
"""

import argparse
import json
import logging
import os
from pathlib import Path
import sys

from appliance_catalog import load_catalog
from ai_agent import generate_network_topology, process_and_save_topology
from gns3_exporter import convert as export_gns3project
from gns3project_validator import GNS3ProjectValidator
from hw_config import DYNAMIPS_BUILTIN_PORTS, DYNAMIPS_BUILTIN_DEFAULT, DYNAMIPS_SLOT_MODULES
from config_agent import run_phase2

logger = logging.getLogger("structranet.main")

# Default output directory (overridable via env var)
OUTPUT_DIR = os.getenv("STRUCTRANET_OUTPUT_DIR", "output")


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI Arguments
# ═══════════════════════════════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(
        description="Structranet AI - Natural Language to GNS3 Topology JSON"
    )
    parser.add_argument("--request", "-r", type=str, default=None,
                        help="Network description (skips interactive prompt)")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Output JSON file path (default: output/final_topology.json)")
    parser.add_argument("--catalog", type=str, default=None,
                        help="Path to custom appliance catalog JSON overlay")
    parser.add_argument("--no-phase2", action="store_true",
                        help="Skip Phase 2 (software configuration generation)")
    parser.add_argument("--project-output", type=str, default=None,
                        help="Output .gns3project path (default: output/<final_json_stem>.gns3project)")
    parser.add_argument("--no-validate", action="store_true",
                        help="Skip .gns3project structural validation")
    return parser.parse_args()


# ═══════════════════════════════════════════════════════════════════════════════
#  Catalog → Inventory Adapter
# ═══════════════════════════════════════════════════════════════════════════════

# Port-count derivation constants
# Derive Dynamips limits from hw_config single source of truth:
# builtin ports + (ports_per_module * max_slots).
_DYNAMIPS_MAX_PORTS = {
    platform: (
        DYNAMIPS_BUILTIN_PORTS.get(platform, DYNAMIPS_BUILTIN_DEFAULT)
        + (cfg["ports_per_module"] * cfg["max_slots"])
    )
    for platform, cfg in DYNAMIPS_SLOT_MODULES.items()
}
_SINGLE_PORT_TYPES = {"vpcs", "traceng", "nat"}
_MAX_EXPANDABLE_PORTS = {
    "iou": 16, "qemu": 8, "docker": 8,
    "virtualbox": 8, "vmware": 10,
    "ethernet_switch": 128, "ethernet_hub": 128,
}


def catalog_to_inventory(catalog: dict) -> list[dict]:
    """Convert the appliance_catalog dict into the inventory list format
    expected by ai_agent.generate_network_topology().

    The catalog is keyed by template_name with values containing node_type
    and other hardware properties.  The inventory format is a flat list of
    dicts with name, gns3_type, category, and port_count fields.

    Port counts are derived from the catalog's hardware properties and
    the same constants used in schema.py's Topology validators.
    """
    inventory = []

    for name, props in catalog.items():
        ntype = props.get("node_type", "")
        entry = {
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


# ═══════════════════════════════════════════════════════════════════════════════
#  Main Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(name)s [%(levelname)s] %(message)s")

    print("=" * 60)
    print("  Structranet AI - Natural Language to GNS3 Topology JSON")
    print("  (Topology + Hardware + Software Config)")
    print("=" * 60 + "\n")

    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── Step 1/5: Load appliance catalog ────────────────────────────────────
    print("[1/5] Loading appliance catalog...")
    catalog = load_catalog(args.catalog)
    inventory = catalog_to_inventory(catalog)

    if not inventory:
        print("[ERR] No appliances in catalog. Add entries to appliance_catalog.py.")
        sys.exit(1)

    print(f"  Found {len(inventory)} appliance(s): "
          f"{', '.join(d['name'] for d in inventory)}")

    # ── Step 2/5: Get user input ────────────────────────────────────────────
    print(f"\n[2/5] Describe the network you want.")
    print(f"  Available: {', '.join(d['name'] for d in inventory)}")
    if args.request:
        user_request = args.request
        print(f"  Request: {user_request}")
    else:
        user_request = input("\n  > ")
    if not user_request.strip():
        print("[ERR] No input. Exiting.")
        sys.exit(1)

    # ── Step 3/5: Phase 1 — Logical topology generation ─────────────────────
    print("\n[3/5] Phase 1 — AI generating logical topology...")
    result = generate_network_topology(user_request, inventory)
    if not result:
        print("[ERR] AI generation failed. Check your API key and model config.")
        sys.exit(1)
    print(f"  Generated {len(result.topology.nodes)} node(s), "
          f"{len(result.topology.links)} link(s)")

    # ── Step 4/5: Phase 1 — Hardware injection + save ───────────────────────
    print("\n[4/5] Phase 1 — Injecting hardware expansion (slots/adapters/ports)...")
    phase1_file = os.path.join(OUTPUT_DIR, "_topology.json")
    enriched = process_and_save_topology(result, phase1_file)
    if not enriched:
        print("[ERR] Hardware injection failed. Check logs above.")
        sys.exit(1)
    print(f"  Hardware-injected topology saved to: {phase1_file}")

    topo_dict = enriched.model_dump()

    # ── Step 5/5: Phase 2 — Software configuration generation ───────────────
    final_file = args.output or os.path.join(OUTPUT_DIR, "final_topology.json")

    if args.no_phase2:
        print("\n[5/5] Phase 2 — SKIPPED (--no-phase2 flag set)")
        # Use Phase 1 output as the final topology
        final_dict = topo_dict
        # Save it as final
        with open(final_file, "w") as f:
            json.dump(final_dict, f, indent=2)
        print(f"  Phase 1 output saved as final: {final_file}")
    else:
        print("\n[5/5] Phase 2 — Generating software configurations (IP/routing/startup)...")
        final_dict = run_phase2(phase1_file, final_file)
        if final_dict is None:
            print("[WARN] Phase 2 failed — falling back to Phase 1 topology (no software configs).")
            final_dict = topo_dict
            # Save Phase 1 as the final file
            with open(final_file, "w") as f:
                json.dump(final_dict, f, indent=2)
            print(f"  Phase 1 topology saved as final: {final_file}")
        else:
            print(f"  Phase 2 complete. Final topology saved to: {final_file}")

    # ── Summary ──────────────────────────────────────────────────────────────
    node_count = len(final_dict.get("topology", {}).get("nodes", []))
    link_count = len(final_dict.get("topology", {}).get("links", []))
    # Count how many nodes have software configs
    configured = sum(
        1 for n in final_dict.get("topology", {}).get("nodes", [])
        if n.get("properties") and any(
            k in n["properties"]
            for k in ("startup_config_content", "startup_script", "start_command")
        )
    )
    print(f"\n  Summary: {node_count} node(s), {link_count} link(s), "
          f"{configured} node(s) with software configs")
    print(f"  Output: {final_file}")

    # ── Export: final_topology.json → .gns3project ───────────────────────────
    print("\n[6/6] Exporting portable GNS3 project (.gns3project)...")
    project_output = args.project_output
    if not project_output:
        final_stem = Path(final_file).stem
        project_output = os.path.join(OUTPUT_DIR, f"{final_stem}.gns3project")

    try:
        project_path = export_gns3project(final_dict, project_output)
        print(f"  Export complete: {project_path}")
    except Exception as exc:
        print(f"[ERR] Export failed: {exc}")
        sys.exit(1)

    # ── Validation gate (optional) ────────────────────────────────────────────
    if args.no_validate:
        print("  Validation skipped (--no-validate)")
    else:
        print("  Running structural validator...")
        validator = GNS3ProjectValidator(project_path, verbose=False)
        ok = validator.validate()
        if ok:
            print("  Validator result: PASS")
        else:
            print("[ERR] Validator result: FAIL (see issues above)")
            sys.exit(1)


if __name__ == "__main__":
    main()
