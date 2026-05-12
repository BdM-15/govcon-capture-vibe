"""Multi-turn tool-calling loop for the skill runtime.

The runtime takes a parsed skill, a user prompt, and a wired
:class:`~src.skills.tools.ToolContext`, and runs a chat completion loop
against the configured LLM until the model emits a final answer (no more
tool calls) or hits the turn cap.

Every turn — assistant message, tool call, tool response — is appended to
``transcript.json`` so the run can be replayed/audited. The final assistant
message is returned as the skill response.

This module is pure runtime: discovery, frontmatter parsing, persistence
metadata, and route wiring all live elsewhere.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.skills.llm_chat import ChatResponse, ChatToolCall, chat_with_tools
from src.skills.tool_registry import ToolSpec
from src.skills.tool_types import ToolError
from src.skills.tools import (
    ToolContext,
    build_mcp_tool_specs,
    build_tool_specs,
    serialize_tool_payload_for_model,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Support helpers (inlined from runtime_support)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


async def run_tool_loop(
    *,
    skill_name: str,
    skill_body: str,
    user_prompt: str,
    ctx: ToolContext,
    max_turns: int = 12,
    temperature: float = 0.2,
) -> ToolLoopResult:
    """Drive the model through a tool-calling loop and return its final answer.

    Args:
        skill_name: Skill slug (used in logs + the system prompt).
        skill_body: SKILL.md body verbatim — becomes the authoritative
            workflow contract in the system message.
        user_prompt: The user's request (may be empty for default-trigger
            skills).
        ctx: Wired :class:`ToolContext` (skill_dir, run_dir, KG bindings).
        max_turns: Hard cap on assistant turns (each turn is one model call).
            Default 12 is generous for most skills; set lower for cost
            control.
        temperature: Sampling temperature for the model.

    Returns:
        :class:`ToolLoopResult` with the final answer, full transcript,
        turn/tool-call counts, and aggregate token usage.
    """
    specs = build_tool_specs(skill_name=skill_name)
    if ctx.mcp_sessions:
        # Phase 4a: append one ToolSpec per discovered MCP tool so the model
        # sees them alongside the in-process tools. Naming convention
        # ``mcp__<server>__<tool>`` keeps the namespace collision-free.
        specs.extend(build_mcp_tool_specs(ctx.mcp_sessions))
    specs_by_name = {s.name: s for s in specs}
    tool_schemas = [s.to_openai() for s in specs]

    system_msg = compose_system_prompt(
        skill_name=skill_name,
        skill_body=skill_body,
        workspace_name=ctx.workspace_name,
        tool_names=[s.name for s in specs],
    )
    user_text = (user_prompt or "").strip() or "Run the skill with default behavior."
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_text},
    ]

    transcript: list[dict[str, Any]] = [
        {"kind": "system", "content": system_msg},
        {"kind": "user", "content": user_text},
    ]

    warnings: list[str] = []
    usage_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    tool_calls_total = 0
    final_response = ""
    finish_reason = ""
    turns = 0

    for turn in range(1, max_turns + 1):
        turns = turn
        ctx.call_seq[0] = tool_calls_total
        t0 = now_ms()
        try:
            chat: ChatResponse = await chat_with_tools(
                messages=messages,
                tools=tool_schemas,
                temperature=temperature,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("chat_with_tools failed on turn %d", turn)
            warnings.append(f"chat call failed on turn {turn}: {exc}")
            final_response = (
                f"⚠️ Skill runtime error on turn {turn}: {exc}\n\n"
                "Partial transcript persisted to the run folder."
            )
            finish_reason = "error"
            break

        elapsed_ms = now_ms() - t0
        for k, v in (chat.usage or {}).items():
            usage_total[k] = usage_total.get(k, 0) + int(v or 0)

        append_transcript(
            transcript,
            {
                "kind": "assistant",
                "turn": turn,
                "content": chat.content,
                "tool_calls": [
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments_json}
                    for tc in chat.tool_calls
                ],
                "finish_reason": chat.finish_reason,
                "usage": chat.usage,
                "elapsed_ms": elapsed_ms,
            },
        )
        # Push the assistant message into the conversation so the next turn
        # has the full context the model needs to reference its tool_call_ids.
        messages.append(chat.raw_message)

        if not chat.tool_calls:
            final_response = chat.content or ""
            finish_reason = chat.finish_reason or "stop"
            break

        # Execute every tool call from this turn before looping back.
        for call in chat.tool_calls:
            tool_calls_total += 1
            ctx.call_seq[0] = tool_calls_total
            tool_t0 = now_ms()
            payload_str, extra = await dispatch_tool_call(call, specs_by_name, ctx)
            tool_elapsed = now_ms() - tool_t0
            # Extract chunk-<32hex> ids from the FULL payload before we
            # truncate the preview, so the reasoning drawer can deep-link to
            # the originating chunk even when the id sits past the 500-char
            # cutoff. Required-32-hex shape rejects mid-string truncations.
            _full_chunk_ids: list[str] = []
            try:
                import re as _re
                seen: set[str] = set()
                for m in _re.finditer(r"\bchunk-[a-f0-9]{32}\b", payload_str):
                    cid = m.group(0)
                    if cid not in seen:
                        seen.add(cid)
                        _full_chunk_ids.append(cid)
                        if len(_full_chunk_ids) >= 25:
                            break
            except Exception:
                pass
            append_transcript(
                transcript,
                {
                    "kind": "tool",
                    "turn": turn,
                    "call_id": call.id,
                    "name": call.name,
                    "arguments": call.arguments_json,
                    "elapsed_ms": tool_elapsed,
                    "result_preview": payload_str[:500],
                    "chunk_ids": _full_chunk_ids,
                    "extra": extra,
                },
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.name,
                    "content": payload_str,
                }
            )
        # Persist after each turn so a crash leaves a usable transcript.
        persist_transcript(ctx.run_dir, transcript)

    else:
        # Hit the turn cap without a final answer — force one closing call
        # without tools so the model summarizes what it has.
        warnings.append(f"hit max_turns={max_turns} without final answer; forcing summary")
        try:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "You have reached the tool-call budget. Stop calling tools "
                        "and write the best final answer you can with the evidence "
                        "you have so far."
                    ),
                }
            )
            chat = await chat_with_tools(messages=messages, tools=None, temperature=temperature)
            final_response = chat.content or "(no response)"
            finish_reason = "max_turns"
            for k, v in (chat.usage or {}).items():
                usage_total[k] = usage_total.get(k, 0) + int(v or 0)
            append_transcript(
                transcript,
                {
                    "kind": "assistant",
                    "turn": turns + 1,
                    "content": final_response,
                    "tool_calls": [],
                    "finish_reason": finish_reason,
                    "usage": chat.usage,
                    "forced_summary": True,
                },
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"forced summary failed: {exc}")
            final_response = "⚠️ Skill exhausted its tool budget without a final answer."
            finish_reason = "max_turns_no_summary"

            persist_transcript(ctx.run_dir, transcript)

    return ToolLoopResult(
        response=final_response,
        transcript=transcript,
        turns=turns,
        tool_calls=tool_calls_total,
        finish_reason=finish_reason,
        usage_total=usage_total,
        warnings=warnings,
    )
