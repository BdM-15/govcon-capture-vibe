"""Skill-chaining tool for tools-mode skills."""

from __future__ import annotations

from typing import Any

from src.skills.tool_types import ToolContext, ToolError, ToolResult


async def tool_invoke_skill(
    ctx: ToolContext,
    name: str,
    prompt: str,
    context: dict[str, Any] | None = None,
) -> ToolResult:
    """Invoke one child skill synchronously and return its run summary."""
    if ctx.invoke_skill_fn is None:
        raise ToolError("invoke_skill is not configured for this runtime")
    skill_name = str(name or "").strip()
    if not skill_name:
        raise ToolError("name must be a non-empty skill name")
    if skill_name == ctx.skill_name:
        raise ToolError("invoke_skill cannot invoke the current skill")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ToolError("prompt must be a non-empty string")
    if context is not None and not isinstance(context, dict):
        raise ToolError("context must be an object when provided")
    return await ctx.invoke_skill_fn(skill_name, prompt, context or {})


__all__ = ["tool_invoke_skill"]