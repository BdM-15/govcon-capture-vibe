"""Pipeline library + LangGraph Studio helpers for Theseus UI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.server.langgraph_studio_lifecycle import studio_status_payload
from src.server.runtime_state import get_langgraph_studio_status

_REPO_ROOT = Path(__file__).resolve().parents[2]

PIPELINE_LIBRARY: list[dict[str, Any]] = [
    {
        "pipeline_id": "mission-readiness",
        "name": "Mission Readiness Frame",
        "description": (
            "Decomposed readiness research: eval, workload, pains, modernization, "
            "tea-leaves, win-themes → deterministic merge → brief synthesis."
        ),
        "preset": "mission-readiness",
        "engine": "langgraph",
        "graph_id": "mission_readiness",
        "skill_count": 7,
        "doc_path": "docs/SKILL_DECOMPOSITION.md",
        "waves": [
            ["eval", "workload"],
            ["pains", "modernization", "tea-leaves"],
            ["win-themes"],
            ["compile"],
        ],
    },
]


def _studio_url() -> str:
    runtime = studio_status_payload(get_langgraph_studio_status())
    if runtime.get("url"):
        return str(runtime["url"])
    explicit = str(os.getenv("THESEUS_LANGGRAPH_STUDIO_URL") or "").strip()
    if explicit:
        return explicit
    port = str(os.getenv("LANGGRAPH_STUDIO_PORT") or "2024").strip()
    return f"http://127.0.0.1:{port}"


def _studio_ready() -> bool:
    return bool(studio_status_payload(get_langgraph_studio_status()).get("ok"))


def register_pipeline_routes(app: Any) -> None:
    router = APIRouter()

    @router.get("/api/ui/pipelines/library", tags=["theseus-ui"])
    async def pipeline_library_route() -> JSONResponse:
        runtime = studio_status_payload(get_langgraph_studio_status())
        studio_ready = bool(runtime.get("ok"))
        studio_api = str(runtime.get("url") or _studio_url())
        studio_graph = str(runtime.get("graph_url") or "")
        items = []
        for entry in PIPELINE_LIBRARY:
            row = dict(entry)
            row["studio_url"] = studio_api if studio_ready else ""
            row["studio_graph_url"] = studio_graph if studio_ready else ""
            row["studio_ready"] = studio_ready
            items.append(row)
        return JSONResponse(
            {
                "pipelines": items,
                "studio_url": studio_api if studio_ready else "",
                "studio_graph_url": studio_graph if studio_ready else "",
                "studio_ready": studio_ready,
                "studio_auto_start": True,
                "repo_root": str(_REPO_ROOT),
            }
        )

    @router.get("/api/ui/skill-chains/{chain_id}/events", tags=["theseus-ui"])
    async def chain_events_route(chain_id: str, tail: int = 200) -> JSONResponse:
        from src.core.config import get_settings
        from src.skills.graphs.chain_events import read_chain_events

        workspace_root = _REPO_ROOT / "rag_storage" / get_settings().workspace
        chain_dir = workspace_root / "skill_chains" / chain_id
        if not chain_dir.is_dir():
            return JSONResponse({"chain_id": chain_id, "events": [], "error": "not_found"}, status_code=404)
        events = read_chain_events(chain_dir, tail=max(1, min(tail, 500)))
        return JSONResponse({"chain_id": chain_id, "events": events})

    app.include_router(router)