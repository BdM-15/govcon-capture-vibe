"""Support helpers for the skill runtime tool loop."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.skills.llm_chat import ChatToolCall
from src.skills.tool_registry import ToolSpec
from src.skills.tool_types import ToolContext, ToolError
from src.skills.tools import serialize_tool_payload_for_model

logger = logging.getLogger(__name__)


@dataclass
class ToolLoopResult:
    """Outcome of one ``run_tool_loop`` call."""

    response: str
    transcript: list[dict[str, Any]]
    turns: int
    tool_calls: int
    finish_reason: str
    usage_total: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def compose_system_prompt(
    skill_name: str,
    skill_body: str,
    workspace_name: str,
    tool_names: list[str],
) -> str:
    """Assemble runtime system message for one tools-mode run."""
    return (
        f"You are executing the agent skill `{skill_name}` against Project "
        f"Theseus workspace `{workspace_name}`.\n"
        "\n"
        "## Skill Instructions (authoritative)\n"
        f"{skill_body.strip()}\n"
        "\n"
        "## Operating Rules\n"
        f"- Tools available this run: {', '.join(tool_names)}.\n"
        "- Use the tools to fetch every fact you need — do not guess about "
        "the workspace contents. Pull entity slices with `kg_entities`, "
        "free-text searches with `kg_chunks`, deterministic graph queries "
        "with `kg_query`, bundled prompts/templates with `read_file`, and "
        "deliverables with `write_file`.\n"
        "- When `run_script` accepts CLI `args`, the placeholders "
        "`{run_dir}`, `{artifacts}`, and `{skill_dir}` are substituted with "
        "absolute paths so cross-skill renderers can write into this run's "
        "artifacts/ folder without you knowing the absolute layout.\n"
        "- Cite sources by chunk_id (e.g. `chunk-7f3a…`) or entity name in "
        "every claim that came from workspace data. If a chunk_id is not "
        "available, say so explicitly rather than inventing one.\n"
        "- Stop calling tools and produce your final answer once you have "
        "enough evidence. The final assistant message (no tool calls) is "
        "what the user sees.\n"
        "- If a tool returns an error, read the error and adjust — do not "
        "retry the same call unchanged.\n"
    )


def now_ms() -> float:
    return time.monotonic() * 1000.0


def append_transcript(transcript: list[dict[str, Any]], entry: dict[str, Any]) -> None:
    transcript.append(entry)


def persist_transcript(run_dir: Path, transcript: list[dict[str, Any]]) -> None:
    """Write ``transcript.json`` next to ``run.md`` for audit + UI replay."""
    try:
        path = run_dir / "transcript.json"
        path.write_text(
            json.dumps(transcript, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Failed to persist transcript at %s: %s", run_dir, exc)


async def dispatch_tool_call(
    call: ChatToolCall,
    specs_by_name: dict[str, ToolSpec],
    ctx: ToolContext,
) -> tuple[str, dict[str, Any]]:
    """Invoke one tool call. Returns ``(payload_str_for_model, transcript_extra)``."""
    spec = specs_by_name.get(call.name)
    if spec is None:
        err = {"error": f"unknown tool {call.name!r}"}
        return json.dumps(err), {"error": err["error"]}

    try:
        args = json.loads(call.arguments_json or "{}")
        if not isinstance(args, dict):
            raise ValueError("arguments must be a JSON object")
    except (ValueError, json.JSONDecodeError) as exc:
        err = {"error": f"invalid arguments JSON: {exc}", "raw": call.arguments_json}
        return json.dumps(err), {"error": err["error"]}

    try:
        result = await spec.handler(ctx, **args)
    except ToolError as exc:
        err = {"error": str(exc)}
        return json.dumps(err), {"error": str(exc)}
    except TypeError as exc:
        err = {"error": f"argument error: {exc}"}
        return json.dumps(err), {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        logger.exception("tool %s raised unexpectedly", call.name)
        err = {"error": f"unhandled tool exception: {exc.__class__.__name__}: {exc}"}
        return json.dumps(err), {"error": str(exc)}

    payload_str = serialize_tool_payload_for_model(result)
    extra = {"truncated": result.truncated, **(result.transcript_extra or {})}
    return payload_str, extra