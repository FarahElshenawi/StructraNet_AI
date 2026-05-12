"""
gns3_constants.py — Shared GNS3 Constants for Structranet AI

Centralises all GNS3-format constants that are needed by both the live
REST API assembler (assembler.py) and the new offline config extractor
/ project enricher.  Previously these were scattered across assembler.py
and gns3_exporter.py with subtle inconsistencies; this module is the
single source of truth.

Phase B — Part 1 deliverable.

Contents
~~~~~~~~
  GNS3 format version / revision
  File config path mapping  (software_key × node_type → filesystem path)
  Visual defaults           (symbols, sizes, console types, label style)
  Layout role priorities
  Port name format per node type
"""

from typing import Any, Dict, FrozenSet, List, Tuple


# ═══════════════════════════════════════════════════════════════════════════════
#  GNS3 File Format Constants
# ═══════════════════════════════════════════════════════════════════════════════
# Source: gns3server/schemas/project.py

GNS3_REVISION: int = 9          # current revision for GNS3 2.2.x
GNS3_VERSION: str = "2.2.0"     # minimum version that supports this revision
SCENE_WIDTH: int = 2000
SCENE_HEIGHT: int = 1000


# ═══════════════════════════════════════════════════════════════════════════════
#  Software Config → GNS3 Virtual Filesystem Path Mapping
# ═══════════════════════════════════════════════════════════════════════════════
#
# GNS3 strictly rejects startup_config_content, private_config_content,
# and startup_script from the properties PUT endpoint (400 Bad Request).
# They must be written either:
#   - via the Files API (live REST deployment), or
#   - as files inside the .gns3project ZIP (offline export).
#
# This mapping is used by BOTH the assembler and the offline exporter.
#
# Format: (software_config_key, node_type) → virtual_filesystem_path
#
# For live deployment (assembler):  path is appended to
#   POST /projects/{pid}/nodes/{nid}/files/{path}
#
# For offline export (.gns3project):  path becomes
#   files/<node_uuid>/<path>   inside the ZIP archive.

FILE_CONFIG_PATHS: Dict[Tuple[str, str], str] = {
    # ── IOS startup-config (dynamips, iou, qemu IOS images) ──
    ("startup_config_content", "dynamips"): "startup-config.cfg",
    ("startup_config_content", "iou"):      "startup-config.cfg",
    ("startup_config_content", "qemu"):     "startup-config.cfg",
    # ── IOS private-config (dynamips, iou) ──
    ("private_config_content", "dynamips"): "private-config.cfg",
    ("private_config_content", "iou"):      "private-config.cfg",
    # ── VPCS startup script ──
    ("startup_script", "vpcs"):             "startup.vpc",
}

# Alternative representation: flat list of (key, node_type, zip_subpath)
# Useful for the exporter which needs to iterate all combinations.
FILE_CONFIG_TRIPLETS: List[Tuple[str, str, str]] = [
    ("startup_config_content", "dynamips", "configs/startup-config.cfg"),
    ("startup_config_content", "iou",      "configs/startup-config.cfg"),
    ("startup_config_content", "qemu",     "configs/startup-config.cfg"),
    ("private_config_content", "dynamips", "configs/private-config.cfg"),
    ("private_config_content", "iou",      "configs/private-config.cfg"),
    ("startup_script",         "vpcs",     "startup.vpc"),
]

# Keys that must be extracted to files and removed from properties dict
# before sending to GNS3 (either via PUT or in the project.gns3 JSON).
SOFTWARE_CONFIG_KEYS: FrozenSet[str] = frozenset(
    k for k, _, _ in FILE_CONFIG_TRIPLETS
) | {"start_command", "environment"}


# ═══════════════════════════════════════════════════════════════════════════════
#  Node Visual Defaults
# ═══════════════════════════════════════════════════════════════════════════════
# Source: GNS3 built-in symbol library (gns3-server/resources/symbols/)

# Symbol SVG path per node type
SYMBOL: Dict[str, str] = {
    "dynamips":           ":/symbols/router.svg",
    "iou":                ":/symbols/router.svg",
    "qemu":               ":/symbols/router.svg",
    "docker":             ":/symbols/docker_guest.svg",
    "vpcs":               ":/symbols/vpcs_guest.svg",
    "traceng":            ":/symbols/traceng.svg",
    "ethernet_switch":    ":/symbols/ethernet_switch.svg",
    "ethernet_hub":       ":/symbols/hub.svg",
    "cloud":              ":/symbols/cloud.svg",
    "nat":                ":/symbols/nat.svg",
    "virtualbox":         ":/symbols/vbox_guest.svg",
    "vmware":             ":/symbols/vmware_guest.svg",
    "frame_relay_switch": ":/symbols/frame_relay_switch.svg",
    "atm_switch":         ":/symbols/atm_switch.svg",
}

# Default canvas dimensions per node type
NODE_SIZE: Dict[str, Tuple[int, int]] = {
    "dynamips":           (65, 65),
    "iou":                (65, 65),
    "qemu":               (65, 65),
    "docker":             (65, 65),
    "vpcs":               (65, 65),
    "traceng":            (65, 65),
    "ethernet_switch":    (65, 65),
    "ethernet_hub":       (65, 65),
    "cloud":              (95, 65),
    "nat":                (95, 65),
    "virtualbox":         (65, 65),
    "vmware":             (65, 65),
    "frame_relay_switch": (65, 65),
    "atm_switch":         (65, 65),
}

# Console type per node type
# GNS3 uses the string "none" (not JSON null) for built-in types
# that have no console.  Matches actual GNS3 portable project exports.
CONSOLE_TYPE: Dict[str, str] = {
    "dynamips":           "telnet",
    "iou":                "telnet",
    "qemu":               "telnet",
    "docker":             "telnet",
    "vpcs":               "telnet",
    "traceng":            "none",
    "ethernet_switch":    "none",
    "ethernet_hub":       "none",
    "cloud":              "none",
    "nat":                "none",
    "virtualbox":         "telnet",
    "vmware":             "telnet",
    "frame_relay_switch": "none",
    "atm_switch":         "none",
}

# Default label style for node labels and link endpoint labels.
# Matches what GNS3 produces in actual portable project exports.
LABEL_STYLE: str = (
    "font-family: TypeWriter;"
    "font-size: 10.0;"
    "font-weight: bold;"
    "fill: #000000;"
    "fill-opacity: 1.0;"
)


# ═══════════════════════════════════════════════════════════════════════════════
#  Canvas Layout — Role Priority
# ═══════════════════════════════════════════════════════════════════════════════
# Lower number = higher on canvas (routers central, switches above/below,
# end devices at periphery).
#
# Layout tiers:
#   0 — Cloud/NAT          (top of canvas — WAN edge)
#   1 — Routers            (centre — core/distribution layer)
#   2 — Switches/Hubs      (below routers — access layer)
#   3 — End devices/VPCS   (bottom — edge hosts)

ROLE_PRIORITY: Dict[str, int] = {
    "cloud": 0, "nat": 0,
    "dynamips": 1, "iou": 1, "qemu": 1, "virtualbox": 1, "vmware": 1,
    "ethernet_switch": 2, "ethernet_hub": 2,
    "frame_relay_switch": 2, "atm_switch": 2,
    "vpcs": 3, "traceng": 3, "docker": 3,
}
DEFAULT_ROLE_PRIORITY: int = 4  # unknown types placed at bottom


# ═══════════════════════════════════════════════════════════════════════════════
#  Port Name Format per Node Type
# ═══════════════════════════════════════════════════════════════════════════════
# The format string that GNS3 uses to generate port names.
# {0} = adapter_number, {1} = port_number (Python format)
#
# Source: gns3server/templates/ and GNS3 GUI appliance files.

PORT_NAME_FORMAT: Dict[str, str] = {
    "dynamips":           "FastEthernet{0}/{1}",
    "iou":                "Ethernet{0}/{1}",
    "qemu":               "eth{0}",
    "docker":             "eth{0}",
    "vpcs":               "Ethernet{0}",
    "traceng":            "Ethernet{0}",
    "ethernet_switch":    "Ethernet{0}",
    "ethernet_hub":       "Ethernet{0}",
    "virtualbox":         "eth{0}",
    "vmware":             "eth{0}",
    "cloud":              "Cloud{0}",
    "nat":                "nat{0}",
    "frame_relay_switch": "{0}",
    "atm_switch":         "{0}",
}

# Port segment size per node type (ports per adapter)
PORT_SEGMENT_SIZE: Dict[str, int] = {
    "dynamips": 1,
    "iou": 4,
    "qemu": 1,
    "docker": 1,
    "vpcs": 1,
    "traceng": 1,
    "ethernet_switch": 1,
    "ethernet_hub": 1,
    "virtualbox": 1,
    "vmware": 1,
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Layout Grid Constants
# ═══════════════════════════════════════════════════════════════════════════════

GRID_COLUMN_SPACING: int = 200    # pixels between columns
GRID_ROW_SPACING: int = 150       # pixels between rows
GRID_COLUMNS_PER_ROW: int = 5     # max nodes per row before wrapping
GRID_X_OFFSET: int = -400         # x offset for first column
GRID_Y_OFFSET: int = -200         # y offset for first row
