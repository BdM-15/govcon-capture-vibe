"""Skill-runtime tools for agnostic external web research."""

from __future__ import annotations

from src.skills.tool_types import ToolContext, ToolError, ToolResult
from src.web_research import fetch_page, provider_status, research, search_web
from src.web_research.config import web_research_settings


def _settings(ctx: ToolContext):
    return web_research_settings(workspace_dir=ctx.workspace_dir)


async def tool_web_search(
    ctx: ToolContext,
    query: str,
    limit: int = 5,
) -> ToolResult:
    if not str(query or "").strip():
        raise ToolError("query must be a non-empty string")
    try:
        payload = await search_web(
            query,
            limit=limit,
            settings=_settings(ctx),
            workspace_dir=ctx.workspace_dir,
        )
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return ToolResult(payload=payload)


async def tool_web_fetch(
    ctx: ToolContext,
    url: str,
    quality: str = "standard",
) -> ToolResult:
    if not str(url or "").strip():
        raise ToolError("url must be a non-empty string")
    normalized_quality = str(quality or "standard").strip().lower()
    if normalized_quality not in {"standard", "premium"}:
        raise ToolError("quality must be 'standard' or 'premium'")
    try:
        payload = await fetch_page(
            url,
            quality=normalized_quality,
            settings=_settings(ctx),
            workspace_dir=ctx.workspace_dir,
        )
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return ToolResult(
        payload=payload,
        truncated=bool(payload.get("truncated")),
    )


async def tool_web_research(
    ctx: ToolContext,
    queries: list[str] | None = None,
    urls: list[str] | None = None,
    fetch_quality: str = "standard",
    max_fetches: int = 3,
) -> ToolResult:
    normalized_quality = str(fetch_quality or "standard").strip().lower()
    if normalized_quality not in {"standard", "premium"}:
        raise ToolError("fetch_quality must be 'standard' or 'premium'")
    if max_fetches < 0 or max_fetches > 10:
        raise ToolError("max_fetches must be between 0 and 10")
    try:
        payload = await research(
            queries=queries,
            urls=urls,
            fetch_quality=normalized_quality,
            max_fetches=max_fetches,
            settings=_settings(ctx),
            workspace_dir=ctx.workspace_dir,
        )
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    truncated = any(bool(row.get("truncated")) for row in payload.get("fetches") or [])
    return ToolResult(payload=payload, truncated=truncated)


async def tool_web_provider_status(ctx: ToolContext) -> ToolResult:
    return ToolResult(payload=provider_status(_settings(ctx)))