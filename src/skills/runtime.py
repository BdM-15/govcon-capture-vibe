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
from typing import Any

from src.skills.llm_chat import ChatResponse, ChatToolCall, chat_with_tools
from src.skills.runtime_support import (
    ToolLoopResult,
    append_transcript,
    compose_system_prompt,
    dispatch_tool_call,
    now_ms,
    persist_transcript,
)
from src.skills.tools import (
    ToolContext,
    build_mcp_tool_specs,
    build_tool_specs,
)

logger = logging.getLogger(__name__)


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
