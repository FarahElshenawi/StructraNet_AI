"""
api.py — FastAPI REST API for Structranet AI.

Entry point: uvicorn api:app --reload --port 8000

Wraps the existing CLI pipeline modules (ai_agent, config_agent,
gns3_exporter, preflight) as HTTP endpoints with SSE support for
real-time progress streaming to the Next.js frontend.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from api_models import (
    CreateSessionRequest,
    EditRequest,
    GenerateRequest,
    InventoryItem,
    SessionResponse,
    SessionStatus,
)
from appliance_catalog import load_catalog
from main import catalog_to_inventory
from pipeline_runner import run_phase1, run_phase2_and_export
from preflight import (
    PreflightProfile,
    filter_inventory_by_profile,
    profile_from_dict,
    profile_to_dict,
)
from session_store import SessionStore

load_dotenv()
logger = logging.getLogger("structranet.api")

store = SessionStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(name)s [%(levelname)s] %(message)s",
    )
    logger.info("Structranet AI API starting")
    yield
    logger.info("Structranet AI API shutting down")


app = FastAPI(
    title="Structranet AI API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════════════

async def _get_session(session_id: str):
    session = await store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _profile_input_to_preflight(data: Dict[str, Any]) -> PreflightProfile:
    return profile_from_dict({
        "gns3_version": data.get("gns3_version", "2.2"),
        "supports_iou": data.get("supports_iou", False),
        "supports_qemu": data.get("supports_qemu", True),
        "supports_docker": data.get("supports_docker", False),
        "strict_validation": data.get("strict_validation", True),
        "require_template_image_map": data.get("require_template_image_map", False),
        "template_image_map": data.get("template_image_map"),
        "security_profile": data.get("security_profile", "none"),
    })


# ═══════════════════════════════════════════════════════════════════════════════
#  Health
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


# ═══════════════════════════════════════════════════════════════════════════════
#  Catalog
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/catalog")
async def get_catalog(path: str | None = None):
    catalog = load_catalog(path)
    inventory = catalog_to_inventory(catalog)
    return [
        InventoryItem(
            name=d["name"],
            gns3_type=d["gns3_type"],
            category=d.get("category", ""),
            port_count=d.get("port_count"),
        )
        for d in inventory
    ]


# ═══════════════════════════════════════════════════════════════════════════════
#  Sessions
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/sessions", status_code=201)
async def create_session(body: CreateSessionRequest):
    catalog = load_catalog(body.catalog_path)
    inventory = catalog_to_inventory(catalog)
    if not inventory:
        raise HTTPException(400, "No appliances in catalog")

    profile = _profile_input_to_preflight(body.profile.model_dump())
    filtered_inventory, blocked_types = filter_inventory_by_profile(
        inventory, profile,
    )
    if not filtered_inventory:
        raise HTTPException(400, "Profile blocks all available node types")

    session = await store.create(
        profile=profile,
        catalog=catalog,
        inventory=inventory,
        filtered_inventory=filtered_inventory,
        blocked_types=blocked_types,
    )

    return SessionResponse(
        session_id=session.session_id,
        created_at=datetime.fromtimestamp(
            session.created_at, tz=timezone.utc,
        ).isoformat(),
        profile=body.profile,
        inventory=[
            InventoryItem(
                name=d["name"],
                gns3_type=d["gns3_type"],
                category=d.get("category", ""),
                port_count=d.get("port_count"),
            )
            for d in filtered_inventory
        ],
    )


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    session = await _get_session(session_id)
    return SessionStatus(
        session_id=session.session_id,
        phase=session.phase,
        sub_phase=session.sub_phase,
        topology=session.topology_data,
        summary=session.summary,
        requirements=session.requirements,
        error=session.error,
        iteration=session.state.iteration,
        gns3project_ready=session.gns3project_path is not None,
    )


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    deleted = await store.delete(session_id)
    if not deleted:
        raise HTTPException(404, "Session not found")
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
#  Generation
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/sessions/{session_id}/generate", status_code=202)
async def start_generation(
    session_id: str,
    body: GenerateRequest,
    background_tasks: BackgroundTasks,
):
    session = await _get_session(session_id)
    if session.phase not in ("idle", "review", "error"):
        raise HTTPException(
            409, f"Cannot generate in phase '{session.phase}'",
        )

    if body.security_profile != "none":
        session.profile.security_profile = body.security_profile

    session.state.last_request = body.request

    background_tasks.add_task(run_phase1, session, store, body.request)
    return {"status": "started", "session_id": session_id}


@app.post("/api/sessions/{session_id}/edit", status_code=202)
async def edit_topology(
    session_id: str,
    body: EditRequest,
    background_tasks: BackgroundTasks,
):
    session = await _get_session(session_id)
    if session.phase != "review":
        raise HTTPException(
            409, f"Cannot edit in phase '{session.phase}' (must be 'review')",
        )

    session.state.chat_history.append({
        "role": "user",
        "content": (
            f"Please modify the topology based on this feedback: {body.feedback}\n"
            "Return the complete updated design in the same CoT JSON envelope format."
        ),
    })

    background_tasks.add_task(
        run_phase1, session, store, session.state.last_request,
    )
    return {"status": "started", "session_id": session_id}


@app.post("/api/sessions/{session_id}/approve", status_code=202)
async def approve_topology(
    session_id: str,
    background_tasks: BackgroundTasks,
):
    session = await _get_session(session_id)
    if session.phase != "review":
        raise HTTPException(
            409, f"Cannot approve in phase '{session.phase}' (must be 'review')",
        )

    background_tasks.add_task(run_phase2_and_export, session, store)
    return {"status": "started", "session_id": session_id}


# ═══════════════════════════════════════════════════════════════════════════════
#  SSE Events
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/sessions/{session_id}/events")
async def session_events(session_id: str):
    session = await _get_session(session_id)
    queue = store.subscribe(session)

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield {"event": "keepalive", "data": "{}"}
                    continue

                if event is None:
                    break

                yield {
                    "event": event.get("event", "message"),
                    "data": json.dumps(event.get("data", {})),
                }
        except asyncio.CancelledError:
            pass
        finally:
            store.unsubscribe(session, queue)

    return EventSourceResponse(event_generator())


# ═══════════════════════════════════════════════════════════════════════════════
#  Data endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/sessions/{session_id}/topology")
async def get_topology(session_id: str):
    session = await _get_session(session_id)
    if session.topology_data is None:
        raise HTTPException(404, "No topology generated yet")
    return session.topology_data


@app.get("/api/sessions/{session_id}/requirements")
async def get_requirements(session_id: str):
    session = await _get_session(session_id)
    return session.requirements


# ═══════════════════════════════════════════════════════════════════════════════
#  Downloads
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/sessions/{session_id}/download")
async def download_gns3project(session_id: str):
    session = await _get_session(session_id)
    if session.gns3project_path is None:
        raise HTTPException(404, "Export not complete")

    path = Path(session.gns3project_path)
    if not path.exists():
        raise HTTPException(404, "Export file missing from disk")

    return FileResponse(
        path=str(path),
        media_type="application/zip",
        filename=path.name,
    )


@app.get("/api/sessions/{session_id}/download/json")
async def download_final_json(session_id: str):
    session = await _get_session(session_id)
    final_file = Path(session.output_dir) / "final_topology.json"
    if not final_file.exists():
        phase1_file = Path(session.output_dir) / "_topology.json"
        if phase1_file.exists():
            final_file = phase1_file
        else:
            raise HTTPException(404, "No topology JSON available")

    return FileResponse(
        path=str(final_file),
        media_type="application/json",
        filename=final_file.name,
    )
