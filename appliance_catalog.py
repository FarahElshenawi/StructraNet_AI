"""
appliance_catalog.py -- Static Appliance Catalog for Structranet AI

Defines the mandatory creation properties for every GNS3 appliance type
that Structranet AI can emit.  These properties are required by the GNS3
server (or by the .gns3project portable-project format) to create a
functional node -- without them, GNS3 will reject the node or silently
default to broken values.

Phase A deliverable: Static Catalog + Mandatory Properties.

Design choices
~~~~~~~~~~~~~~
  * Each entry is keyed by **template_name** (the human-readable string
    the AI agent uses to identify a device, e.g. "Cisco 7200").
  * Values include ALL properties that GNS3 requires at node-creation
    time, minus the ones that hw_config.py will dynamically inject
    (slotN, adapters, ports_mapping).
  * The catalog is a plain dict so it can be serialised to JSON and
    shipped to users for customisation.
  * `load_catalog()` merges a user-supplied JSON overlay on top of the
    built-in defaults, giving users an escape hatch for custom images /
    RAM / non-standard platforms.
  * `get_appliance()` is the single lookup point that all other modules
    call -- they never access APPLIANCE_CATALOG directly.

Sources: GNS3 server v2.2 source code
  - gns3server/schemas/dynamips_template.py
  - gns3server/schemas/iou_template.py
  - gns3server/schemas/vpcs_template.py
  - gns3server/schemas/ethernet_switch_template.py
  - gns3server/schemas/ethernet_hub_template.py
  - gns3server/compute/dynamips/nodes/c7200.py
  - gns3server/compute/iou/iou_vm.py
"""

import json
import logging
import os
from copy import deepcopy
from typing import Any, Dict, Optional

logger = logging.getLogger("structranet.appliance_catalog")


# ═══════════════════════════════════════════════════════════════════════════════
#  Default Appliance Catalog
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Each entry maps a template_name to a dict of mandatory creation
#  properties.  The dict is NOT the complete GNS3 node -- it only
#  contains the keys that MUST be present in node["properties"] for
#  the .gns3project to be valid.
#
#  Mandatory keys per GNS3 node type:
#    dynamips : platform, image, ram, nvram, slot0, console_type,
#               port_name_format, port_segment_size
#    iou      : path, ram, nvram, ethernet_adapters, serial_adapters,
#               console_type, port_name_format, port_segment_size
#    vpcs     : console_type
#    ethernet_switch : console_type, port_name_format, port_segment_size
#    ethernet_hub    : port_name_format, port_segment_size
#

APPLIANCE_CATALOG: Dict[str, Dict[str, Any]] = {
    # ── Dynamips: Cisco 7200 Series ──────────────────────────────────────────
    # Ref: gns3server/compute/dynamips/nodes/c7200.py
    # The c7200 uses Port Adapters (PA-*) in slots 1-6.
    # Slot 0 is the NPE (Network Processing Engine) with built-in FastEthernet.
    "Cisco 7200": {
        "node_type": "dynamips",
        "platform": "c7200",
        "image": "c7200-adventerprisek9-mz.124-24.T5.image",
        "ram": 512,
        "nvram": 512,
        "slot0": "PA-FE-TX",           # NPE-400 built-in FastEthernet (1 port)
        "console_type": "telnet",
        "port_name_format": "FastEthernet{0}/{1}",
        "port_segment_size": 1,
    },

    # ── Dynamips: Cisco 3745 ─────────────────────────────────────────────────
    # Ref: gns3server/compute/dynamips/nodes/c3745.py
    # Uses Network Modules (NM-*) in slots 1-4.
    # Built-in: GT96100-FE on slot 0 (2 FastEthernet ports: Fa0/0, Fa0/1).
    "Cisco 3745": {
        "node_type": "dynamips",
        "platform": "c3745",
        "image": "c3745-adventerprisek9-mz.124-25d.image",
        "ram": 256,
        "nvram": 256,
        "slot0": "GT96100-FE",         # Built-in dual FastEthernet
        "console_type": "telnet",
        "port_name_format": "FastEthernet{0}/{1}",
        "port_segment_size": 1,
    },

    # ── IOU L3 (Layer 3 image -- routing) ────────────────────────────────────
    # Ref: gns3server/compute/iou/iou_vm.py
    # IOU uses integer slot values: 2 = Ethernet module with 4 ports,
    # 1 = Serial module with 4 ports, "l2" = L2 switching module.
    # Default: 2 ethernet adapters, 0 serial adapters.
    # application_id is auto-assigned by hw_config.py (see H-3).
    "IOU L3": {
        "node_type": "iou",
        "path": "/opt/gns3/images/i86bi-linux-l3-adventerprisek9-15.5.2T.bin",
        "ram": 256,
        "nvram": 128,
        "ethernet_adapters": 2,
        "serial_adapters": 0,
        "console_type": "telnet",
        "port_name_format": "Ethernet{0}/{1}",
        "port_segment_size": 4,
    },

    # ── IOU L2 (Layer 2 image -- switching) ──────────────────────────────────
    # L2 images use slot0 = "l2" for switching support.
    # Default: 1 ethernet adapter (with l2 module), 0 serial adapters.
    "IOU L2": {
        "node_type": "iou",
        "path": "/opt/gns3/images/i86bi-linux-l2-adventerprisek9-15.2d.bin",
        "ram": 256,
        "nvram": 128,
        "ethernet_adapters": 1,
        "serial_adapters": 0,
        "slot0": "l2",
        "console_type": "telnet",
        "port_name_format": "Ethernet{0}/{1}",
        "port_segment_size": 4,
    },

    # ── VPCS (Virtual PC Simulator) ──────────────────────────────────────────
    # Ref: gns3server/compute/vpcs/vpcs_vm.py
    # Hard-locked to 1 Ethernet port.  No expansion possible.
    "VPCS": {
        "node_type": "vpcs",
        "console_type": "telnet",
        "port_name_format": "Ethernet{0}",
        "port_segment_size": 1,
    },

    # ── Ethernet Switch (built-in GNS3 switch) ──────────────────────────────
    # Ref: gns3server/compute/builtin/nodes/ethernet_switch.py
    # Ports are managed via ports_mapping, NOT slots/adapters.
    "Ethernet Switch": {
        "node_type": "ethernet_switch",
        "console_type": "none",
        "port_name_format": "Ethernet{0}",
        "port_segment_size": 1,
    },

    # ── Ethernet Hub (built-in GNS3 hub) ────────────────────────────────────
    # Ref: gns3server/compute/builtin/nodes/ethernet_hub.py
    # Like a switch but all ports are access/untagged (no VLANs).
    "Ethernet Hub": {
        "node_type": "ethernet_hub",
        "port_name_format": "Ethernet{0}",
        "port_segment_size": 1,
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Catalog Loading with User Overlay
# ═══════════════════════════════════════════════════════════════════════════════

def load_catalog(user_path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Load the appliance catalog, optionally merging a user-supplied overlay.

    The merge strategy is **shallow merge per appliance**: for each key in
    the user JSON, the user's value completely overrides the default.
    New appliances (keys not in the built-in catalog) are added as-is.

    This keeps the merge simple and predictable -- users who want to
    override a single field (e.g., change the IOS image path) can
    provide just that field and the rest falls through from defaults.

    Args:
        user_path: Path to a JSON file with user-defined appliance
                   overrides.  If ``None`` or the file does not exist,
                   the built-in catalog is returned unchanged.

    Returns:
        A new dict containing the merged catalog.  The built-in
        APPLIANCE_CATALOG is never mutated.
    """
    catalog = deepcopy(APPLIANCE_CATALOG)

    if user_path is None:
        return catalog

    if not os.path.isfile(user_path):
        logger.warning(
            "User catalog file '%s' not found — using built-in defaults",
            user_path,
        )
        return catalog

    try:
        with open(user_path, "r", encoding="utf-8") as fh:
            user_overrides: Dict[str, Dict[str, Any]] = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error(
            "Failed to load user catalog '%s': %s — using built-in defaults",
            user_path, exc,
        )
        return catalog

    if not isinstance(user_overrides, dict):
        logger.error(
            "User catalog '%s' must be a JSON object (dict), got %s — "
            "using built-in defaults",
            user_path, type(user_overrides).__name__,
        )
        return catalog

    # Shallow-merge each appliance entry
    for name, overrides in user_overrides.items():
        if not isinstance(overrides, dict):
            logger.warning(
                "User catalog entry '%s' is not a dict — skipping", name,
            )
            continue

        if name in catalog:
            # Merge: user keys override default keys
            catalog[name].update(overrides)
            logger.info(
                "User catalog: merged overrides for appliance '%s' "
                "(%d keys overridden)", name, len(overrides),
            )
        else:
            # New appliance not in built-in catalog
            catalog[name] = deepcopy(overrides)
            logger.info(
                "User catalog: added new appliance '%s' (%d keys)",
                name, len(overrides),
            )

    return catalog


# ═══════════════════════════════════════════════════════════════════════════════
#  Appliance Lookup
# ═══════════════════════════════════════════════════════════════════════════════

def get_appliance(
    name: str,
    catalog: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Look up an appliance definition by template name.

    The lookup is case-insensitive to tolerate variations in how the
    LLM or user capitalises the name (e.g., "cisco 7200" vs "Cisco 7200").

    Args:
        name:    Template name to look up (e.g., "Cisco 7200", "IOU L3").
        catalog: Catalog dict to search.  If ``None``, the built-in
                 APPLIANCE_CATALOG is used (without user overlay).

    Returns:
        A *deep copy* of the appliance definition dict, or ``None`` if
        no match is found.  The copy ensures callers can mutate the
        result without polluting the catalog.
    """
    if catalog is None:
        catalog = APPLIANCE_CATALOG

    # Exact match first (fast path)
    if name in catalog:
        return deepcopy(catalog[name])

    # Case-insensitive fallback
    name_lower = name.lower()
    for key, value in catalog.items():
        if key.lower() == name_lower:
            return deepcopy(value)

    logger.debug("Appliance lookup failed for '%s' — no match in catalog", name)
    return None
