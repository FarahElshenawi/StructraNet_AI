"""
constants/validation.py — Structural Validation Constants for Structranet AI

Verified against:
  gns3-gui/gns3/modules/dynamips/settings.py  ADAPTER_MATRIX
  GNS3 Dynamips README
  GNS3 official docs (cisco-ios-images-for-dynamips)

Key corrections vs previous version:
  1. C3700_NMS: removed NM-1E, NM-4E, NM-1T — those are C3600-only.
     Official C3700_NMS = ("NM-1FE-TX", "NM-4T", "NM-16ESW")
  2. C3600_NMS: removed NM-1D (does not exist in GNS3 source).
     Official C3600_NMS = ("NM-1FE-TX", "NM-1E", "NM-4E", "NM-16ESW", "NM-4T")
  3. c1700: NO NM slots. Slot 0 is motherboard-only (C1700-MB-1FE).
     Removed NM-1FE-TX/NM-1E/NM-4E from c1700 slots — they are invalid there.
     Corrected chip name C1700-MB-1ETH → C1700-MB-1FE.
  4. c2600: only 1 NM slot (slot 1). Slot 0 is motherboard.
     Reduced from 2 slots to 1 configurable slot.
  5. c3660 builtin_ifaces corrected: Leopard-2FE provides 2 ports. (was correct)
  6. Added c3600 alias entry (GNS3 uses platform="c3600" for all 3620/3640/3660).
  7. c1700 ram_range: min 128MB per GNS3 docs (minimum image requires 128MB).
  8. MODULE_PORT_COUNT derived from constants/hardware.py — single source of truth.
"""

from typing import Dict, FrozenSet, List, Tuple

from constants.hardware import (
    C2600_MOTHERBOARDS,
    C2600_NMS,
    DYNAMIPS_MODULE_INTERFACES,
)

# ═══════════════════════════════════════════════════════════════════════════════
#  Node-type taxonomy
# ═══════════════════════════════════════════════════════════════════════════════

VALID_NODE_TYPES: FrozenSet[str] = frozenset([
    "cloud", "nat", "ethernet_hub", "ethernet_switch",
    "frame_relay_switch", "atm_switch",
    "docker", "dynamips", "vpcs", "traceng",
    "virtualbox", "vmware", "iou", "qemu",
])

BUILTIN_NODE_TYPES: FrozenSet[str] = frozenset([
    "vpcs", "ethernet_switch", "ethernet_hub",
    "cloud", "nat", "traceng",
    "frame_relay_switch", "atm_switch",
])

APPLIANCE_NODE_TYPES: FrozenSet[str] = frozenset([
    "dynamips", "iou", "qemu", "docker", "virtualbox", "vmware",
])


# ═══════════════════════════════════════════════════════════════════════════════
#  Dynamips platform compatibility matrix
# ═══════════════════════════════════════════════════════════════════════════════

# --- Module lists (sourced directly from GNS3 settings.py) ---

# C3700_NMS: valid for c3725, c3745, c2691
# Source: gns3-gui settings.py C3700_NMS = ("NM-1FE-TX", "NM-4T", "NM-16ESW")
# NM-1E, NM-4E, NM-1T, NM-1D are C3600-only and must NOT appear here.
# (NM-1D does not exist in GNS3 at all; removed from C3600_NMS too.)
_C3700_NMS: List[str] = [
    "NM-1FE-TX",
    "NM-4T",
    "NM-16ESW",
]

# C3600_NMS: valid for c3620, c3640, c3660
# Source: gns3-gui settings.py C3600_NMS = ("NM-1FE-TX", "NM-1E", "NM-4E",
#                                            "NM-16ESW", "NM-4T")
# NM-1D does NOT exist in GNS3 — removed (was erroneously added).
_C3600_NMS: List[str] = [
    "NM-1FE-TX",
    "NM-1E",
    "NM-4E",
    "NM-16ESW",
    "NM-4T",
]

# C2600_NMS: valid for c2600 slot 1 only
# Source: gns3-gui settings.py C2600_NMS = ("NM-1FE-TX", "NM-1E", "NM-4E", "NM-16ESW")
# NO serial modules — c2600 serial is WIC-only (not modeled here)
# Imported from constants.hardware for single source of truth.
_C2600_NMS: List[str] = list(C2600_NMS)

# C2600_MOTHERBOARDS: valid for c2600 slot 0 only
# Source: gns3-gui settings.py C2600_MOTHERBOARDS
# These are motherboard chips, NOT Network Modules.
_C2600_MOTHERBOARDS: List[str] = list(C2600_MOTHERBOARDS)

# C7200_PAS: valid for c7200 slots 1-6
# Source: gns3-gui settings.py C7200_PAS
_C7200_PAS: List[str] = [
    "PA-A1", "PA-FE-TX", "PA-2FE-TX", "PA-GE",
    "PA-4T+", "PA-8T", "PA-4E", "PA-8E", "PA-POS-OC3",
]

# IO_C7200: valid for c7200 slot 0 only
# Source: gns3-gui settings.py IO_C7200
_IO_C7200: List[str] = [
    "C7200-IO-FE",
    "C7200-IO-2FE",
    "C7200-IO-GE-E",
]

DYNAMIPS_COMPAT: Dict[str, Dict] = {

    # ── c7200 ────────────────────────────────────────────────────────────────
    # Slot 0 = I/O controller (required). Slots 1-6 = PA modules.
    "c7200": {
        "builtin_ifaces": 0,   # built-in count depends on IO controller chosen
        "slots": {
            0: _IO_C7200,
            1: _C7200_PAS, 2: _C7200_PAS, 3: _C7200_PAS,
            4: _C7200_PAS, 5: _C7200_PAS, 6: _C7200_PAS,
        },
        "valid_images": [r"c7200.*\.image", r"c7200.*\.bin"],
        "ram_range": (256, 1024),
    },

    # ── c3745 ────────────────────────────────────────────────────────────────
    # Slot 0 = GT96100-FE (fixed, 2 FastEthernet ports).
    # Slots 1-4 = C3700_NMS only (NM-1FE-TX, NM-4T, NM-16ESW).
    # NM-4E is NOT valid here — it is C3600-only.
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
    # Slot 0 = GT96100-FE (fixed, 2 FastEthernet ports).
    # Slots 1-2 = C3700_NMS only.
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
    # Slot 0 = Leopard-2FE (fixed, 2 FastEthernet ports).
    # Slots 1-6 = C3600_NMS.
    # GNS3 stores this as platform="c3600", chassis="3660".
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
    # No fixed motherboard Ethernet. All 4 slots are C3600_NMS.
    # GNS3 stores this as platform="c3600", chassis="3640".
    "c3640": {
        "builtin_ifaces": 0,
        "slots": {
            0: _C3600_NMS, 1: _C3600_NMS, 2: _C3600_NMS, 3: _C3600_NMS,
        },
        "valid_images": [r"c3640.*\.bin"],
        "ram_range": (128, 512),
    },

    # ── c3620 ────────────────────────────────────────────────────────────────
    # No fixed motherboard Ethernet. 2 NM slots = C3600_NMS.
    # GNS3 stores this as platform="c3600", chassis="3620".
    "c3620": {
        "builtin_ifaces": 0,
        "slots": {
            0: _C3600_NMS, 1: _C3600_NMS,
        },
        "valid_images": [r"c3620.*\.bin"],
        "ram_range": (64, 256),
    },

    # ── c2691 ────────────────────────────────────────────────────────────────
    # Slot 0 = GT96100-FE (fixed, 2 FastEthernet ports).
    # Slot 1 = C3700_NMS only (NM-1FE-TX, NM-4T, NM-16ESW).
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
    # Slot 0 = C2600-MB-* motherboard chip (NOT C3600_NMS — those are NM modules
    #          that are invalid in the motherboard slot). Acceptable values:
    #          C2600-MB-1E, C2600-MB-2E, C2600-MB-1FE, C2600-MB-2FE.
    # Slot 1 = 1 configurable NM slot using C2600_NMS (no serial modules).
    # (Previous version incorrectly used C3600_NMS for both slots.)
    "c2600": {
        "builtin_ifaces": 1,
        "slots": {
            0: _C2600_MOTHERBOARDS,  # motherboard chips only
            1: _C2600_NMS,           # C2600_NMS — no serial modules
        },
        "valid_images": [r"c2600.*\.bin"],
        "ram_range": (64, 256),
    },

    # ── c1700 ────────────────────────────────────────────────────────────────
    # Slot 0 = C1700-MB-1FE (fixed, 1 FastEthernet — corrected from C1700-MB-1ETH).
    # NO NM expansion slots. Only WIC subslots (not modeled here).
    # Adding NM modules to c1700 is invalid — GNS3 will reject them.
    "c1700": {
        "builtin_ifaces": 1,
        "slots": {
            0: ["C1700-MB-1FE"],
            # No NM slots — c1700 has no Network Module bay
        },
        "valid_images": [r"c1700.*\.bin"],
        "ram_range": (128, 256),
    },

    # ── c3600 (alias) ────────────────────────────────────────────────────────
    # GNS3 exports all c3620/c3640/c3660 with platform="c3600".
    # This alias prevents lookup from falling to the fallback.
    # Uses c3660 spec (most capable: Leopard-2FE + 6 NM slots).
    "c3600": {
        "builtin_ifaces": 2,
        "slots": {
            0: ["Leopard-2FE"] + _C3600_NMS,  # Leopard-2FE for c3660; C3600_NMS for c3640/c3620
            1: _C3600_NMS, 2: _C3600_NMS, 3: _C3600_NMS,
            4: _C3600_NMS, 5: _C3600_NMS, 6: _C3600_NMS,
        },
        "valid_images": [r"c3[0-9]+.*\.bin"],
        "ram_range": (64, 512),
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Module → port count lookup
#  Derived from constants/hardware.py — single source of truth.
# ═══════════════════════════════════════════════════════════════════════════════

MODULE_PORT_COUNT: Dict[str, int] = {
    name: info["count"]
    for name, info in DYNAMIPS_MODULE_INTERFACES.items()
}

# Extra modules that appear in DYNAMIPS_COMPAT but may not be in
# DYNAMIPS_MODULE_INTERFACES (various motherboard and I/O chips).
_EXTRA_MODULE_PORTS: Dict[str, int] = {
    "Leopard-2FE":    2,
    "C7200-IO-FE":    1,
    "C7200-IO-2FE":   2,
    "C7200-IO-GE-E":  1,
    # Corrected name: C1700-MB-1FE (not C1700-MB-1ETH)
    "C1700-MB-1FE":   1,
    "PA-A1":          1,
    "PA-POS-OC3":     1,
    # NM-1D removed — does not exist in GNS3 source code
    # c2600 motherboard chips — GNS3 source: C2600_MOTHERBOARDS
    "C2600-MB-1E":    1,
    "C2600-MB-2E":    2,
    "C2600-MB-1FE":   1,
    "C2600-MB-2FE":   2,
    "GT96100-FE":       2,
}
for _mod, _count in _EXTRA_MODULE_PORTS.items():
    MODULE_PORT_COUNT.setdefault(_mod, _count)