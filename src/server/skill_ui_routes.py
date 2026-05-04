"""Agent-skill UI routes for Project Theseus."""

from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable, Optional

from fastapi import FastAPI

from src.core import get_settings
from src.server.skill_catalog_ui_routes import register_skill_catalog_ui_routes
from src.server.skill_invoke_ui_routes import register_skill_invoke_ui_routes
from src.server.skill_run_ui_routes import register_skill_run_ui_routes
from src.server.skill_settings_ui_routes import register_skill_settings_ui_routes
from src.skills import get_skill_manager
from src.skills.settings import SkillSettingsStore

QueryDataFunc = Callable[
    [str, str, list[dict], dict],
    Awaitable[dict],
]
LlmFunc = Callable[[str], Awaitable[str]]


def register_skill_ui_routes(
    app: FastAPI,
    *,
    workspace_dir: Callable[[], Path],
    data_func: Optional[QueryDataFunc],
    llm_func: Optional[LlmFunc],
) -> None:
    """Register skill, run, Studio, and chunk-preview UI endpoints."""

    settings_store = SkillSettingsStore(workspace_dir)

    register_skill_settings_ui_routes(
        app,
        settings_store=settings_store,
        workspace_name=lambda: get_settings().workspace,
    )
    register_skill_catalog_ui_routes(app, manager_factory=get_skill_manager)
    register_skill_invoke_ui_routes(
        app,
        workspace_dir=workspace_dir,
        settings_store=settings_store,
        data_func=data_func,
        llm_func=llm_func,
        workspace_name=lambda: get_settings().workspace,
        manager_factory=get_skill_manager,
    )

    register_skill_run_ui_routes(app, workspace_dir=workspace_dir)
