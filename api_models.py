"""
api_models.py — Pydantic v2 request/response models for the Structranet AI REST API.

Separate from schema.py (which defines GNS3 domain models with strict validators).
These models serve the Next.js frontend and are simpler projections.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════════
#  Profile & Session Creation
# ═══════════════════════════════════════════════════════════════════════════════

class ProfileInput(BaseModel):
    gns3_version: str = "2.2"
    supports_iou: bool = False
    supports_qemu: bool = True
    supports_docker: bool = False
    strict_validation: bool = True
    require_template_image_map: bool = False
    template_image_map: Optional[Dict[str, str]] = None
    security_profile: Literal["none", "basic", "enterprise"] = "none"


class CreateSessionRequest(BaseModel):
    profile: ProfileInput = Field(default_factory=ProfileInput)
    catalog_path: Optional[str] = None


class InventoryItem(BaseModel):
    name: str
    gns3_type: str
    category: str
    port_count: Optional[int] = None


class SessionResponse(BaseModel):
    session_id: str
    created_at: str
    profile: ProfileInput
    inventory: List[InventoryItem]


# ═══════════════════════════════════════════════════════════════════════════════
#  Generation & Edit
# ═══════════════════════════════════════════════════════════════════════════════

class GenerateRequest(BaseModel):
    request: str
    project_name: Optional[str] = None
    security_profile: Literal["none", "basic", "enterprise"] = "none"


class EditRequest(BaseModel):
    feedback: str


# ═══════════════════════════════════════════════════════════════════════════════
#  Thought Stream
# ═══════════════════════════════════════════════════════════════════════════════

class ThoughtChunk(BaseModel):
    id: str
    type: Literal["understanding", "decision", "assumption", "warning"]
    content: str
    timestamp: float = Field(default_factory=time.time)


# ═══════════════════════════════════════════════════════════════════════════════
#  Topology Data (simplified for frontend SVG rendering)
# ═══════════════════════════════════════════════════════════════════════════════

class TopologyNode(BaseModel):
    node_id: str
    name: str
    node_type: str
    template_name: str
    link_count: int = 0


class TopologyLink(BaseModel):
    from_node: str
    to_node: str
    link_type: str = "ethernet"


class TopologyData(BaseModel):
    name: str
    nodes: List[TopologyNode]
    links: List[TopologyLink]
    node_count: int
    link_count: int


# ═══════════════════════════════════════════════════════════════════════════════
#  Requirements Manifest (structured)
# ═══════════════════════════════════════════════════════════════════════════════

class RequiredAppliance(BaseModel):
    node_id: str
    name: str
    node_type: str
    template_name: str
    category: Literal["dynamips", "iou", "qemu", "docker", "builtin"]
    image_required: bool
    image_file: Optional[str] = None
    status: Literal["ok", "missing", "builtin"]


# ═══════════════════════════════════════════════════════════════════════════════
#  Summary
# ═══════════════════════════════════════════════════════════════════════════════

class TopologySummary(BaseModel):
    thinking_text: str
    thoughts: List[ThoughtChunk]
    design_review: List[str]
    assumptions: List[str]


# ═══════════════════════════════════════════════════════════════════════════════
#  Session Status (full snapshot for polling)
# ═══════════════════════════════════════════════════════════════════════════════

class SessionStatus(BaseModel):
    session_id: str
    phase: Literal["idle", "generating", "review", "exporting", "success", "error"]
    sub_phase: Optional[Literal["thinking", "building", "finalizing"]] = None
    topology: Optional[TopologyData] = None
    summary: Optional[TopologySummary] = None
    requirements: List[RequiredAppliance] = []
    error: Optional[str] = None
    iteration: int = 0
    gns3project_ready: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
#  Export
# ═══════════════════════════════════════════════════════════════════════════════

class ExportResponse(BaseModel):
    download_url: str
    validator_passed: Optional[bool] = None
    file_size_bytes: int = 0
    node_count: int = 0
    link_count: int = 0
    configured_count: int = 0
