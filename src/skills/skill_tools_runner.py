"""Tools-mode skill invocation helper."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from src.skills.settings import skill_tools_max_turns, skill_tools_runtime_limits
from src.skills.skill_emitters import auto_emit_artifacts
from src.skills.skill_models import Skill, SkillInvocationResult
from src.skills.text_normalization import normalize_skill_text

logger = logging.getLogger(__name__)


def resolve_extra_script_roots(skill: Skill) -> tuple[list[Path], list[str]]:
    """Resolve opt-in cross-skill script roots for tools-mode execution."""
    warnings: list[str] = []
    roots: list[Path] = []
    raw_paths = skill.frontmatter.metadata.get("script_paths") or []
    if isinstance(raw_paths, str):
        raw_paths = [raw_paths]
    skill_dir_resolved = Path(skill.path).resolve()
    for entry in raw_paths:
        if not isinstance(entry, str) or not entry.strip():
            warnings.append(f"script_paths: skipping non-string entry {entry!r}")
            continue
        candidate = (Path(skill.path) / entry).resolve()
        if not candidate.is_dir():
            warnings.append(
                f"script_paths: directory does not exist or is not a dir: {entry}"
            )
            continue
        if candidate == skill_dir_resolved:
            continue
        roots.append(candidate)
    return roots, warnings


async def run_tools_skill(
    *,
    skill: Skill,
    workspace: str,
    user_prompt: str,
    workspace_root: Optional[Path],
    slice_fn: Optional[Callable[..., dict[str, Any]]],
    retrieve_fn: Optional[Callable[..., Awaitable[dict[str, Any]]]],
    run_store: Any,
    mcp_registry: Any,
    touch_invocation: Callable[[str], None],
    run_tool_loop_fn: Optional[Callable[..., Awaitable[Any]]] = None,
    tool_context_cls: Optional[type] = None,
    auto_emit_fn: Callable[[Skill, Path], None] = auto_emit_artifacts,
) -> SkillInvocationResult:
    """Run a tools-mode skill using the multi-turn tool loop."""
    if workspace_root is None:
        raise RuntimeError("tools-mode skills require workspace_root for run persistence")

    if run_tool_loop_fn is None:
        from src.skills.runtime import run_tool_loop as run_tool_loop_fn
    if tool_context_cls is None:
        from src.skills.tools import ToolContext as tool_context_cls

    warnings: list[str] = []
    started = datetime.now(timezone.utc)
    run_id, run_dir = run_store.create_run_dir(
        workspace_root=workspace_root,
        skill_name=skill.name,
        user_prompt=user_prompt,
        started_at=started,
        create_tool_outputs=True,
    )

    max_turns = skill_tools_max_turns(skill.frontmatter.metadata)
    limits = skill_tools_runtime_limits()
    extra_script_roots, extra_warnings = resolve_extra_script_roots(skill)
    warnings.extend(extra_warnings)

    ctx = tool_context_cls(
        skill_name=skill.name,
        skill_dir=Path(skill.path),
        run_dir=run_dir,
        workspace_dir=workspace_root,
        workspace_name=workspace,
        slice_fn=slice_fn,
        retrieve_fn=retrieve_fn,
        max_read_bytes=limits.max_read_bytes,
        max_write_bytes=limits.max_write_bytes,
        max_script_seconds=limits.max_script_seconds,
        max_kg_entities_per_type=limits.max_kg_entities_per_type,
        max_kg_chunks=limits.max_kg_chunks,
        max_kg_chunks_per_entity=limits.max_kg_chunks_per_entity,
        max_kg_relationships_per_entity=limits.max_kg_relationships_per_entity,
        extra_script_roots=extra_script_roots,
    )

    requested_mcps = skill.frontmatter.required_mcps
    if requested_mcps:
        try:
            startup = await mcp_registry.start_run_sessions(run_id=run_id, requested=requested_mcps)
            ctx.mcp_sessions = startup.sessions
            warnings.extend(startup.warning_messages())
            if startup.started_names:
                logger.info(
                    "skill %s run %s: MCP sessions live: %s",
                    skill.name,
                    run_id,
                    startup.started_names,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("MCP startup failed for skill %s run %s: %s", skill.name, run_id, exc)
            warnings.append(f"MCP startup failed: {exc}")

    try:
        loop_result = await run_tool_loop_fn(
            skill_name=skill.name,
            skill_body=skill.body_md,
            user_prompt=user_prompt,
            ctx=ctx,
            max_turns=max_turns,
        )
    finally:
        if ctx.mcp_sessions:
            try:
                await mcp_registry.shutdown_run(run_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("MCP shutdown failed for run %s: %s", run_id, exc)

    warnings.extend(loop_result.warnings)
    elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    response_text = normalize_skill_text(loop_result.response)

    try:
        run_store.persist_tools_run(
            run_dir=run_dir,
            run_id=run_id,
            skill_name=skill.name,
            workspace=workspace,
            user_prompt=user_prompt,
            response=response_text,
            turns=loop_result.turns,
            tool_calls=loop_result.tool_calls,
            finish_reason=loop_result.finish_reason,
            usage_total=loop_result.usage_total,
            warnings=warnings,
            elapsed_ms=elapsed_ms,
            started_at=started,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to persist tools-mode run for %s: %s", skill.name, exc)
        warnings.append(f"persistence failed: {exc}")

    try:
        auto_emit = bool(skill.frontmatter.metadata.get("auto_emit_artifacts"))
    except Exception:
        auto_emit = False
    if auto_emit:
        try:
            auto_emit_fn(skill, Path(run_dir))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-emit artifacts failed for %s run %s: %s", skill.name, run_id, exc)
            warnings.append(f"auto_emit_artifacts failed: {exc}")

    touch_invocation(skill.name)

    return SkillInvocationResult(
        skill=skill.name,
        workspace=workspace,
        response=response_text,
        entities_used=[],
        warnings=warnings,
        elapsed_ms=elapsed_ms,
        prompt_tokens_estimate=int(loop_result.usage_total.get("total_tokens", 0)),
        run_id=run_id,
        run_dir=str(Path(run_dir).resolve()),
        finish_reason=loop_result.finish_reason,
    )