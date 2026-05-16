"""
session_store.py — In-memory session registry with SSE fan-out.

Each session carries pipeline state (SessionState from ai_agent),
a dedicated output directory, and a list of asyncio.Queue subscribers
for Server-Sent Events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ai_agent import SessionState
from api_models import RequiredAppliance, TopologyData, TopologySummary

logger = logging.getLogger("structranet.session_store")


@dataclass
class Session:
    session_id: str
    created_at: float
    output_dir: str

    # Preflight
    profile: Any  # PreflightProfile (avoid circular import at type level)
    catalog: Dict[str, Any]
    inventory: List[Dict[str, Any]]
    filtered_inventory: List[Dict[str, Any]]
    blocked_types: Set[str]

    # Pipeline state
    state: SessionState = field(default_factory=SessionState)
    phase: str = "idle"
    sub_phase: Optional[str] = None
    error: Optional[str] = None

    # Artifacts
    raw_topology: Any = None  # GNS3Project from Phase 1
    topology_dict: Optional[Dict[str, Any]] = None
    final_dict: Optional[Dict[str, Any]] = None
    topology_data: Optional[TopologyData] = None
    summary: Optional[TopologySummary] = None
    requirements: List[RequiredAppliance] = field(default_factory=list)
    gns3project_path: Optional[str] = None
    validator_passed: Optional[bool] = None

    # SSE subscribers
    event_queues: List[asyncio.Queue] = field(default_factory=list)


class SessionStore:
    def __init__(self, base_output_dir: str = "output/sessions"):
        self._sessions: Dict[str, Session] = {}
        self._base_dir = base_output_dir
        self._lock = asyncio.Lock()

    async def create(
        self,
        profile: Any,
        catalog: Dict[str, Any],
        inventory: List[Dict[str, Any]],
        filtered_inventory: List[Dict[str, Any]],
        blocked_types: Set[str],
    ) -> Session:
        async with self._lock:
            session_id = uuid.uuid4().hex[:12]
            output_dir = str(Path(self._base_dir) / session_id)
            Path(output_dir).mkdir(parents=True, exist_ok=True)

            session = Session(
                session_id=session_id,
                created_at=time.time(),
                output_dir=output_dir,
                profile=profile,
                catalog=catalog,
                inventory=inventory,
                filtered_inventory=filtered_inventory,
                blocked_types=blocked_types,
            )
            self._sessions[session_id] = session
            logger.info("Session created: %s → %s", session_id, output_dir)
            return session

    async def get(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    async def delete(self, session_id: str) -> bool:
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session is None:
                return False
            for q in session.event_queues:
                await q.put(None)
            try:
                shutil.rmtree(session.output_dir, ignore_errors=True)
            except OSError:
                pass
            logger.info("Session deleted: %s", session_id)
            return True

    async def list_sessions(self) -> List[Dict[str, Any]]:
        return [
            {
                "session_id": s.session_id,
                "phase": s.phase,
                "created_at": s.created_at,
            }
            for s in self._sessions.values()
        ]

    def subscribe(self, session: Session) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        session.event_queues.append(queue)
        logger.debug(
            "SSE subscriber added for session %s (total: %d)",
            session.session_id, len(session.event_queues),
        )
        return queue

    def unsubscribe(self, session: Session, queue: asyncio.Queue) -> None:
        try:
            session.event_queues.remove(queue)
        except ValueError:
            pass

    async def broadcast(self, session: Session, event: Dict[str, Any]) -> None:
        dead: List[asyncio.Queue] = []
        for q in session.event_queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            try:
                session.event_queues.remove(q)
            except ValueError:
                pass
