"""
constants/hardware.py — Verified against GNS3 source:
  gns3-gui/gns3/modules/dynamips/settings.py  ADAPTER_MATRIX / C3600_NMS / C3700_NMS
  GNS3 Dynamips README (platform slot documentation)
  GNS3 official docs (cisco-ios-images-for-dynamips)

Key corrections vs previous version:
  - c3745/c3725/c2691 Ethernet expansion: NM-4E → NM-1FE-TX (NM-4E is C3600-only)
    C3700_NMS = ("NM-1FE-TX", "NM-4T", "NM-16ESW")  ← official GNS3 source
    C3600_NMS = ("NM-1FE-TX", "NM-1E", "NM-4E", "NM-1D", "NM-4T", "NM-16ESW")
  - c1700 motherboard chip: C1700-MB-1ETH → C1700-MB-1FE (correct GNS3 name)
  - c1700 has NO NM slots — removed erroneous NM entries from slot tables
  - Added c3600 as a top-level platform (GNS3 stores c3620/c3640/c3660 as
    platform="c3600" with a chassis field; we keep our internal split but add
    the alias so lookup never falls through to the fallback)
  - c2600 corrected to 1 NM slot (slot 1 only; slot 0 is motherboard)
  - DYNAMIPS_MAX_LINKS in ai.py must match — see comments below
"""
from typing import Any, Dict

# ---------------------------------------------------------------------------
# VM / Docker adapter caps
# ---------------------------------------------------------------------------
MAX_ADAPTERS: Dict[str, int] = {
    "qemu": 275,
    "docker": 99,
    "virtualbox": 8,
    "vmware": 10,
}

# ---------------------------------------------------------------------------
# Dynamips Ethernet expansion modules
#
# C3700_NMS (c3745, c3725, c2691):
#   Official list: NM-1FE-TX, NM-4T, NM-16ESW
#   NM-4E is NOT in C3700_NMS — it is C3600-only.
#
# C3600_NMS (c3620, c3640, c3660):
#   Official list: NM-1FE-TX, NM-1E, NM-4E, NM-1D, NM-4T, NM-16ESW
#
# Therefore:
#   c3745 / c3725 / c2691 → use NM-1FE-TX (1 port per slot)
#   c3620 / c3640 / c3660 → use NM-4E   (4 ports per slot)  ← unchanged
#   c2600                 → use NM-1E   (1 port per slot)   ← C3600_NMS subset
# ---------------------------------------------------------------------------
DYNAMIPS_SLOT_MODULES: Dict[str, Dict[str, Any]] = {
    # c7200: slot 0 = IO controller (fixed), slots 1-6 = PA modules
    "c7200": {"module": "PA-8E",     "ports_per_module": 8, "first_configurable": 1, "max_slots": 6},

    # c3745: slot 0 = GT96100-FE (fixed), slots 1-4 = C3700_NMS
    # NM-1FE-TX is the correct C3700 Ethernet NM (1 port per slot)
    "c3745": {"module": "NM-1FE-TX", "ports_per_module": 1, "first_configurable": 1, "max_slots": 4},

    # c3725: slot 0 = GT96100-FE (fixed), slots 1-2 = C3700_NMS
    "c3725": {"module": "NM-1FE-TX", "ports_per_module": 1, "first_configurable": 1, "max_slots": 2},

    # c3660: slot 0 = Leopard-2FE (fixed), slots 1-6 = C3600_NMS
    # Stored internally as "c3660" but GNS3 exports platform="c3600", chassis="3660"
    "c3660": {"module": "NM-4E",     "ports_per_module": 4, "first_configurable": 1, "max_slots": 6},

    # c3640: no fixed slot 0, slots 0-3 = C3600_NMS
    "c3640": {"module": "NM-4E",     "ports_per_module": 4, "first_configurable": 0, "max_slots": 4},

    # c3620: no fixed slot 0, slots 0-1 = C3600_NMS
    "c3620": {"module": "NM-4E",     "ports_per_module": 4, "first_configurable": 0, "max_slots": 2},

    # c2691: slot 0 = GT96100-FE (fixed), slot 1 = C3700_NMS
    "c2691": {"module": "NM-1FE-TX", "ports_per_module": 1, "first_configurable": 1, "max_slots": 1},

    # c2600: slot 0 = motherboard (fixed), slot 1 = C3600_NMS
    # NM-1E is the safest single-port C3600 Ethernet NM for c2600
    "c2600": {"module": "NM-1E",     "ports_per_module": 1, "first_configurable": 1, "max_slots": 1},

    # c1700: NO NM slots — only WIC subslots (not modeled here)
    # Motherboard provides 1 FastEthernet (C1700-MB-1FE). No expansion Ethernet.
    # We include an entry so lookup never falls to fallback, but max_slots=0.
    "c1700": {"module": "NM-1FE-TX", "ports_per_module": 1, "first_configurable": 1, "max_slots": 0},

    # c3600 alias: GNS3 uses platform="c3600" for all 3620/3640/3660 chassis.
    # Map to the same spec as c3660 (most capable) so hardware injection
    # doesn't fall through to the fallback when it sees platform="c3600".
    "c3600": {"module": "NM-4E",     "ports_per_module": 4, "first_configurable": 1, "max_slots": 6},
}

DYNAMIPS_FALLBACK: Dict[str, Any] = {
    "module": "PA-8E",
    "ports_per_module": 8,
    "first_configurable": 1,
    "max_slots": 4,
}

# ---------------------------------------------------------------------------
# Dynamips Serial expansion modules
# ---------------------------------------------------------------------------
DYNAMIPS_SERIAL_MODULES: Dict[str, Dict[str, Any]] = {
    "c7200":  {"module": "PA-4T+",  "ports_per_module": 4, "first_configurable": 1, "max_slots": 6},
    "c3745":  {"module": "NM-4T",   "ports_per_module": 4, "first_configurable": 1, "max_slots": 4},
    "c3725":  {"module": "NM-4T",   "ports_per_module": 4, "first_configurable": 1, "max_slots": 2},
    "c3660":  {"module": "NM-4T",   "ports_per_module": 4, "first_configurable": 1, "max_slots": 6},
    "c3640":  {"module": "NM-4T",   "ports_per_module": 4, "first_configurable": 0, "max_slots": 4},
    "c3620":  {"module": "NM-1T",   "ports_per_module": 1, "first_configurable": 0, "max_slots": 2},
    "c2691":  {"module": "NM-4T",   "ports_per_module": 4, "first_configurable": 1, "max_slots": 1},
    "c2600":  {"module": "NM-1T",   "ports_per_module": 1, "first_configurable": 1, "max_slots": 1},
    "c1700":  {"module": "NM-1T",   "ports_per_module": 1, "first_configurable": 1, "max_slots": 0},
    "c3600":  {"module": "NM-4T",   "ports_per_module": 4, "first_configurable": 1, "max_slots": 6},
}

DYNAMIPS_SERIAL_FALLBACK: Dict[str, Any] = {
    "module": "PA-4T+",
    "ports_per_module": 4,
    "first_configurable": 1,
    "max_slots": 4,
}

# ---------------------------------------------------------------------------
# Built-in (motherboard) Ethernet port counts per platform
# These ports are on adapter 0 and require no slot module.
# ---------------------------------------------------------------------------
DYNAMIPS_BUILTIN_PORTS: Dict[str, int] = {
    "c7200": 1,   # C7200-IO-FE in slot 0
    "c3745": 2,   # GT96100-FE in slot 0
    "c3725": 2,   # GT96100-FE in slot 0
    "c3660": 2,   # Leopard-2FE in slot 0
    "c3640": 0,   # no fixed slot 0
    "c3620": 0,   # no fixed slot 0
    "c2691": 2,   # GT96100-FE in slot 0
    "c2600": 1,   # CISCO2600-MB-1E/2FE depending on chassis; 1 is safe minimum
    "c1700": 1,   # C1700-MB-1FE
    "c3600": 2,   # alias — c3660 is most capable (Leopard-2FE = 2 ports)
}
DYNAMIPS_BUILTIN_DEFAULT = 1

DYNAMIPS_BUILTIN_SERIAL_PORTS: Dict[str, int] = {
    "c7200": 0, "c3745": 0, "c3725": 0, "c3660": 0, "c3640": 0,
    "c3620": 0, "c2691": 0, "c2600": 0, "c1700": 0, "c3600": 0,
}

# ---------------------------------------------------------------------------
# Module interface details (name → prefix + port count)
# Used for IOS interface name resolution.
# Corrected: C1700-MB-1ETH → C1700-MB-1FE  (official GNS3/Dynamips name)
# ---------------------------------------------------------------------------
DYNAMIPS_MODULE_INTERFACES: Dict[str, Dict[str, Any]] = {
    "PA-8E":          {"prefix": "Ethernet",        "count": 8},
    "PA-4E":          {"prefix": "Ethernet",        "count": 4},
    "PA-FE-TX":       {"prefix": "FastEthernet",    "count": 1},
    "PA-2FE-TX":      {"prefix": "FastEthernet",    "count": 2},
    "PA-GE":          {"prefix": "GigabitEthernet", "count": 1},
    "NM-4E":          {"prefix": "Ethernet",        "count": 4},
    "NM-1E":          {"prefix": "Ethernet",        "count": 1},
    "NM-1FE-TX":      {"prefix": "FastEthernet",    "count": 1},
    "NM-16ESW":       {"prefix": "FastEthernet",    "count": 16},
    "GT96100-FE":     {"prefix": "FastEthernet",    "count": 2},
    "Leopard-2FE":    {"prefix": "FastEthernet",    "count": 2},
    # C7200 I/O controllers (slot 0 only)
    "C7200-IO-FE":    {"prefix": "FastEthernet",    "count": 1},
    "C7200-IO-2FE":   {"prefix": "FastEthernet",    "count": 2},
    "C7200-IO-GE-E":  {"prefix": "GigabitEthernet", "count": 1},
    # C1700 motherboard chip — correct name is C1700-MB-1FE
    "C1700-MB-1FE":   {"prefix": "FastEthernet",    "count": 1},
    # Serial modules
    "PA-4T+":         {"prefix": "Serial",          "count": 4},
    "PA-8T":          {"prefix": "Serial",          "count": 8},
    "NM-4T":          {"prefix": "Serial",          "count": 4},
    "NM-1T":          {"prefix": "Serial",          "count": 1},
}

# ---------------------------------------------------------------------------
# Built-in interface details per platform (for IOS name resolution)
# ---------------------------------------------------------------------------
DYNAMIPS_BUILTIN_INTERFACE_DETAILS: Dict[str, Dict[str, Any]] = {
    "c7200": {"prefix": "FastEthernet",  "count": 1},
    "c3745": {"prefix": "FastEthernet",  "count": 2},
    "c3725": {"prefix": "FastEthernet",  "count": 2},
    "c3660": {"prefix": "FastEthernet",  "count": 2},
    "c3640": {"prefix": None,            "count": 0},
    "c3620": {"prefix": None,            "count": 0},
    "c2691": {"prefix": "FastEthernet",  "count": 2},
    "c2600": {"prefix": "FastEthernet",  "count": 1},
    "c1700": {"prefix": "FastEthernet",  "count": 1},
    "c3600": {"prefix": "FastEthernet",  "count": 2},  # alias
}

IOU_PORTS_PER_ADAPTER   = 4
IOU_MAX_ADAPTERS        = 16
IOU_DEFAULT_ETH_ADAPTERS = 2
IOU_DEFAULT_SER_ADAPTERS = 2

SWITCH_HUB_DEFAULT_PORTS = 8

IMMUTABLE_PORT_COUNT: Dict[str, int] = {"vpcs": 1, "traceng": 1, "nat": 1}
IMMUTABLE_TYPES = frozenset(IMMUTABLE_PORT_COUNT.keys())
MAPPING_BASED_TYPES = frozenset(["frame_relay_switch", "atm_switch"])

L2_CONCENTRATOR_TYPES: frozenset = frozenset(["ethernet_switch", "ethernet_hub"])
L3_ROUTER_TYPES: frozenset = frozenset(["dynamips", "iou", "qemu", "docker", "virtualbox", "vmware"])
NO_CONFIG_TYPES: frozenset = frozenset([
    "ethernet_switch", "ethernet_hub", "nat", "cloud", "frame_relay_switch", "atm_switch",
])