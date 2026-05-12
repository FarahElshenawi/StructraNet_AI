"""
preflight.py — Environment profile collection and compatibility checks.

Collects the minimum user-specific information needed to generate portable
.gns3project files that are likely to run on the user's machine.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class PreflightProfile:
    gns3_version: str
    supports_iou: bool
    supports_qemu: bool
    supports_docker: bool
    strict_validation: bool = True

    @property
    def unsupported_node_types(self) -> set[str]:
        blocked: set[str] = set()
        if not self.supports_iou:
            blocked.add("iou")
        if not self.supports_qemu:
            blocked.add("qemu")
        if not self.supports_docker:
            blocked.add("docker")
        return blocked


def _ask_bool(prompt: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    raw = input(f"{prompt} {suffix} ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes", "1", "true"}


def load_profile(path: str) -> PreflightProfile:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    return PreflightProfile(
        gns3_version=str(data.get("gns3_version", "2.2")),
        supports_iou=bool(data.get("supports_iou", False)),
        supports_qemu=bool(data.get("supports_qemu", True)),
        supports_docker=bool(data.get("supports_docker", False)),
        strict_validation=bool(data.get("strict_validation", True)),
    )


def save_profile(profile: PreflightProfile, path: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(profile), indent=2), encoding="utf-8")


def collect_profile_interactive() -> PreflightProfile:
    print("\n[Preflight] Tell me about your GNS3 environment:")
    version = input("  GNS3 version (example: 2.2.54) [2.2]: ").strip() or "2.2"
    supports_iou = _ask_bool("  Is IOU usable on your setup?", default=False)
    supports_qemu = _ask_bool("  Is QEMU usable on your setup?", default=True)
    supports_docker = _ask_bool("  Is Docker usable on your setup?", default=False)
    strict = _ask_bool("  Fail fast on compatibility issues?", default=True)
    return PreflightProfile(
        gns3_version=version,
        supports_iou=supports_iou,
        supports_qemu=supports_qemu,
        supports_docker=supports_docker,
        strict_validation=strict,
    )


def check_topology_compatibility(
    topology_dict: Dict[str, Any],
    profile: PreflightProfile,
) -> List[str]:
    issues: List[str] = []
    nodes = topology_dict.get("topology", {}).get("nodes", [])
    blocked = profile.unsupported_node_types

    if not str(profile.gns3_version).startswith("2.2"):
        issues.append(
            f"GNS3 version '{profile.gns3_version}' may be incompatible "
            "with revision 9 exports (recommended: 2.2.x)."
        )

    for node in nodes:
        ntype = str(node.get("node_type", "")).lower()
        name = node.get("name", node.get("node_id", "?"))
        if ntype in blocked:
            issues.append(
                f"Node '{name}' uses unsupported type '{ntype}' "
                "for your declared environment profile."
            )
    return issues

