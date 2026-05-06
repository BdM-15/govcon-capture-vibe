"""Legacy single-shot skill invocation helper."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from src.skills.skill_emitters import auto_emit_artifacts
from src.skills.skill_models import Skill, SkillInvocationResult
from src.skills.skill_prompting import compose_skill_prompt
from src.skills.text_normalization import normalize_skill_text

logger = logging.getLogger(__name__)


def _is_false(value: Any) -> bool:
    if isinstance(value, bool):
        return value is False
    if isinstance(value, str):
        return value.strip().lower() in {"0", "false", "no", "off"}
    return False


async def run_legacy_skill(
    *,
    skill: Skill,
    workspace: str,
    user_prompt: str,
    entity_payload: dict[str, Any],
    llm: Callable[[str], Awaitable[str]],
    max_payload_chars: Optional[int],
    default_max_payload_chars: int,
    workspace_root: Optional[Path],
    persist_run: Callable[..., tuple[str, str]],
    touch_invocation: Callable[[str], None],
    auto_emit_fn: Callable[[Skill, Path], None] = auto_emit_artifacts,
) -> SkillInvocationResult:
    """Run the pre-tools-mode single-shot prompt path."""
    warnings: list[str] = []
    budget = max_payload_chars if max_payload_chars is not None else default_max_payload_chars
    payload_json = json.dumps(entity_payload, ensure_ascii=False, indent=2)
    if len(payload_json) > budget:
        payload_json = payload_json[:budget] + "\n…[truncated]"
        warnings.append(
            f"briefing book truncated at {budget} chars (SKILL_MAX_PAYLOAD_CHARS); "
            "raise the env var, narrow entity_types, or lower max_chunks_per_entity"
        )

    if isinstance(entity_payload.get("entities"), dict):
        entities_used = sorted(entity_payload["entities"].keys())
    else:
        entities_used = sorted(
            key for key in entity_payload.keys()
            if key not in {"source_chunks", "relationships", "retrieval_metadata"}
        )

    composed = compose_skill_prompt(skill, workspace, user_prompt, payload_json)

    started = datetime.now(timezone.utc)
    response = await llm(composed)
    response = normalize_skill_text(response)
    elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)

    touch_invocation(skill.name)

    run_id = ""
    run_dir = ""
    if workspace_root is not None:
        try:
            run_id, run_dir = persist_run(
                workspace_root=workspace_root,
                skill_name=skill.name,
                workspace=workspace,
                user_prompt=user_prompt,
                composed_prompt=composed,
                response=response,
                entities_used=entities_used,
                warnings=warnings,
                elapsed_ms=elapsed_ms,
                started_at=started,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to persist skill run for %s: %s", skill.name, exc)
            warnings.append(f"persistence failed: {exc}")

    try:
        auto_emit = not _is_false(skill.frontmatter.metadata.get("auto_emit_artifacts", True))
    except Exception:
        auto_emit = True
    if auto_emit and run_dir:
        try:
            auto_emit_fn(skill, Path(run_dir))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-emit artifacts failed for %s run %s: %s", skill.name, run_id, exc)
            warnings.append(f"auto_emit_artifacts failed: {exc}")

    return SkillInvocationResult(
        skill=skill.name,
        workspace=workspace,
        response=response,
        entities_used=entities_used,
        warnings=warnings,
        elapsed_ms=elapsed_ms,
        prompt_tokens_estimate=len(composed) // 4,
        run_id=run_id,
        run_dir=run_dir,
        finish_reason="",
    )