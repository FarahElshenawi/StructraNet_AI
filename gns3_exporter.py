"""
gns3_exporter.py — Structranet AI  ·  GNS3 Portable Project Exporter  (V4.1)

Converts final_topology.json → network.gns3project (a ZIP importable via
GNS3 GUI → File → Import portable project).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 GROUND TRUTH SOURCES (consulted for every field decision)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  GNS3 server source  gns3server/schemas/project.py
                      gns3server/schemas/node.py
                      gns3server/schemas/link.py
  GNS3 controller     gns3server/controller/import_project.py
                      gns3server/controller/topology.py
  GNS3 portable ZIP   Reverse-engineered from real GNS3 2.2 project exports
  GNS3 GUI            gns3-gui/gns3/modules/dynamips/settings.py
                      (authoritative ADAPTER_MATRIX for slot0 defaults)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 HARDWARE GROUND TRUTH (from gns3-gui/settings.py ADAPTER_MATRIX)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  c3745 slot0 = GT96100-FE  (2 FastEthernet — NOT Leopard-2FE)
  c3725 slot0 = GT96100-FE  (2 FastEthernet)
  c3660 slot0 = Leopard-2FE (2 FastEthernet — fixed motherboard chip)
  c3640 slot0 = configurable NM  (no fixed built-in)
  c3620 slot0 = configurable NM  (no fixed built-in)
  c7200 slot0 = IO controller (C7200-IO-FE etc.), PA-* in slots 1-6

  IOU nodes require a unique integer application_id per node per project.
  Source: gns3server/compute/iou/iou_vm.py — application_id is always
  serialised in the node info dict and must be unique across all IOU nodes
  sharing the same compute to avoid MAC address collisions.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import argparse
import json
import logging
import os
import re
import sys
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from constants.gns3 import (
    CONSOLE_TYPE,
    DEFAULT_ROLE_PRIORITY,
    FILE_CONFIG_TRIPLETS,
    GNS3_REVISION,
    GNS3_VERSION,
    LABEL_STYLE,
    ROLE_PRIORITY,
    SCENE_HEIGHT,
    SCENE_WIDTH,
    SYMBOL,
)

logger = logging.getLogger("gns3_exporter")

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

def _is_uuid(s: str) -> bool:
    return bool(s and _UUID_RE.match(s))


# ═══════════════════════════════════════════════════════════════════════════════
#  Visual defaults (GNS3 GUI display)
# ═══════════════════════════════════════════════════════════════════════════════

_NODE_DIMENSIONS: Dict[str, Tuple[int, int]] = {
    "dynamips":           (56, 40),
    "iou":                (56, 40),
    "vpcs":               (34, 32),
    "traceng":            (34, 32),
    "cloud":              (95, 65),
    "nat":                (95, 65),
}
_DEFAULT_NODE_SIZE = (65, 65)

_LABEL_OFFSET: Dict[str, Tuple[int, int]] = {
    "dynamips":        (-17, -25),
    "iou":             (-17, -25),
    "vpcs":            (-8,  -22),
    "traceng":         (-8,  -22),
}
_DEFAULT_LABEL_OFFSET = (-10, -25)

_APPLIANCE_TYPES = frozenset(
    ["dynamips", "iou", "qemu", "docker", "virtualbox", "vmware"]
)
_BUILTIN_TYPES = frozenset([
    "vpcs", "ethernet_switch", "ethernet_hub", "cloud", "nat",
    "traceng", "frame_relay_switch", "atm_switch",
])


# ═══════════════════════════════════════════════════════════════════════════════
#  Dynamips platform tables
#
#  FIX (Bug 2 / Hardware): These tables were previously wrong for c3660 and c3745.
#  Corrected values sourced from gns3-gui/gns3/modules/dynamips/settings.py
#  ADAPTER_MATRIX (the single authoritative source for GNS3 slot defaults):
#
#    ADAPTER_MATRIX["c3600"]["3660"] = {0: "Leopard-2FE"}  → c3660 slot0=Leopard-2FE
#    ADAPTER_MATRIX["c3745"][""]    = {0: "GT96100-FE"}    → c3745 slot0=GT96100-FE
#    ADAPTER_MATRIX["c3725"][""]    = {0: "GT96100-FE"}    → c3725 slot0=GT96100-FE
#
#  The previous version had Leopard-2FE in c3745 (wrong) and count=0 for c3660 (wrong).
# ═══════════════════════════════════════════════════════════════════════════════

# Built-in Ethernet interface info per platform.
# "count" = number of ports that slot0's fixed module provides.
_DYN_BUILTIN: Dict[str, Dict[str, Any]] = {
    "c7200": {"prefix": "FastEthernet",  "count": 1},   # C7200-IO-FE in slot0
    # FIX: c3745 slot0 = GT96100-FE (2 FE) — was wrongly "Leopard-2FE" before
    "c3745": {"prefix": "FastEthernet",  "count": 2},   # GT96100-FE in slot0
    "c3725": {"prefix": "FastEthernet",  "count": 2},   # GT96100-FE in slot0
    # FIX: c3660 slot0 = Leopard-2FE (2 FE) — was wrongly count=0 before
    "c3660": {"prefix": "FastEthernet",  "count": 2},   # Leopard-2FE in slot0
    "c3640": {"prefix": None,            "count": 0},   # NO fixed slot0
    "c3620": {"prefix": None,            "count": 0},   # NO fixed slot0
    "c2691": {"prefix": "FastEthernet",  "count": 2},   # GT96100-FE in slot0
    "c2600": {"prefix": "FastEthernet",  "count": 1},   # built-in WIC
    "c1700": {"prefix": "FastEthernet",  "count": 1},   # C1700-MB-1ETH
}

# Module → interface prefix + port count
_DYN_MODULE: Dict[str, Dict[str, Any]] = {
    "PA-8E":      {"prefix": "Ethernet",         "count": 8},
    "PA-4E":      {"prefix": "Ethernet",         "count": 4},
    "PA-FE-TX":   {"prefix": "FastEthernet",     "count": 1},
    "PA-2FE-TX":  {"prefix": "FastEthernet",     "count": 2},
    "PA-GE":      {"prefix": "GigabitEthernet",  "count": 1},
    "NM-4E":      {"prefix": "Ethernet",         "count": 4},
    "NM-1E":      {"prefix": "Ethernet",         "count": 1},
    "NM-1FE-TX":  {"prefix": "FastEthernet",     "count": 1},
    "NM-16ESW":   {"prefix": "FastEthernet",     "count": 16},
    # FIX: GT96100-FE is c3725/c3745/c2691's slot0 chip (2 ports)
    "GT96100-FE": {"prefix": "FastEthernet",     "count": 2},
    # FIX: Leopard-2FE is c3660's slot0 chip (2 ports)
    "Leopard-2FE":{"prefix": "FastEthernet",     "count": 2},
    "C7200-IO-FE":  {"prefix": "FastEthernet",   "count": 1},
    "C7200-IO-2FE": {"prefix": "FastEthernet",   "count": 2},
    "C7200-IO-GE-E":{"prefix": "GigabitEthernet","count": 1},
    "PA-4T+":     {"prefix": "Serial",           "count": 4},
    "PA-8T":      {"prefix": "Serial",           "count": 8},
    "NM-4T":      {"prefix": "Serial",           "count": 4},
    "NM-1T":      {"prefix": "Serial",           "count": 1},
}

# Default hardware properties injected when missing.
# FIX: c3745 slot0 corrected to GT96100-FE (was Leopard-2FE — wrong).
# FIX: c3660 slot0 corrected to Leopard-2FE (was absent — wrong).
# Source: gns3-gui/gns3/modules/dynamips/settings.py ADAPTER_MATRIX.
_DYN_HW_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "c7200": {"ram": 512,  "slot0": "C7200-IO-FE",  "default_nm": "PA-8E",    "max_slots": 6},
    # c3745: slot0 = GT96100-FE (motherboard FastEthernet chip, 2 ports)
    "c3745": {"ram": 256,  "slot0": "GT96100-FE",   "default_nm": "NM-4E",    "max_slots": 4},
    "c3725": {"ram": 256,  "slot0": "GT96100-FE",   "default_nm": "NM-4E",    "max_slots": 2},
    # c3660: slot0 = Leopard-2FE (fixed motherboard chip, 2 FastEthernet ports)
    "c3660": {"ram": 256,  "slot0": "Leopard-2FE",  "default_nm": "NM-4E",    "max_slots": 6},
    # c3640/c3620: no fixed slot0 — all slots are user NM modules
    "c3640": {"ram": 256,                            "default_nm": "NM-4E",    "max_slots": 4},
    "c3620": {"ram": 256,                            "default_nm": "NM-4E",    "max_slots": 2},
    "c2691": {"ram": 256,  "slot0": "GT96100-FE",   "default_nm": "NM-4E",    "max_slots": 1},
    "c2600": {"ram": 128,  "slot0": "NM-1FE-TX",    "default_nm": "NM-1E",    "max_slots": 1},
    "c1700": {"ram": 128,  "slot0": "NM-1FE-TX",    "default_nm": "NM-1E",    "max_slots": 1},
}

_NODE_TYPE_DIR: Dict[str, str] = {
    "dynamips":   "dynamips",
    "iou":        "iou",
    "qemu":       "qemu",
    "docker":     "docker",
    "vpcs":       "vpcs",
    "virtualbox": "virtualbox",
    "vmware":     "vmware",
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Input normalisation
# ═══════════════════════════════════════════════════════════════════════════════

def _normalise_input(data: dict) -> Tuple[str, List[dict], List[dict]]:
    name = data.get("name", "Imported_Network")

    topo = data.get("topology")
    if isinstance(topo, dict):
        nodes = topo.get("nodes", [])
        links = topo.get("links", [])
    else:
        nodes = data.get("nodes", [])
        links = data.get("links", [])

    if not nodes:
        raise ValueError(
            "No nodes found. Expected 'topology.nodes' or top-level 'nodes'."
        )

    return name, list(nodes), list(links)


# ═══════════════════════════════════════════════════════════════════════════════
#  UUID assignment
# ═══════════════════════════════════════════════════════════════════════════════

def _assign_uuids(
    project_name: str,
    nodes: List[dict],
) -> Tuple[str, Dict[str, str]]:
    project_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"structranet-{project_name}"))
    node_uuid_map: Dict[str, str] = {}

    for n in nodes:
        nid = n.get("node_id", "")
        if _is_uuid(nid):
            node_uuid_map[nid] = nid
        else:
            node_uuid_map[nid] = str(uuid.uuid5(uuid.UUID(project_uuid), nid))

    return project_uuid, node_uuid_map


# ═══════════════════════════════════════════════════════════════════════════════
#  Canvas layout
# ═══════════════════════════════════════════════════════════════════════════════

def _grid_positions(nodes: List[dict]) -> Dict[str, Tuple[int, int]]:
    existing: Dict[str, Tuple[int, int]] = {}
    needs_layout: List[dict] = []

    for n in nodes:
        nid = n.get("node_id", "")
        if "x" in n and "y" in n:
            try:
                existing[nid] = (int(n["x"]), int(n["y"]))
                continue
            except (TypeError, ValueError):
                pass
        needs_layout.append(n)

    if not needs_layout:
        return existing

    scored = sorted(
        needs_layout,
        key=lambda n: (
            ROLE_PRIORITY.get(n.get("node_type", ""), DEFAULT_ROLE_PRIORITY),
            n.get("node_id", ""),
        ),
    )

    positions: Dict[str, Tuple[int, int]] = dict(existing)
    col, row, last_priority = 0, 0, None

    for n in scored:
        nid = n.get("node_id", "")
        priority = ROLE_PRIORITY.get(n.get("node_type", ""), DEFAULT_ROLE_PRIORITY)

        if last_priority is not None and priority != last_priority:
            row += 1
            col = 0
        last_priority = priority

        positions[nid] = (col * 200 - 400, row * 150 - 200)
        col += 1
        if col >= 5:
            col = 0
            row += 1

    return positions


# ═══════════════════════════════════════════════════════════════════════════════
#  Port name resolution
# ═══════════════════════════════════════════════════════════════════════════════

def _port_name(node: dict, adapter: int, port: int) -> str:
    ntype    = node.get("node_type", "")
    props    = node.get("properties", {})
    template = str(node.get("template_name", "")).lower()

    if ntype == "dynamips":
        platform = str(props.get("platform", "")).lower() or template
        if adapter == 0:
            bi = _DYN_BUILTIN.get(platform, {"prefix": "FastEthernet", "count": 1})
            pfx = bi.get("prefix") or "FastEthernet"
            if bi.get("count", 0) == 0:
                # c3640/c3620: slot0 is a user NM module, not a fixed chip
                mod = props.get("slot0", "")
                if mod and mod in _DYN_MODULE:
                    pfx = _DYN_MODULE[mod]["prefix"]
                else:
                    pfx = "FastEthernet"
            return f"{pfx}0/{port}"
        mod_name = props.get(f"slot{adapter}", "")
        if mod_name and mod_name in _DYN_MODULE:
            pfx = _DYN_MODULE[mod_name]["prefix"]
            return f"{pfx}{adapter}/{port}"
        return f"Ethernet{adapter}/{port}"

    if ntype == "iou":
        eth_adapters = int(props.get("ethernet_adapters", 2))
        if adapter < eth_adapters:
            return f"Ethernet{adapter}/{port}"
        else:
            local_ser = adapter - eth_adapters
            return f"Serial{local_ser}/{port}"

    if ntype in ("qemu", "docker", "virtualbox", "vmware"):
        return f"eth{adapter}"

    if ntype in ("vpcs", "traceng"):
        return "eth0"

    if ntype == "ethernet_switch":
        return f"Ethernet{port}"

    if ntype == "ethernet_hub":
        return f"Ethernet{port}"

    if ntype == "nat":
        return "nat0"

    if ntype == "cloud":
        return f"Cloud{port}"

    if ntype == "frame_relay_switch":
        return f"Serial{port}"

    if ntype == "atm_switch":
        return f"ATM{port}"

    return f"Ethernet{adapter}/{port}"


def _short_name(long_name: str) -> str:
    return (
        long_name
        .replace("GigabitEthernet", "g")
        .replace("FastEthernet",    "f")
        .replace("Ethernet",        "e")
        .replace("Serial",          "s")
        .lower()
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Ports array builder
# ═══════════════════════════════════════════════════════════════════════════════

def _build_ports(node: dict, links: List[dict]) -> List[dict]:
    nid = node.get("node_id", "")
    seen: set = set()
    ports: List[dict] = []

    for link in links:
        for ep in link.get("nodes", []):
            if ep.get("node_id") != nid:
                continue
            adapter = ep.get("adapter_number", 0)
            port    = ep.get("port_number",    0)
            key     = (adapter, port)
            if key in seen:
                continue
            seen.add(key)

            long  = _port_name(node, adapter, port)
            short = _short_name(long)
            ltype = link.get("link_type", "ethernet")

            ports.append({
                "adapter_number": adapter,
                "port_number":    port,
                "name":           long,
                "short_name":     short,
                "link_type":      ltype,
                "data_link_types": (
                    {"Ethernet": "DLT_EN10MB"} if ltype == "ethernet"
                    else {"PPP": "DLT_PPP_SERIAL"}
                ),
            })

    ports.sort(key=lambda p: (p["adapter_number"], p["port_number"]))
    return ports


# ═══════════════════════════════════════════════════════════════════════════════
#  Config file extraction  (ZIP content)
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_configs(node: dict, node_uuid: str) -> Dict[str, str]:
    ntype    = node.get("node_type", "")
    props    = node.get("properties", {})
    type_dir = _NODE_TYPE_DIR.get(ntype, ntype)
    result: Dict[str, str] = {}

    for prop_key, target_type, subpath in FILE_CONFIG_TRIPLETS:
        if target_type != ntype:
            continue
        value = props.get(prop_key)
        if value and isinstance(value, str):
            zip_path = f"project-files/{type_dir}/{node_uuid}/{subpath}"
            result[zip_path] = value

    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  Properties cleaner
# ═══════════════════════════════════════════════════════════════════════════════

_PIPELINE_ONLY_KEYS = frozenset([])

def _clean_properties(node: dict) -> dict:
    return {
        k: v
        for k, v in node.get("properties", {}).items()
        if k not in _PIPELINE_ONLY_KEYS
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  Hardware property injection
# ═══════════════════════════════════════════════════════════════════════════════

def _detect_dynamips_platform(props: dict, template: str) -> str:
    existing = str(props.get("platform", "")).lower().strip()
    if existing and existing in _DYN_HW_DEFAULTS:
        return existing

    name_lower = str(template).lower()
    for platform in ("c7200", "c3745", "c3725", "c3660", "c3640", "c3620",
                     "c2691", "c2600", "c1700"):
        if platform in name_lower or platform[1:] in name_lower:
            return platform

    logger.warning(
        "Cannot detect Dynamips platform from template '%s' — defaulting to c3745",
        template,
    )
    return "c3745"


def _inject_dynamips_properties(
    node: dict, props: dict, template: str, links: List[dict]
) -> None:
    platform = _detect_dynamips_platform(props, template)
    hw = _DYN_HW_DEFAULTS.get(platform, _DYN_HW_DEFAULTS["c3745"])

    props.setdefault("platform", platform)
    props.setdefault("ram", hw["ram"])

    if "image" not in props:
        placeholder = f"{platform}-adventerprisek9-mz.124-25d.bin"
        props["image"] = placeholder
        logger.warning(
            "Node '%s': no 'image' property — using placeholder '%s'.",
            node.get("name", "?"), placeholder,
        )

    # slot0: only for platforms with a fixed slot0 module.
    # c3640/c3620 have no fixed slot0, so "slot0" key is absent from hw defaults.
    if "slot0" not in props and "slot0" in hw:
        props["slot0"] = hw["slot0"]

    nid = node.get("node_id", "")
    max_adapter = 0
    serial_adapter_set: set = set()

    for link in links:
        for ep in link.get("nodes", []):
            if ep.get("node_id") != nid:
                continue
            adapter = ep.get("adapter_number", 0)
            max_adapter = max(max_adapter, adapter)
            if link.get("link_type") == "serial":
                serial_adapter_set.add(adapter)

    default_nm = hw["default_nm"]
    serial_nm  = "NM-4T" if default_nm.startswith("NM") else "PA-4T+"
    max_slots  = hw["max_slots"]

    for slot_num in range(1, min(max_adapter + 1, max_slots + 1)):
        slot_key = f"slot{slot_num}"
        if slot_key not in props:
            props[slot_key] = serial_nm if slot_num in serial_adapter_set else default_nm

    if "slot0" not in props:
        for link in links:
            for ep in link.get("nodes", []):
                if ep.get("node_id") == nid and ep.get("adapter_number", -1) == 0:
                    props["slot0"] = serial_nm if 0 in serial_adapter_set else default_nm
                    break


def _inject_iou_properties(
    node: dict, props: dict, template: str, links: List[dict]
) -> None:
    if "path" not in props:
        props["path"] = f"/opt/gns3/images/{template}.bin"
        logger.warning(
            "Node '%s': no 'path' property — using placeholder '%s'.",
            node.get("name", "?"), props["path"],
        )

    if "ethernet_adapters" not in props or "serial_adapters" not in props:
        nid = node.get("node_id", "")
        max_eth = -1
        max_ser = -1
        for link in links:
            for ep in link.get("nodes", []):
                if ep.get("node_id") != nid:
                    continue
                adapter = ep.get("adapter_number", 0)
                if link.get("link_type") == "serial":
                    max_ser = max(max_ser, adapter)
                else:
                    max_eth = max(max_eth, adapter)

        eth = int(props.get("ethernet_adapters", max(max_eth + 1, 2) if max_eth >= 0 else 2))
        props.setdefault("ethernet_adapters", eth)
        if "serial_adapters" not in props:
            if max_ser >= 0:
                ser_count = max(max_ser - eth + 1, 1)
                props["serial_adapters"] = ser_count
            else:
                props["serial_adapters"] = 0

    props.setdefault("ram", 256)


def _inject_qemu_properties(props: dict, template: str) -> None:
    if "hda_disk_image" not in props:
        props["hda_disk_image"] = f"{template}.qcow2"
    props.setdefault("ram", 512)
    props.setdefault("adapters", 8)


def _inject_docker_properties(props: dict, template: str) -> None:
    props.setdefault("image", template)


def _inject_hardware_properties(node: dict, links: List[dict]) -> None:
    ntype    = node.get("node_type", "")
    template = node.get("template_name", "")
    props    = node.setdefault("properties", {})

    if ntype == "dynamips":
        _inject_dynamips_properties(node, props, template, links)
    elif ntype == "iou":
        _inject_iou_properties(node, props, template, links)
    elif ntype == "qemu":
        _inject_qemu_properties(props, template)
    elif ntype == "docker":
        _inject_docker_properties(props, template)


# ═══════════════════════════════════════════════════════════════════════════════
#  Main converter
# ═══════════════════════════════════════════════════════════════════════════════

def convert(
    input_data: dict,
    output_path: str,
    name_override: str = None,
    image_map: Dict[str, str] = None,
) -> str:
    image_map = image_map or {}

    project_name, nodes_in, links_in = _normalise_input(input_data)
    if name_override:
        project_name = name_override

    project_uuid, node_uuid_map = _assign_uuids(project_name, nodes_in)

    positions = _grid_positions(nodes_in)

    node_lookup: Dict[str, dict] = {n.get("node_id", ""): n for n in nodes_in}

    gns3_nodes: List[dict] = []
    all_zip_configs: Dict[str, str] = {}

    # FIX (Bug 2): Track IOU application_id counter so every IOU node gets a
    # unique integer.  Source: gns3server/compute/iou/iou_vm.py — application_id
    # must be unique across all IOU nodes sharing the same compute to avoid
    # MAC address collisions.  We start at 1 and increment per IOU node.
    iou_application_id_counter = 1

    for n in nodes_in:
        nid   = n.get("node_id", "")
        ntype = n.get("node_type", "")
        nuuid = node_uuid_map[nid]
        x, y  = positions.get(nid, (0, 0))
        w, h  = _NODE_DIMENSIONS.get(ntype, _DEFAULT_NODE_SIZE)
        lx, ly = _LABEL_OFFSET.get(ntype, _DEFAULT_LABEL_OFFSET)

        if ntype == "dynamips" and n.get("template_name") in image_map:
            n.setdefault("properties", {})["image"] = image_map[n["template_name"]]

        _inject_hardware_properties(n, links_in)

        # FIX (Bug 2): Assign unique application_id to every IOU node.
        if ntype == "iou":
            props = n.setdefault("properties", {})
            if "application_id" not in props:
                props["application_id"] = iou_application_id_counter
            iou_application_id_counter += 1

        all_zip_configs.update(_extract_configs(n, nuuid))

        template_name = n.get("template_name", "")
        template_id: Optional[str] = None
        if ntype in _APPLIANCE_TYPES and template_name:
            template_id = str(
                uuid.uuid5(uuid.NAMESPACE_DNS, f"gns3-template-{template_name}")
            )

        if ntype == "iou":
            port_name_format  = "Ethernet{segment0}/{port0}"
            port_segment_size = 4
        else:
            port_name_format  = n.get("port_name_format", "Ethernet{0}")
            port_segment_size = 0

        label = n.get("label") if isinstance(n.get("label"), dict) else {}
        node_obj: dict = {
            "compute_id":       n.get("compute_id", "local"),
            "node_id":          nuuid,
            "node_type":        ntype,
            "name":             n.get("name", nid),
            "console":          None,
            "console_type":     CONSOLE_TYPE.get(ntype),
            "x":                x,
            "y":                y,
            "z":                n.get("z", 1),
            "width":            w,
            "height":           h,
            "symbol":           SYMBOL.get(ntype, ":/symbols/computer.svg"),
            "label": {
                "text":     n.get("name", nid),
                "x":        label.get("x", lx),
                "y":        label.get("y", ly),
                "rotation": 0,
                "style":    LABEL_STYLE,
            },
            "properties":       _clean_properties(n),
            "port_name_format": port_name_format,
            "port_segment_size": port_segment_size,
            "first_port_name":  n.get("first_port_name"),
            "ports":            _build_ports(n, links_in),
        }

        if ntype in _APPLIANCE_TYPES:
            node_obj["template_id"] = template_id

        gns3_nodes.append(node_obj)

    gns3_links: List[dict] = []

    for i, link in enumerate(links_in):
        eps = link.get("nodes", [])
        if len(eps) < 2:
            logger.warning("Link %d has fewer than 2 endpoints — skipped", i)
            continue

        ep0, ep1 = eps[0], eps[1]
        orig_id0 = ep0.get("node_id", "")
        orig_id1 = ep1.get("node_id", "")

        uuid0 = node_uuid_map.get(orig_id0)
        uuid1 = node_uuid_map.get(orig_id1)

        if not uuid0:
            logger.warning("Link %d: unknown node_id '%s' — skipped", i, orig_id0)
            continue
        if not uuid1:
            logger.warning("Link %d: unknown node_id '%s' — skipped", i, orig_id1)
            continue

        ltype     = link.get("link_type", "ethernet")
        link_uuid = str(uuid.uuid5(uuid.UUID(project_uuid), f"link-{i}"))

        node0 = node_lookup.get(orig_id0, {})
        node1 = node_lookup.get(orig_id1, {})
        ad0, pt0 = ep0.get("adapter_number", 0), ep0.get("port_number", 0)
        ad1, pt1 = ep1.get("adapter_number", 0), ep1.get("port_number", 0)
        pname0 = _port_name(node0, ad0, pt0)
        pname1 = _port_name(node1, ad1, pt1)

        gns3_links.append({
            "link_id":   link_uuid,
            "link_type": ltype,
            "nodes": [
                {
                    "node_id":        uuid0,
                    "adapter_number": ad0,
                    "port_number":    pt0,
                    "label": {
                        "text":     _short_name(pname0),
                        "x":        0,
                        "y":        0,
                        "rotation": 0,
                        "style":    LABEL_STYLE,
                    },
                },
                {
                    "node_id":        uuid1,
                    "adapter_number": ad1,
                    "port_number":    pt1,
                    "label": {
                        "text":     _short_name(pname1),
                        "x":        0,
                        "y":        0,
                        "rotation": 0,
                        "style":    LABEL_STYLE,
                    },
                },
            ],
        })

    project_gns3 = {
        "name":         project_name,
        "project_id":   project_uuid,
        "revision":     GNS3_REVISION,
        "type":         "topology",
        "version":      GNS3_VERSION,
        "auto_start":   False,
        "auto_close":   True,
        "auto_open":    False,
        "scene_width":  SCENE_WIDTH,
        "scene_height": SCENE_HEIGHT,
        "topology": {
            "nodes":    gns3_nodes,
            "links":    gns3_links,
            "drawings": [],
            "computes": [],
        },
    }

    if not str(output_path).endswith(".gns3project"):
        output_path = str(output_path) + ".gns3project"

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(
        output_path, "w",
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=True,
    ) as zf:
        zf.writestr(
            "project.gns3",
            json.dumps(project_gns3, indent=2, ensure_ascii=False),
        )
        for zip_path, content in all_zip_configs.items():
            zf.writestr(zip_path, content)
            logger.info("Packed config: %s (%d bytes)", zip_path, len(content))

    abs_path = os.path.abspath(output_path)

    print(f"[OK] '{project_name}'  ->  {abs_path}")
    print(f"     nodes:   {len(gns3_nodes)}")
    print(f"     links:   {len(gns3_links)}")
    print(f"     configs: {len(all_zip_configs)} file(s) packed")
    print()
    print("Import: GNS3 GUI -> File -> Import portable project")

    return abs_path


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    parser = argparse.ArgumentParser(
        description="Convert any network topology JSON → GNS3 .gns3project",
    )
    parser.add_argument("input",  help="Input topology JSON file")
    parser.add_argument("output", nargs="?", default=None,
                        help="Output .gns3project path")
    parser.add_argument("--name",   default=None, help="Override the project name")
    parser.add_argument("--images", default=None,
                        help="Template→image map: 'c3745=image.bin,c7200=other.bin'")
    parser.add_argument("--debug",  action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    image_map: Dict[str, str] = {}
    if args.images:
        for entry in args.images.split(","):
            entry = entry.strip()
            if "=" in entry:
                k, v = entry.split("=", 1)
                image_map[k.strip()] = v.strip()

    try:
        with open(args.input, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"[ERR] File not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[ERR] Invalid JSON in {args.input}: {e}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        out_path = args.output
    else:
        raw_name = (
            args.name
            or data.get("name")
            or (data.get("topology") or {}).get("name")
            or "network"
        )
        safe = re.sub(r"[^\w\- ]", "_", raw_name).replace(" ", "_")
        out_path = str(Path(args.input).parent / f"{safe}.gns3project")

    try:
        convert(data, out_path, name_override=args.name, image_map=image_map)
    except Exception as e:
        print(f"[ERR] {e}", file=sys.stderr)
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()