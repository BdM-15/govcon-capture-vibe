"""Orchestrate research harness phases after the agentic tool loop."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from src.skills.depth_gate import depth_gate_issues
from src.skills.llm_chat import chat_with_tools
from src.skills.research_harness import (
    ResearchHarnessConfig,
    _is_handoff_json_only,
    build_frame_reflexion_messages,
    build_frame_synthesis_messages,
    build_reflexion_messages,
    build_synthesis_messages,
    frame_artifact_needs_work,
    init_harness_state,
    load_harness_state,
    needs_synthesis,
    save_harness_state,
    write_frame_artifact,
    write_synthesis_artifact,
)
from src.skills.research_plan import close_retrieval_plan
from src.skills.runtime_support import ToolLoopResult, append_transcript, persist_transcript
from src.skills.skill_local_tools import SkillToolsHooks
from src.skills.skill_models import Skill

logger = logging.getLogger(__name__)


def _ensure_minimum_frame_if_available(
    *,
    skill: Skill,
    run_dir: Path,
    workspace_dir: Path,
    warnings: list[str],
    label: str,
) -> None:
    """Run mission_readiness_tools.ensure_minimum_frame only when that module exists."""
    skill_dir = Path(skill.path)
    tools_path = skill_dir / "mission_readiness_tools.py"
    if not tools_path.is_file():
        return
    try:
        from src.skills.skill_local_tools import load_skill_tool_module

        module = load_skill_tool_module(skill_dir, "mission_readiness_tools")
        module.ensure_minimum_frame(run_dir, workspace_dir)
        warnings.append(f"research_harness: {label}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Frame scaffold failed for %s: %s", skill.name, exc)
        warnings.append(f"frame_scaffold_failed: {exc}")


async def run_frame_synthesis_pass(
    *,
    skill: Skill,
    user_prompt: str,
    run_dir: Path,
    config: ResearchHarnessConfig,
    transcript: list[dict[str, Any]],
    workspace_dir: Path | None = None,
    temperature: float = 0.2,
) -> tuple[bool, dict[str, int], list[str]]:
    """Structured JSON synthesis over scratchpad (no tools) when frame is missing or thin."""
    warnings: list[str] = []
    if not config.frame_artifact:
        return False, {}, warnings

    messages = build_frame_synthesis_messages(
        skill_name=skill.name,
        skill_body=skill.body_md,
        user_prompt=user_prompt,
        run_dir=run_dir,
        config=config,
    )
    chat = await chat_with_tools(
        messages=messages,
        tools=None,
        temperature=temperature,
        max_tokens=config.reflexion_max_tokens,
    )
    content = (chat.content or "").strip()
    if not content:
        warnings.append("research_harness: frame synthesis pass returned empty content")
        return False, chat.usage or {}, warnings

    written = write_frame_artifact(run_dir, config, content, workspace_dir=workspace_dir)
    if written is None:
        warnings.append("research_harness: frame synthesis pass could not parse JSON")
        return False, chat.usage or {}, warnings

    append_transcript(
        transcript,
        {
            "kind": "synthesis",
            "phase": "synthesize_frame",
            "artifact": config.frame_artifact,
            "content_preview": content[:500],
            "bytes": len(content.encode("utf-8")),
            "usage": chat.usage,
        },
    )
    persist_transcript(run_dir, transcript)
    warnings.append(f"research_harness: frame synthesis pass wrote {config.frame_artifact}")
    usage = {key: int(value or 0) for key, value in (chat.usage or {}).items()}
    return True, usage, warnings


async def run_synthesis_pass(
    *,
    skill: Skill,
    user_prompt: str,
    run_dir: Path,
    config: ResearchHarnessConfig,
    transcript: list[dict[str, Any]],
    temperature: float = 0.25,
) -> tuple[str, dict[str, int], list[str]]:
    """Long-form synthesis completion over accumulated scratchpad (no tools)."""
    warnings: list[str] = []
    messages = build_synthesis_messages(
        skill_name=skill.name,
        skill_body=skill.body_md,
        user_prompt=user_prompt,
        run_dir=run_dir,
        config=config,
    )
    chat = await chat_with_tools(
        messages=messages,
        tools=None,
        temperature=temperature,
        max_tokens=config.synthesis_max_tokens,
    )
    content = (chat.content or "").strip()
    if not content:
        warnings.append("research_harness: synthesis pass returned empty content")
        return "", chat.usage or {}, warnings

    write_synthesis_artifact(run_dir, config, content)
    append_transcript(
        transcript,
        {
            "kind": "synthesis",
            "phase": "synthesize",
            "content_preview": content[:500],
            "bytes": len(content.encode("utf-8")),
            "usage": chat.usage,
        },
    )
    persist_transcript(run_dir, transcript)
    warnings.append("research_harness: synthesis pass wrote " + config.synthesis_artifact)
    usage = {key: int(value or 0) for key, value in (chat.usage or {}).items()}
    return content, usage, warnings


async def run_reflexion_pass(
    *,
    skill: Skill,
    user_prompt: str,
    run_dir: Path,
    config: ResearchHarnessConfig,
    issues: list[str],
    transcript: list[dict[str, Any]],
    pass_index: int,
    workspace_dir: Path | None = None,
    temperature: float = 0.25,
) -> tuple[str, dict[str, int], list[str]]:
    """Reflexion revise pass — expand deliverable to fix depth-audit issues."""
    warnings: list[str] = []
    messages = build_reflexion_messages(
        skill_name=skill.name,
        skill_body=skill.body_md,
        user_prompt=user_prompt,
        run_dir=run_dir,
        config=config,
        issues=issues,
    )
    chat = await chat_with_tools(
        messages=messages,
        tools=None,
        temperature=temperature,
        max_tokens=config.reflexion_max_tokens,
    )
    content = (chat.content or "").strip()
    if not content:
        warnings.append(f"research_harness: reflexion pass {pass_index} returned empty content")
        return "", chat.usage or {}, warnings

    from src.skills.mission_readiness_merge import is_compiler_run_dir
    from src.skills.research_harness import (
        apply_section_patches_to_brief,
        brief_structure_preserved,
        parse_compiler_section_patches,
    )

    json_handoff = config.synthesis_artifact.endswith(".json")
    if is_compiler_run_dir(run_dir) and not json_handoff:
        original = (run_dir / "artifacts" / config.synthesis_artifact).read_text(
            encoding="utf-8",
            errors="replace",
        )
        patches = parse_compiler_section_patches(content)
        if not patches:
            warnings.append(
                f"research_harness: compiler reflexion pass {pass_index} returned no "
                "section_patches — full rewrite rejected"
            )
            return "", chat.usage or {}, warnings
        merged = apply_section_patches_to_brief(original, patches)
        preserved, reason = brief_structure_preserved(original, merged)
        if not preserved:
            warnings.append(
                f"research_harness: compiler reflexion pass {pass_index} rejected — {reason}"
            )
            return "", chat.usage or {}, warnings
        write_synthesis_artifact(run_dir, config, merged)
        content = merged
    elif json_handoff:
        written = write_frame_artifact(run_dir, config, content, workspace_dir=workspace_dir)
        if written is None:
            warnings.append(
                f"research_harness: reflexion pass {pass_index} could not parse JSON handoff"
            )
            return "", chat.usage or {}, warnings
    else:
        write_synthesis_artifact(run_dir, config, content)
    state = load_harness_state(run_dir)
    if state:
        state["reflexion_passes"] = int(state.get("reflexion_passes") or 0) + 1
        save_harness_state(run_dir, state)

    append_transcript(
        transcript,
        {
            "kind": "reflexion",
            "phase": "revise",
            "pass": pass_index,
            "issues": issues[:12],
            "content_preview": content[:500],
            "bytes": len(content.encode("utf-8")),
            "usage": chat.usage,
        },
    )
    persist_transcript(run_dir, transcript)
    warnings.append(f"research_harness: reflexion pass {pass_index} revised {config.synthesis_artifact}")
    usage = {key: int(value or 0) for key, value in (chat.usage or {}).items()}
    return content, usage, warnings


async def run_frame_reflexion_pass(
    *,
    skill: Skill,
    user_prompt: str,
    run_dir: Path,
    config: ResearchHarnessConfig,
    issues: list[str],
    transcript: list[dict[str, Any]],
    pass_index: int,
    workspace_dir: Path | None = None,
    temperature: float = 0.2,
) -> tuple[bool, dict[str, int], list[str]]:
    """Reflexion pass for structured JSON when brief revise alone leaves depth gaps."""
    warnings: list[str] = []
    if not config.frame_artifact:
        return False, {}, warnings

    messages = build_frame_reflexion_messages(
        skill_name=skill.name,
        skill_body=skill.body_md,
        user_prompt=user_prompt,
        run_dir=run_dir,
        config=config,
        issues=issues,
    )
    chat = await chat_with_tools(
        messages=messages,
        tools=None,
        temperature=temperature,
        max_tokens=config.reflexion_max_tokens,
    )
    content = (chat.content or "").strip()
    if not content:
        warnings.append(f"research_harness: frame reflexion pass {pass_index} returned empty content")
        return False, chat.usage or {}, warnings

    written = write_frame_artifact(run_dir, config, content, workspace_dir=workspace_dir)
    if written is None:
        warnings.append(
            f"research_harness: frame reflexion pass {pass_index} could not parse JSON"
        )
        return False, chat.usage or {}, warnings

    append_transcript(
        transcript,
        {
            "kind": "reflexion",
            "phase": "revise_frame",
            "pass": pass_index,
            "issues": issues[:12],
            "artifact": config.frame_artifact,
            "bytes": len(content.encode("utf-8")),
            "usage": chat.usage,
        },
    )
    persist_transcript(run_dir, transcript)
    warnings.append(
        f"research_harness: frame reflexion pass {pass_index} revised {config.frame_artifact}"
    )
    usage = {key: int(value or 0) for key, value in (chat.usage or {}).items()}
    return True, usage, warnings


def _merge_usage(total: dict[str, int], extra: dict[str, int]) -> dict[str, int]:
    merged = dict(total)
    for key, value in extra.items():
        merged[key] = merged.get(key, 0) + int(value or 0)
    return merged


async def seed_harness_bootstrap_retrieval(
    *,
    run_dir: Path,
    config: ResearchHarnessConfig,
    retrieve_fn: Callable[..., Awaitable[dict[str, Any]]],
    user_prompt: str,
    skill_description: str,
    mode: str = "hybrid",
    top_k: int = 40,
) -> list[str]:
    """Run one aquery_data pass and seed research_scratchpad.md before the tool loop."""
    warnings: list[str] = []
    from src.skills.research_harness import append_bootstrap_retrieval

    try:
        payload = await retrieve_fn(user_prompt, skill_description, mode, top_k)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Bootstrap retrieval failed: %s", exc)
        warnings.append(f"bootstrap_retrieval_failed: {exc}")
        return warnings

    meta = payload.get("metadata") or {}
    if not meta.get("used"):
        reason = str(meta.get("reason") or "no grounded context")
        warnings.append(f"bootstrap_retrieval_empty: {reason}")
        return warnings

    query = str(meta.get("retrieval_query") or user_prompt).strip()
    append_bootstrap_retrieval(run_dir, config, payload, query=query)
    warnings.append("research_harness: bootstrap aquery_data seeded scratchpad")
    return warnings


async def finalize_research_harness(
    *,
    skill: Skill,
    user_prompt: str,
    run_dir: Path,
    config: ResearchHarnessConfig,
    hooks: SkillToolsHooks,
    loop_result: ToolLoopResult,
    workspace_dir: Path | None = None,
    entity_payload: dict[str, Any] | None = None,
) -> ToolLoopResult:
    """Run synthesis and reflexion passes after the tool loop when needed."""
    from src.skills.mission_readiness_merge import (
        is_compiler_run_dir,
        persist_normalized_compiler_frame,
        refresh_compiler_claim_gaps_section,
    )

    transcript = list(loop_result.transcript)
    warnings = list(loop_result.warnings)
    usage_total = dict(loop_result.usage_total)
    response = loop_result.response
    compiler_run = is_compiler_run_dir(run_dir)

    try:
        close_retrieval_plan(run_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed closing retrieval plan for %s: %s", skill.name, exc)
        warnings.append(f"close_retrieval_plan_failed: {exc}")

    if workspace_dir is not None and not compiler_run:
        _ensure_minimum_frame_if_available(
            skill=skill,
            run_dir=run_dir,
            workspace_dir=workspace_dir,
            warnings=warnings,
            label="ensured minimum mission_readiness_frame.json shell",
        )

    if config.frame_artifact and frame_artifact_needs_work(run_dir, config) and not compiler_run:
        if isinstance(response, str) and response.strip():
            written = write_frame_artifact(run_dir, config, response, workspace_dir=workspace_dir)
            if written is not None:
                warnings.append(
                    f"research_harness: persisted {config.frame_artifact} from tool-loop response"
                )

    chain_ctx = (entity_payload or {}).get("chain_step_context") or {}
    eval_retrieve_only = bool(chain_ctx.get("eval_retrieve_only"))
    if (
        skill.name == "readiness-frame-eval"
        and workspace_dir is not None
        and not compiler_run
        and not eval_retrieve_only
    ):
        try:
            from src.skills.eval_handoff_expander import expand_eval_handoff

            _, expand_warnings = await expand_eval_handoff(
                run_dir=run_dir,
                workspace_dir=workspace_dir,
                loop_response=str(response or ""),
            )
            warnings.extend(expand_warnings)
            handoff_path = run_dir / "artifacts" / "eval_handoff.json"
            if handoff_path.is_file():
                try:
                    from src.skills.local_llm_admin import (
                        admin_model_configured,
                        expand_acronyms_in_eval_handoff_json,
                    )

                    if admin_model_configured():
                        original = handoff_path.read_text(encoding="utf-8", errors="replace")
                        revised = await expand_acronyms_in_eval_handoff_json(original)
                        if revised.strip() and revised != original:
                            handoff_path.write_text(revised, encoding="utf-8")
                            warnings.append(
                                "readiness-frame-eval: admin_llm expanded acronyms in eval_handoff.json"
                            )
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"admin_llm_eval_handoff_acronym_pass_failed: {exc}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Eval handoff expansion failed for %s: %s", skill.name, exc)
            warnings.append(f"eval_handoff_expander_failed: {exc}")

    if frame_artifact_needs_work(run_dir, config) and not compiler_run:
        try:
            frame_written, usage, frame_synth_warnings = await run_frame_synthesis_pass(
                skill=skill,
                user_prompt=user_prompt,
                run_dir=run_dir,
                config=config,
                transcript=transcript,
                workspace_dir=workspace_dir,
            )
            warnings.extend(frame_synth_warnings)
            usage_total = _merge_usage(usage_total, usage)
            if workspace_dir is not None and not compiler_run:
                _ensure_minimum_frame_if_available(
                    skill=skill,
                    run_dir=run_dir,
                    workspace_dir=workspace_dir,
                    warnings=warnings,
                    label="post frame synthesis scaffold",
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Frame synthesis failed for %s: %s", skill.name, exc)
            warnings.append(f"research_harness frame synthesis failed: {exc}")

    if needs_synthesis(run_dir, config) and not compiler_run:
        try:
            synthesized, usage, synth_warnings = await run_synthesis_pass(
                skill=skill,
                user_prompt=user_prompt,
                run_dir=run_dir,
                config=config,
                transcript=transcript,
            )
            warnings.extend(synth_warnings)
            usage_total = _merge_usage(usage_total, usage)
            if synthesized:
                response = synthesized
        except Exception as exc:  # noqa: BLE001
            logger.warning("Research synthesis failed for %s: %s", skill.name, exc)
            warnings.append(f"research_harness synthesis failed: {exc}")

    from src.skills.research_harness import dedupe_depth_issues

    depth_issues = dedupe_depth_issues(
        depth_gate_issues(run_dir, hooks=hooks, user_prompt=user_prompt)
    )
    frame_missing = frame_artifact_needs_work(run_dir, config) or any(
        f"missing artifacts/{config.frame_artifact}" in issue
        for issue in depth_issues
        if config.frame_artifact
    )
    reflexion_pass = 0
    handoff_json_only = _is_handoff_json_only(config.deliverables)

    if depth_issues and config.frame_artifact and frame_missing and not compiler_run:
        frame_pass = 0
        while depth_issues and frame_pass < 3:
            frame_pass += 1
            try:
                frame_revised, usage, frame_warnings = await run_frame_reflexion_pass(
                    skill=skill,
                    user_prompt=user_prompt,
                    run_dir=run_dir,
                    config=config,
                    issues=depth_issues,
                    transcript=transcript,
                    pass_index=frame_pass,
                    workspace_dir=workspace_dir,
                )
                warnings.extend(frame_warnings)
                usage_total = _merge_usage(usage_total, usage)
                if frame_revised:
                    depth_issues = depth_gate_issues(
                        run_dir, hooks=hooks, user_prompt=user_prompt
                    )
                    frame_missing = any(
                        "mission_readiness_frame.json" in issue for issue in depth_issues
                    )
                else:
                    break
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Research frame reflexion failed for %s pass %d: %s",
                    skill.name,
                    frame_pass,
                    exc,
                )
                warnings.append(f"research_harness frame reflexion failed: {exc}")
                break

    if workspace_dir is not None and not compiler_run:
        _ensure_minimum_frame_if_available(
            skill=skill,
            run_dir=run_dir,
            workspace_dir=workspace_dir,
            warnings=warnings,
            label="pre brief reflexion scaffold",
        )
        from src.skills.research_harness import dedupe_depth_issues

    depth_issues = dedupe_depth_issues(
        depth_gate_issues(run_dir, hooks=hooks, user_prompt=user_prompt)
    )

    while (
        depth_issues
        and reflexion_pass < config.max_reflexion_passes
        and not handoff_json_only
        and not compiler_run
    ):
        reflexion_pass += 1
        try:
            revised, usage, rev_warnings = await run_reflexion_pass(
                skill=skill,
                user_prompt=user_prompt,
                run_dir=run_dir,
                config=config,
                issues=depth_issues,
                transcript=transcript,
                pass_index=reflexion_pass,
                workspace_dir=workspace_dir,
            )
            warnings.extend(rev_warnings)
            usage_total = _merge_usage(usage_total, usage)
            if revised:
                response = revised
        except Exception as exc:  # noqa: BLE001
            logger.warning("Research reflexion failed for %s pass %d: %s", skill.name, reflexion_pass, exc)
            warnings.append(f"research_harness reflexion failed: {exc}")
            break
        from src.skills.research_harness import dedupe_depth_issues

    depth_issues = dedupe_depth_issues(
        depth_gate_issues(run_dir, hooks=hooks, user_prompt=user_prompt)
    )

    if depth_issues and config.frame_artifact and not compiler_run:
        frame_pass = 0
        while depth_issues and frame_pass < 3:
            frame_pass += 1
            try:
                frame_revised, usage, frame_warnings = await run_frame_reflexion_pass(
                    skill=skill,
                    user_prompt=user_prompt,
                    run_dir=run_dir,
                    config=config,
                    issues=depth_issues,
                    transcript=transcript,
                    pass_index=reflexion_pass + frame_pass,
                    workspace_dir=workspace_dir,
                )
                warnings.extend(frame_warnings)
                usage_total = _merge_usage(usage_total, usage)
                if frame_revised:
                    depth_issues = depth_gate_issues(
                        run_dir, hooks=hooks, user_prompt=user_prompt
                    )
                else:
                    break
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Research frame reflexion failed for %s pass %d: %s",
                    skill.name,
                    frame_pass,
                    exc,
                )
                warnings.append(f"research_harness frame reflexion failed: {exc}")
                break

    if compiler_run:
        from src.skills.compiler_mode import compiler_brief_llm_enabled
        from src.skills.mission_readiness_merge import write_compiler_brief_scaffold
        from src.skills.platform_step_finalize import repair_compiler_artifacts

        if persist_normalized_compiler_frame(run_dir):
            warnings.append("compiler_mode: re-normalized mission_readiness_frame.json from handoffs")
        write_compiler_brief_scaffold(run_dir)
        refresh_compiler_claim_gaps_section(run_dir)
        repair_compiler_artifacts(run_dir)
        warnings.append("compiler_mode: deterministic brief from merged handoffs")

    if workspace_dir is not None and not compiler_run:
        _ensure_minimum_frame_if_available(
            skill=skill,
            run_dir=run_dir,
            workspace_dir=workspace_dir,
            warnings=warnings,
            label="final frame scaffold",
        )

    from src.skills.research_harness import dedupe_depth_issues

    depth_issues = dedupe_depth_issues(
        depth_gate_issues(run_dir, hooks=hooks, user_prompt=user_prompt)
    )
    if compiler_run and depth_issues and compiler_brief_llm_enabled():
        acronym_issues = [
            issue
            for issue in depth_issues
            if "undefined acronyms" in issue.lower()
        ]
        if acronym_issues:
            try:
                from src.skills.local_llm_admin import (
                    admin_model_configured,
                    build_admin_chat_fn,
                    expand_acronyms_in_text,
                )

                if admin_model_configured():
                    brief_path = run_dir / "artifacts" / config.synthesis_artifact
                    if brief_path.is_file():
                        original = brief_path.read_text(encoding="utf-8", errors="replace")
                        admin_chat = await build_admin_chat_fn()
                        revised = await expand_acronyms_in_text(
                            original,
                            chat_fn=admin_chat,
                        )
                        if revised.strip() and revised != original:
                            brief_path.write_text(revised, encoding="utf-8")
                            warnings.append("compiler_mode: admin_llm expanded acronyms in brief")
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"admin_llm_acronym_pass_failed: {exc}")

        polish_pass = 0
        max_polish_passes = config.max_reflexion_passes
        while depth_issues and polish_pass < max_polish_passes:
            polish_pass += 1
            try:
                revised, usage, rev_warnings = await run_reflexion_pass(
                    skill=skill,
                    user_prompt=user_prompt,
                    run_dir=run_dir,
                    config=config,
                    issues=depth_issues,
                    transcript=transcript,
                    pass_index=reflexion_pass + polish_pass,
                )
                warnings.extend(rev_warnings)
                usage_total = _merge_usage(usage_total, usage)
                if revised:
                    response = revised
                refresh_compiler_claim_gaps_section(run_dir)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"compiler acronym reflexion failed: {exc}")
                break
            from src.skills.research_harness import dedupe_depth_issues

    depth_issues = dedupe_depth_issues(
        depth_gate_issues(run_dir, hooks=hooks, user_prompt=user_prompt)
    )

    finish_reason = loop_result.finish_reason
    if depth_issues:
        _BLOCKING_MARKERS = (
            "missing mission_readiness_frame.json",
            "eval_crosswalk is empty",
            "invalid source_chunk_ids",
            "invented shorthand",
            "formulaic shorthand",
            "compressed",
            "does not reflect claim_gaps",
            "boilerplate",
            "undefined acronyms",
            "over-relies on one source chunk",
            "narrative sections lack numbered citation",
            "verbatim_extracts is empty",
            "eval_crosswalk under-covers",
        )
        markers = _BLOCKING_MARKERS
        if handoff_json_only:
            markers = tuple(
                marker for marker in _BLOCKING_MARKERS if marker != "undefined acronyms"
            )
        blocking = [
            issue
            for issue in depth_issues
            if issue.startswith("coverage:")
            or any(marker in issue.lower() for marker in markers)
        ]
        if not blocking:
            finish_reason = loop_result.finish_reason or "complete"
        else:
            finish_reason = "depth_incomplete"

    try:
        from src.skills.run_forensics import write_run_forensics

        write_run_forensics(run_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed writing retrieval forensics for %s: %s", skill.name, exc)
        warnings.append(f"retrieval_forensics_write_failed: {exc}")

    if workspace_dir is not None:
        try:
            from src.skills.research_auditor import audit_skill_run
            from src.skills.research_harness import _read_artifact

            from src.skills.research_harness import research_harness_overrides

            coverage_contract = research_harness_overrides(
                skill.frontmatter.metadata or {}
            ).get("coverage_contract")
            scratchpad = _read_artifact(run_dir, "research_scratchpad.md", max_chars=80_000)
            verdict = await audit_skill_run(
                run_dir=run_dir,
                workspace_dir=workspace_dir,
                coverage_contract=coverage_contract,
                skill_task=user_prompt,
                scratchpad_excerpt=scratchpad,
            )
            if not verdict.get("pass"):
                for issue in verdict.get("issues") or []:
                    warnings.append(f"audit: {issue}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Research audit failed for %s: %s", skill.name, exc)
            warnings.append(f"research_audit_failed: {exc}")

    return ToolLoopResult(
        response=response,
        transcript=transcript,
        turns=loop_result.turns,
        tool_calls=loop_result.tool_calls,
        finish_reason=finish_reason,
        usage_total=usage_total,
        warnings=warnings,
    )


def prepare_research_harness(
    *,
    run_dir: Path,
    config: ResearchHarnessConfig,
) -> None:
    """Initialize harness artifacts for a new run."""
    init_harness_state(run_dir, config)


def make_tool_result_recorder(
    run_dir: Path,
    config: ResearchHarnessConfig,
) -> Callable[[str, str, str], None]:
    """Return a callback that records kg/web tool output into the scratchpad."""

    def _record(
        tool_name: str,
        arguments_json: str,
        payload_str: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        from src.skills.research_harness import record_tool_retrieval

        full_payload = (extra or {}).get("harness_payload") or payload_str
        record_tool_retrieval(
            run_dir,
            tool_name=tool_name,
            arguments_json=arguments_json,
            payload_str=full_payload,
            config=config,
        )

    return _record