"""
constants/validation.py — Structural Validation Constants for Structranet AI

Single source of truth for:
  - GNS3 node-type taxonomy (valid, built-in, appliance)
  - Dynamips platform compatibility matrix (slots, RAM, image patterns)

Previously these lived inline in gns3project_validator.py.  Moving them here
means any future module that needs to check "is this a valid node type?" or
"what modules are legal in this slot?" can import from one place instead of
importing the entire validator.

MODULE_PORT_COUNT is intentionally derived from constants/hardware.py's
DYNAMIPS_MODULE_INTERFACES so there is no duplication.  The validator's old
inline copy had a bug (PA-FE-TX was listed as 2 ports; it has 1) and was
missing PA-GE, NM-1FE-TX, NM-16ESW, Leopard-2FE, and the C7200-IO-* variants.

Sources verified against:
  - GNS3 server 2.2 node schema (node_type enum)
  - gns3-gui/gns3/modules/dynamips/settings.py  ADAPTER_MATRIX
  - https://docs.gns3.com/docs/emulators/cisco-ios-images-for-dynamips/
"""

from typing import Dict, FrozenSet, List, Tuple

from constants.hardware import DYNAMIPS_MODULE_INTERFACES

# ═══════════════════════════════════════════════════════════════════════════════
#  Node-type taxonomy
# ═══════════════════════════════════════════════════════════════════════════════

# Every node_type the GNS3 2.2 server accepts (from the official JSON schema enum).
VALID_NODE_TYPES: FrozenSet[str] = frozenset([
    "cloud", "nat", "ethernet_hub", "ethernet_switch",
    "frame_relay_switch", "atm_switch",
    "docker", "dynamips", "vpcs", "traceng",
    "virtualbox", "vmware", "iou", "qemu",
])

# Built-in node types — these are provided by GNS3 itself and do NOT require a
# template_id.  They should never carry a template_id in an exported project.
BUILTIN_NODE_TYPES: FrozenSet[str] = frozenset([
    "vpcs", "ethernet_switch", "ethernet_hub",
    "cloud", "nat", "traceng",
    "frame_relay_switch", "atm_switch",
])

# Appliance node types — backed by an external emulator.  They SHOULD carry a
# template_id (or null for portable offline projects).  Without properties
# (platform, image, adapters, …) GNS3 cannot start them.
APPLIANCE_NODE_TYPES: FrozenSet[str] = frozenset([
    "dynamips", "iou", "qemu", "docker", "virtualbox", "vmware",
])


# ═══════════════════════════════════════════════════════════════════════════════
#  Dynamips platform compatibility matrix
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Keyed by platform string (lowercase, as stored in node.properties.platform).
#
#  Each entry contains:
#    builtin_ifaces : int   — ports provided by the fixed motherboard chip
#                             (these occupy adapter 0 and need no slot module)
#    slots          : dict  — {slot_number: [list of valid module names]}
#    valid_images   : list  — regex patterns the IOS image filename should match
#    ram_range      : tuple — (min_mb, max_mb) inclusive
#
#  Sources:
#    - gns3-gui/gns3/modules/dynamips/settings.py  ADAPTER_MATRIX
#    - https://docs.gns3.com/docs/emulators/cisco-ios-images-for-dynamips/
#    - https://docs.gns3.com/docs/emulators/hardware-emulated-by-gns3/

# Shorthand module lists used inside the matrix (same names GNS3 uses).
_C3600_NMS: List[str] = [
    "NM-1FE-TX", "NM-1E", "NM-4E", "NM-16ESW", "NM-4T", "NM-1T",
]
_C3700_NMS: List[str] = [
    "NM-1FE-TX", "NM-1E", "NM-4E", "NM-16ESW", "NM-4T", "NM-1T",
]
_C7200_PAS: List[str] = [
    "PA-FE-TX", "PA-2FE-TX", "PA-4E", "PA-8E", "PA-GE",
    "PA-4T+", "PA-8T", "PA-A1", "PA-POS-OC3",
]
_IO_C7200: List[str] = [
    "C7200-IO-FE", "C7200-IO-2FE", "C7200-IO-GE-E",
]

DYNAMIPS_COMPAT: Dict[str, Dict] = {
    # ── c7200 ────────────────────────────────────────────────────────────────
    # No fixed motherboard Ethernet.  Slot 0 must be an I/O controller.
    # Slots 1-6 accept standard PA modules.
    "c7200": {
        "builtin_ifaces": 0,
        "slots": {
            0: _IO_C7200,
            1: _C7200_PAS, 2: _C7200_PAS, 3: _C7200_PAS,
            4: _C7200_PAS, 5: _C7200_PAS, 6: _C7200_PAS,
        },
        "valid_images": [r"c7200.*\.image", r"c7200.*\.bin"],
        "ram_range": (256, 1024),
    },

    # ── c3745 ────────────────────────────────────────────────────────────────
    # 2 built-in FastEthernet via GT96100-FE in slot 0 (fixed).
    # 4 NM slots (1-4).
    "c3745": {
        "builtin_ifaces": 2,
        "slots": {
            0: ["GT96100-FE"],
            1: _C3700_NMS, 2: _C3700_NMS, 3: _C3700_NMS, 4: _C3700_NMS,
        },
        "valid_images": [r"c3745.*\.bin"],
        "ram_range": (128, 512),
    },

    # ── c3725 ────────────────────────────────────────────────────────────────
    # 2 built-in FastEthernet via GT96100-FE in slot 0 (fixed).
    # 2 NM slots (1-2).
    "c3725": {
        "builtin_ifaces": 2,
        "slots": {
            0: ["GT96100-FE"],
            1: _C3700_NMS, 2: _C3700_NMS,
        },
        "valid_images": [r"c3725.*\.bin"],
        "ram_range": (128, 512),
    },

    # ── c3660 ────────────────────────────────────────────────────────────────
    # 2 built-in FastEthernet via Leopard-2FE in slot 0 (fixed).
    # 6 NM slots (1-6) — note the validator's old matrix had 0 built-in (wrong).
    "c3660": {
        "builtin_ifaces": 2,
        "slots": {
            0: ["Leopard-2FE"],
            1: _C3600_NMS, 2: _C3600_NMS, 3: _C3600_NMS,
            4: _C3600_NMS, 5: _C3600_NMS, 6: _C3600_NMS,
        },
        "valid_images": [r"c3660.*\.bin"],
        "ram_range": (128, 512),
    },

    # ── c3640 ────────────────────────────────────────────────────────────────
    # No fixed motherboard Ethernet.  All 4 NM slots are user-configurable.
    "c3640": {
        "builtin_ifaces": 0,
        "slots": {
            0: _C3600_NMS, 1: _C3600_NMS, 2: _C3600_NMS, 3: _C3600_NMS,
        },
        "valid_images": [r"c3640.*\.bin"],
        "ram_range": (128, 512),
    },

    # ── c3620 ────────────────────────────────────────────────────────────────
    # No fixed motherboard Ethernet.  2 NM slots.
    "c3620": {
        "builtin_ifaces": 0,
        "slots": {
            0: _C3600_NMS, 1: _C3600_NMS,
        },
        "valid_images": [r"c3620.*\.bin"],
        "ram_range": (64, 256),
    },

    # ── c2691 ────────────────────────────────────────────────────────────────
    # 2 built-in FastEthernet via GT96100-FE.  1 NM slot.
    "c2691": {
        "builtin_ifaces": 2,
        "slots": {
            0: ["GT96100-FE"],
            1: _C3700_NMS,
        },
        "valid_images": [r"c2691.*\.bin"],
        "ram_range": (128, 512),
    },

    # ── c2600 ────────────────────────────────────────────────────────────────
    # 1 built-in FastEthernet.  1 NM slot.
    "c2600": {
        "builtin_ifaces": 1,
        "slots": {
            0: _C3600_NMS, 1: _C3600_NMS,
        },
        "valid_images": [r"c2600.*\.bin"],
        "ram_range": (64, 256),
    },

    # ── c1700 ────────────────────────────────────────────────────────────────
    # 1 built-in FastEthernet (C1700-MB-1ETH).  No NM slot (WIC slots only,
    # but Dynamips doesn't expose WICs as slot keys the same way).
    "c1700": {
        "builtin_ifaces": 1,
        "slots": {
            0: ["C1700-MB-1ETH", "NM-1FE-TX", "NM-1E", "NM-4E"],
        },
        "valid_images": [r"c1700.*\.bin"],
        "ram_range": (64, 256),
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Module → port count lookup
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Derived from constants/hardware.py DYNAMIPS_MODULE_INTERFACES so there is
#  exactly ONE source of truth for port counts.  The validator's old inline
#  copy had PA-FE-TX = 2 (wrong; it's 1) and was missing several modules.

MODULE_PORT_COUNT: Dict[str, int] = {
    name: info["count"]
    for name, info in DYNAMIPS_MODULE_INTERFACES.items()
}

# Add modules that appear in DYNAMIPS_COMPAT but may not be in
# DYNAMIPS_MODULE_INTERFACES (C7200 I/O controllers, Leopard-2FE, etc.).
# These are additive — they don't override anything already derived above.
_EXTRA_MODULE_PORTS: Dict[str, int] = {
    "Leopard-2FE":    2,
    "C7200-IO-FE":    1,
    "C7200-IO-2FE":   2,
    "C7200-IO-GE-E":  1,
    "C1700-MB-1ETH":  1,
    "PA-A1":          1,
    "PA-POS-OC3":     1,
}
for _mod, _count in _EXTRA_MODULE_PORTS.items():
    MODULE_PORT_COUNT.setdefault(_mod, _count)
