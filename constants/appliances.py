"""
constants/appliances.py — Default appliance catalog constants.

RAM defaults corrected to match GNS3 PLATFORMS_DEFAULT_RAM:
  c1700: 128 → 160 MB
  c2691: not in catalog but kept consistent in hw_config
  Cisco 7200 (c7200): 512 MB  ✓ unchanged
  Cisco 3745 (c3745): 256 MB  ✓ unchanged
"""
from typing import Any, Dict

APPLIANCE_CATALOG: Dict[str, Dict[str, Any]] = {
    "Cisco 7200": {
        "node_type": "dynamips",
        "platform": "c7200",
        "image": "c7200-adventerprisek9-mz.124-24.T5.image",
        "ram": 512,      # GNS3 default: 512 MB ✓
        "nvram": 512,
        "slot0": "C7200-IO-FE",   # I/O controller for c7200 (not a PA module)
        "console_type": "telnet",
        "port_name_format": "FastEthernet{0}/{1}",
        "port_segment_size": 1,
    },
    "Cisco 3745": {
        "node_type": "dynamips",
        "platform": "c3745",
        "image": "c3745-adventerprisek9-mz.124-25d.image",
        "ram": 256,      # GNS3 default: 256 MB ✓
        "nvram": 256,
        "slot0": "GT96100-FE",    # Fixed 2-port FE motherboard chip ✓
        "console_type": "telnet",
        "port_name_format": "FastEthernet{0}/{1}",
        "port_segment_size": 1,
    },
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
    "VPCS": {
        "node_type": "vpcs",
        "console_type": "telnet",
        "port_name_format": "Ethernet{0}",
        "port_segment_size": 1,
    },
    "Ethernet Switch": {
        "node_type": "ethernet_switch",
        "console_type": "none",
        "port_name_format": "Ethernet{0}",
        "port_segment_size": 1,
    },
    "Ethernet Hub": {
        "node_type": "ethernet_hub",
        "port_name_format": "Ethernet{0}",
        "port_segment_size": 1,
    },
}