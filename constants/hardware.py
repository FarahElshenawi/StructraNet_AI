from typing import Any, Dict

MAX_ADAPTERS: Dict[str, int] = {
    "qemu": 275,
    "docker": 99,
    "virtualbox": 8,
    "vmware": 10,
}

DYNAMIPS_SLOT_MODULES: Dict[str, Dict[str, Any]] = {
    "c7200": {"module": "PA-8E", "ports_per_module": 8, "first_configurable": 1, "max_slots": 6},
    "c3745": {"module": "NM-4E", "ports_per_module": 4, "first_configurable": 1, "max_slots": 4},
    "c3725": {"module": "NM-4E", "ports_per_module": 4, "first_configurable": 1, "max_slots": 2},
    "c3660": {"module": "NM-4E", "ports_per_module": 4, "first_configurable": 1, "max_slots": 6},
    "c3640": {"module": "NM-4E", "ports_per_module": 4, "first_configurable": 1, "max_slots": 4},
    "c3620": {"module": "NM-4E", "ports_per_module": 4, "first_configurable": 1, "max_slots": 2},
    "c2691": {"module": "NM-4E", "ports_per_module": 4, "first_configurable": 1, "max_slots": 1},
    "c2600": {"module": "NM-1E", "ports_per_module": 1, "first_configurable": 1, "max_slots": 1},
    "c1700": {"module": "NM-1E", "ports_per_module": 1, "first_configurable": 1, "max_slots": 1},
}

DYNAMIPS_FALLBACK: Dict[str, Any] = {
    "module": "PA-8E",
    "ports_per_module": 8,
    "first_configurable": 1,
    "max_slots": 4,
}

DYNAMIPS_SERIAL_MODULES: Dict[str, Dict[str, Any]] = {
    "c7200": {"module": "PA-4T+", "ports_per_module": 4, "first_configurable": 1, "max_slots": 6},
    "c3745": {"module": "NM-4T", "ports_per_module": 4, "first_configurable": 1, "max_slots": 4},
    "c3725": {"module": "NM-4T", "ports_per_module": 4, "first_configurable": 1, "max_slots": 2},
    "c3660": {"module": "NM-4T", "ports_per_module": 4, "first_configurable": 1, "max_slots": 6},
    "c3640": {"module": "NM-4T", "ports_per_module": 4, "first_configurable": 1, "max_slots": 4},
    "c3620": {"module": "NM-1T", "ports_per_module": 1, "first_configurable": 1, "max_slots": 2},
    "c2691": {"module": "NM-4T", "ports_per_module": 4, "first_configurable": 1, "max_slots": 1},
    "c2600": {"module": "NM-1T", "ports_per_module": 1, "first_configurable": 1, "max_slots": 1},
    "c1700": {"module": "NM-1T", "ports_per_module": 1, "first_configurable": 1, "max_slots": 1},
}

DYNAMIPS_SERIAL_FALLBACK: Dict[str, Any] = {
    "module": "PA-4T+",
    "ports_per_module": 4,
    "first_configurable": 1,
    "max_slots": 4,
}

DYNAMIPS_BUILTIN_PORTS: Dict[str, int] = {
    "c7200": 1,
    "c3745": 2,
    "c3725": 2,
    "c3660": 2,
    "c3640": 0,
    "c3620": 0,
    "c2691": 2,
    "c2600": 1,
    "c1700": 1,
}
DYNAMIPS_BUILTIN_DEFAULT = 1

DYNAMIPS_BUILTIN_SERIAL_PORTS: Dict[str, int] = {
    "c7200": 0, "c3745": 0, "c3725": 0, "c3660": 0, "c3640": 0,
    "c3620": 0, "c2691": 0, "c2600": 0, "c1700": 0,
}

DYNAMIPS_MODULE_INTERFACES: Dict[str, Dict[str, Any]] = {
    "PA-8E": {"prefix": "Ethernet", "count": 8},
    "PA-4E": {"prefix": "Ethernet", "count": 4},
    "PA-FE-TX": {"prefix": "FastEthernet", "count": 1},
    "PA-2FE-TX": {"prefix": "FastEthernet", "count": 2},
    "PA-GE": {"prefix": "GigabitEthernet", "count": 1},
    "NM-4E": {"prefix": "Ethernet", "count": 4},
    "NM-1E": {"prefix": "Ethernet", "count": 1},
    "NM-1FE-TX": {"prefix": "FastEthernet", "count": 1},
    "NM-16ESW": {"prefix": "FastEthernet", "count": 16},
    "GT96100-FE": {"prefix": "FastEthernet", "count": 2},
    "PA-4T+": {"prefix": "Serial", "count": 4},
    "PA-8T": {"prefix": "Serial", "count": 8},
    "NM-4T": {"prefix": "Serial", "count": 4},
    "NM-1T": {"prefix": "Serial", "count": 1},
}

DYNAMIPS_BUILTIN_INTERFACE_DETAILS: Dict[str, Dict[str, Any]] = {
    "c7200": {"prefix": "FastEthernet", "count": 1},
    "c3745": {"prefix": "FastEthernet", "count": 2},
    "c3725": {"prefix": "FastEthernet", "count": 2},
    "c3660": {"prefix": "FastEthernet", "count": 2},
    "c3640": {"prefix": None, "count": 0},
    "c3620": {"prefix": None, "count": 0},
    "c2691": {"prefix": "FastEthernet", "count": 2},
    "c2600": {"prefix": "FastEthernet", "count": 1},
    "c1700": {"prefix": "FastEthernet", "count": 1},
}

IOU_PORTS_PER_ADAPTER = 4
IOU_MAX_ADAPTERS = 16
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

