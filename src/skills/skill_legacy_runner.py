"""Legacy single-shot skill invocation helper."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from src.skills.skill_emitters import auto_emit_artifacts
from src.skills.skill_models import Skill, SkillInvocationResult
from src.skills.text_normalization import normalize_skill_text

logger = logging.getLogger(__name__)


def compose_skill_prompt(
    skill: Skill,
    workspace: str,
    user_prompt: str,
    payload_json: str,
) -> str:
    """Compose the legacy single-shot skill prompt."""
    return (
        f"# Agent Skill: {skill.name} ({skill.frontmatter.version})\n"
        f"Active workspace: {workspace}\n\n"
        "## Skill Instructions\n"
        f"{skill.body_md.strip()}\n\n"
        "## Workspace Briefing Book (JSON)\n"
        "This briefing book is the authoritative source of truth for the "
        "active RFP workspace. It contains four sections:\n"
        "  * `entities`           — typed entities (each carries `source_chunks`)\n"
        "  * `source_chunks`      — verbatim RFP text blocks (quote from these)\n"
        "  * `relationships`      — typed KG edges between entities\n"
        "  * `retrieval_metadata` — how this slice was selected (chat-grade\n"
        "    hybrid retrieval vs. bulk fallback); use it to gauge coverage.\n\n"
        "### Citation Discipline (MANDATORY)\n"
        "When you reference a requirement, deliverable, clause, "
        "`proposal_instruction` (UCF Section L or equivalent — e.g. an "
        '"Instructions to Offerors" section in a FAR 16 task order, FOPR, '
        "BPA call, OTA, or agency-specific format), `evaluation_factor` "
        '(UCF Section M or equivalent — e.g. "Evaluation Criteria", '
        "adjectival rating scheme, or LPTA basis), or any other RFP "
        "obligation:\n"
        "  1. **Quote verbatim** from the matching `source_chunks[*].content` — "
        "never paraphrase the RFP wording.\n"
        "  2. **Cite the chunk_id inline** in the form `[chunk-xxxxxxxx]` so "
        "the reader can trace any claim back to the source document.\n"
        "  3. If a needed source chunk is missing from the briefing book, "
        "emit a `GAP` marker rather than fabricating language.\n"
        "  4. Use the `relationships` block to confirm "
        "`proposal_instruction` ↔ `evaluation_factor` ↔ `requirement` "
        "traceability — do not invent links the KG does not show.\n\n"
        "### Coverage Discipline (Phase 1.6)\n"
        "The briefing book was assembled by chat-grade hybrid retrieval over "
        "the user request + skill description. Treat it as the *complete* "
        "evidence set for this invocation:\n"
        "  * Do **not** invent entities, factors, requirements, deliverables, "
        "or clauses that are absent from the briefing book.\n"
        "  * **This solicitation may use UCF or non-UCF format.** Map to the "
        "actual `proposal_instruction` and `evaluation_factor` entities "
        "regardless of section heading. Only emit `GAP` when no matching "
        "instruction or evaluation criterion exists *anywhere* in the "
        "briefing book — never because the entity lacks a literal \"Section "
        "L\" or \"Section M\" label. Many federal task orders, FOPRs, BPA "
        "calls, and OTAs put instructions inline in the PWS or in named "
        "attachments.\n"
        "  * If the user asks about a topic that is not represented in the "
        "`entities` / `source_chunks` blocks (check `retrieval_metadata` for "
        "coverage signals like low `matched_entities`), say so explicitly with "
        "`GAP: insufficient retrieval coverage for <topic>` instead of "
        "substituting unrelated content from another factor or section.\n"
        "  * Stay inside the slice. If the user asks for the small business "
        "participation outline, do not bleed in cybersecurity, transition, or "
        "other factors unless the briefing book actually surfaces them.\n\n"
        "```json\n"
        f"{payload_json}\n"
        "```\n\n"
        "## User Request\n"
        f"{user_prompt.strip() if user_prompt.strip() else '(use skill defaults)'}\n\n"
        "## Output\n"
        "Produce your response below. Be thorough, cite sources, and follow "
        "the skill instructions above.\n"
    )


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