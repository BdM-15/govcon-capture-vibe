"""DAG wave execution for Theseus skill chains (parallel steps within a wave)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from src.skills.chain_dag import (
    all_steps_terminal,
    compute_execution_waves,
    ready_step_ids,
    transitive_dependent_ids,
)
from src.skills.chain_models import (
    ChainArtifactRef,
    ChainArtifactRequirement,
    ChainRunState,
    ChainSpec,
    ChainStepRun,
    ChainStepSpec,
    utc_now_iso,
)
from src.skills.chain_step_gates import apply_step_quality_gate
from src.skills.skill_models import SkillInvocationResult


InvokeSkillCallable = Callable[..., Awaitable[SkillInvocationResult]]


@dataclass(frozen=True)
class _StepExecutionOutcome:
    step_id: str
    result: SkillInvocationResult | None = None
    error: str = ""
    contract_errors: list[str] | None = None


class SkillChainExecutor:
    """Execute a validated chain spec with parallel DAG waves and per-step checkpointing."""

    _OUTCOME_FORMAT_HINTS: dict[str, tuple[str, ...]] = {
        "docx": ("docx", "word", "brief", "document", "draft", "report"),
        "xlsx": ("xlsx", "excel", "workbook", "spreadsheet"),
        "pptx": ("pptx", "powerpoint", "deck", "slides", "presentation"),
        "pdf": ("pdf",),
        "html": ("html", "web"),
        "gif": ("gif",),
        "mp4": ("mp4", "video"),
    }

    def __init__(
        self,
        *,
        invoke_skill: InvokeSkillCallable,
        run_store: Any,
    ) -> None:
        self._invoke_skill = invoke_skill
        self._run_store = run_store

    async def invoke(
        self,
        spec: ChainSpec,
        *,
        workspace: str,
        workspace_root: Path,
        llm: Callable[[str], Awaitable[str]],
        entity_payload: dict[str, Any] | None = None,
        max_payload_chars: Optional[int] = None,
        slice_fn: Optional[Callable[..., dict[str, Any]]] = None,
        retrieve_fn: Optional[Callable[..., Awaitable[dict[str, Any]]]] = None,
        runtime_mode_override: Optional[str] = None,
        source_chain_id: str = "",
        mode: str = "original",
    ) -> ChainRunState:
        chain_id, chain_dir = self._run_store.create_chain_run(
            workspace_root=workspace_root,
            name=spec.name,
            prompt=spec.prompt,
        )
        initial = ChainRunState(
            chain_id=chain_id,
            workspace=workspace,
            status="running",
            mode=mode,
            source_chain_id=source_chain_id,
            spec=spec,
            steps={
                step.id: ChainStepRun(id=step.id, skill=step.skill)
                for step in spec.steps
            },
        )
        self._write_execution_plan(chain_dir, spec)
        self._run_store.write_chain_run(chain_dir, initial.model_dump())

        return await self._run_steps(
            initial,
            chain_dir=chain_dir,
            workspace=workspace,
            workspace_root=workspace_root,
            llm=llm,
            entity_payload=entity_payload or {},
            max_payload_chars=max_payload_chars,
            slice_fn=slice_fn,
            retrieve_fn=retrieve_fn,
            runtime_mode_override=runtime_mode_override,
        )

    async def resume(
        self,
        chain: ChainRunState,
        *,
        workspace_root: Path,
        llm: Callable[[str], Awaitable[str]],
        entity_payload: dict[str, Any] | None = None,
        max_payload_chars: Optional[int] = None,
        slice_fn: Optional[Callable[..., dict[str, Any]]] = None,
        retrieve_fn: Optional[Callable[..., Awaitable[dict[str, Any]]]] = None,
        runtime_mode_override: Optional[str] = None,
        from_step_id: str = "",
        resume_notes: str = "",
    ) -> ChainRunState:
        chain_dir = self._run_store.chain_run_dir(workspace_root, chain.chain_id)
        if not chain_dir.is_dir():
            raise FileNotFoundError(f"Unknown chain: {chain.chain_id}")

        resume_state = self._reset_for_resume(
            chain,
            from_step_id=from_step_id,
            resume_notes=resume_notes,
        )
        self._run_store.write_chain_run(chain_dir, resume_state.model_dump())
        return await self._run_steps(
            resume_state,
            chain_dir=chain_dir,
            workspace=resume_state.workspace,
            workspace_root=workspace_root,
            llm=llm,
            entity_payload=entity_payload or {},
            max_payload_chars=max_payload_chars,
            slice_fn=slice_fn,
            retrieve_fn=retrieve_fn,
            runtime_mode_override=runtime_mode_override,
        )

    @staticmethod
    def _write_execution_plan(chain_dir: Path, spec: ChainSpec) -> None:
        waves = compute_execution_waves(spec)
        payload = {
            "waves": waves,
            "parallelism": max((len(wave) for wave in waves), default=1),
            "step_count": len(spec.steps),
        }
        chain_dir.mkdir(parents=True, exist_ok=True)
        (chain_dir / "execution_plan.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def _run_steps(
        self,
        chain: ChainRunState,
        *,
        chain_dir: Path,
        workspace: str,
        workspace_root: Path,
        llm: Callable[[str], Awaitable[str]],
        entity_payload: dict[str, Any],
        max_payload_chars: Optional[int],
        slice_fn: Optional[Callable[..., dict[str, Any]]],
        retrieve_fn: Optional[Callable[..., Awaitable[dict[str, Any]]]],
        runtime_mode_override: Optional[str],
    ) -> ChainRunState:
        blocked = False

        while not all_steps_terminal(chain.steps):
            if blocked:
                self._skip_pending_steps(chain, reason="chain blocked by earlier failure")
                chain.updated_at = utc_now_iso()
                self._finalize_if_terminal(chain, chain.updated_at)
                self._run_store.write_chain_run(chain_dir, chain.model_dump())
                break

            ready_ids = ready_step_ids(chain.spec, chain.steps)
            if not ready_ids:
                pending = [
                    step_id
                    for step_id, run in chain.steps.items()
                    if run.status == "pending"
                ]
                chain.status = "failed"
                chain.error = (
                    "chain deadlock: pending steps have unsatisfied dependencies: "
                    + ", ".join(pending)
                )
                chain.updated_at = utc_now_iso()
                self._skip_pending_steps(chain, reason=chain.error)
                self._finalize_if_terminal(chain, chain.updated_at)
                self._run_store.write_chain_run(chain_dir, chain.model_dump())
                break

            ready_steps = [
                step for step in chain.spec.steps if step.id in ready_ids
            ]
            for step in ready_steps:
                step_run = chain.steps[step.id]
                input_artifacts, contract_errors = self._resolve_input_artifacts(
                    chain, step
                )
                step_run.input_artifacts = input_artifacts
                if contract_errors:
                    step_run.status = "failed"
                    step_run.error = "; ".join(contract_errors)
                    step_run.finished_at = utc_now_iso()
                    chain.status = "failed"
                    chain.error = (
                        f"step {step.id} artifact contract failed: {step_run.error}"
                    )
                    chain.updated_at = step_run.finished_at
                    self._finalize_if_terminal(chain, step_run.finished_at)
                    self._run_store.write_chain_run(chain_dir, chain.model_dump())
                    blocked = chain.spec.stop_on_error
                    break
                step_run.status = "running"
                step_run.started_at = utc_now_iso()

            if blocked:
                continue

            chain.updated_at = utc_now_iso()
            self._run_store.write_chain_run(chain_dir, chain.model_dump())

            outcomes = await asyncio.gather(
                *[
                    self._execute_step(
                        chain,
                        step=step,
                        workspace=workspace,
                        workspace_root=workspace_root,
                        entity_payload=entity_payload,
                        llm=llm,
                        max_payload_chars=max_payload_chars,
                        slice_fn=slice_fn,
                        retrieve_fn=retrieve_fn,
                        runtime_mode_override=runtime_mode_override,
                    )
                    for step in ready_steps
                    if chain.steps[step.id].status == "running"
                ]
            )

            wave_failed = False
            for outcome in outcomes:
                step_run = chain.steps[outcome.step_id]
                if outcome.contract_errors:
                    step_run.status = "failed"
                    step_run.error = "; ".join(outcome.contract_errors)
                    step_run.finished_at = utc_now_iso()
                    wave_failed = True
                    chain.status = "failed"
                    chain.error = (
                        f"step {outcome.step_id} artifact contract failed: {step_run.error}"
                    )
                    continue
                if outcome.error:
                    step_run.status = "failed"
                    step_run.error = outcome.error
                    step_run.finished_at = utc_now_iso()
                    wave_failed = True
                    chain.status = "failed"
                    chain.error = f"step {outcome.step_id} failed: {outcome.error}"
                    continue
                if outcome.result is None:
                    step_run.status = "failed"
                    step_run.error = "step returned no result"
                    step_run.finished_at = utc_now_iso()
                    wave_failed = True
                    chain.status = "failed"
                    chain.error = f"step {outcome.step_id} failed: no result"
                    continue

                result = outcome.result
                step_run.status = "completed"
                step_run.run_id = result.run_id
                step_run.run_dir = result.run_dir
                step_run.response_preview = result.response[:2000]
                step_run.warnings = list(result.warnings or [])
                step_run.elapsed_ms = result.elapsed_ms
                step_run.finished_at = utc_now_iso()
                if result.run_id:
                    detail = self._run_store.get_run(
                        workspace_root, step_run.skill, result.run_id
                    )
                    if detail:
                        step_run.artifacts = list(detail.get("artifacts") or [])
                step_run.missing_inputs = self._extract_missing_inputs(result.response)
                step_run.missing_outputs = self._extract_missing_outputs(
                    step_run.artifacts
                )
                if apply_step_quality_gate(
                    step_run,
                    finish_reason=result.finish_reason,
                    warnings=list(result.warnings or []),
                    workspace_root=workspace_root,
                ):
                    wave_failed = True
                    chain.status = "failed"
                    chain.error = f"step {outcome.step_id} quality gate failed: {step_run.error}"
                elif step_run.missing_inputs or step_run.missing_outputs:
                    step_run.status = "partial"

            chain.updated_at = utc_now_iso()
            self._finalize_if_terminal(chain, chain.updated_at)
            self._run_store.write_chain_run(chain_dir, chain.model_dump())
            if wave_failed and chain.spec.stop_on_error:
                blocked = True

        return chain

    async def _execute_step(
        self,
        chain: ChainRunState,
        *,
        step: ChainStepSpec,
        workspace: str,
        workspace_root: Path,
        entity_payload: dict[str, Any],
        llm: Callable[[str], Awaitable[str]],
        max_payload_chars: Optional[int],
        slice_fn: Optional[Callable[..., dict[str, Any]]],
        retrieve_fn: Optional[Callable[..., Awaitable[dict[str, Any]]]],
        runtime_mode_override: Optional[str],
    ) -> _StepExecutionOutcome:
        step_run = chain.steps[step.id]
        input_artifacts = list(step_run.input_artifacts)
        try:
            step_payload = self._build_step_entity_payload(
                entity_payload,
                input_artifacts=input_artifacts,
                step_context=step.context,
            )
            result = await self._invoke_skill(
                step.skill,
                workspace=workspace,
                user_prompt=self._compose_step_prompt(chain, step),
                entity_payload=step_payload,
                llm=llm,
                max_payload_chars=max_payload_chars,
                workspace_root=workspace_root,
                slice_fn=slice_fn,
                retrieve_fn=retrieve_fn,
                runtime_mode_override=runtime_mode_override,
                _chain_depth=1,
                _chain=(step.skill,),
            )
        except Exception as exc:  # noqa: BLE001
            return _StepExecutionOutcome(step_id=step.id, error=str(exc))
        return _StepExecutionOutcome(step_id=step.id, result=result)

    @staticmethod
    def _skip_pending_steps(chain: ChainRunState, *, reason: str) -> None:
        for run in chain.steps.values():
            if run.status == "pending":
                run.status = "skipped"
                run.error = reason

    @staticmethod
    def _reset_for_resume(
        chain: ChainRunState,
        *,
        from_step_id: str = "",
        resume_notes: str = "",
    ) -> ChainRunState:
        if from_step_id and from_step_id not in chain.steps:
            raise ValueError(f"Unknown chain step: {from_step_id}")
        resume = chain.model_copy(deep=True)
        invalidate: set[str] = set()
        if from_step_id:
            invalidate.add(from_step_id)
            invalidate.update(transitive_dependent_ids(resume.spec, from_step_id))
        else:
            for step in resume.spec.steps:
                current = resume.steps[step.id]
                if current.status != "completed":
                    invalidate.add(step.id)

        for step_id in invalidate:
            step = next(item for item in resume.spec.steps if item.id == step_id)
            resume.steps[step_id] = ChainStepRun(id=step_id, skill=step.skill)

        resume.status = "running"
        resume.mode = "resume"
        resume.source_chain_id = resume.source_chain_id or resume.chain_id
        resume.promoted_artifacts = []
        resume.missing_inputs = []
        resume.missing_outputs = []
        resume.input_request = {}
        resume.resume_notes = (resume_notes or "").strip()
        resume.error = ""
        resume.finished_at = ""
        resume.updated_at = utc_now_iso()
        return resume

    @classmethod
    def _resolve_input_artifacts(
        cls,
        chain: ChainRunState,
        step: ChainStepSpec,
    ) -> tuple[list[ChainArtifactRef], list[str]]:
        refs = list(step.input_artifacts)
        errors: list[str] = []
        upstream_ids = [
            step_id
            for step_id, run in chain.steps.items()
            if run.status in {"completed", "partial"} and step_id != step.id
        ]

        if not step.artifact_requirements:
            source_ids = step.depends_on or upstream_ids
            refs.extend(cls._artifact_refs_for_steps(chain, source_ids))
            return cls._dedupe_artifacts(refs), []

        for requirement in step.artifact_requirements:
            source_ids = requirement.from_steps or step.depends_on or upstream_ids
            candidates = cls._artifact_refs_for_steps(chain, source_ids)
            matched = [
                artifact
                for artifact in candidates
                if cls._artifact_matches_requirement(artifact, requirement)
            ]
            refs.extend(matched)
            if requirement.required and len(matched) < requirement.min_count:
                errors.append(
                    f"artifact requirement {requirement.id} expected "
                    f">={requirement.min_count}, found {len(matched)}"
                )
        return cls._dedupe_artifacts(refs), errors

    @staticmethod
    def _artifact_refs_for_steps(
        chain: ChainRunState,
        step_ids: list[str],
    ) -> list[ChainArtifactRef]:
        refs: list[ChainArtifactRef] = []
        for step_id in step_ids:
            run = chain.steps.get(step_id)
            if not run or not run.run_id:
                continue
            for artifact in run.artifacts:
                filename = str(artifact.get("filename") or artifact.get("name") or "")
                if not filename:
                    continue
                try:
                    size = int(artifact.get("size") or 0)
                except (TypeError, ValueError):
                    size = 0
                products = [
                    str(product).strip().lower()
                    for product in artifact.get("products") or []
                    if str(product).strip()
                ]
                refs.append(
                    ChainArtifactRef(
                        step_id=step_id,
                        skill=run.skill,
                        run_id=run.run_id,
                        filename=filename,
                        path=str(Path(run.run_dir) / "artifacts" / filename) if run.run_dir else "",
                        display_name=str(artifact.get("display_name") or filename),
                        mime=str(artifact.get("mime") or ""),
                        size=size,
                        products=products,
                    )
                )
        return refs

    @staticmethod
    def _artifact_matches_requirement(
        artifact: ChainArtifactRef,
        requirement: ChainArtifactRequirement,
    ) -> bool:
        filename = artifact.filename.lower()
        if requirement.products:
            artifact_products = set(artifact.products)
            if not artifact_products.intersection(requirement.products):
                return False
        if requirement.extensions:
            ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
            if ext not in requirement.extensions:
                return False
        if requirement.mime_types and artifact.mime not in requirement.mime_types:
            return False
        if requirement.name_contains:
            if not all(token.lower() in filename for token in requirement.name_contains):
                return False
        return True

    @staticmethod
    def _dedupe_artifacts(refs: list[ChainArtifactRef]) -> list[ChainArtifactRef]:
        seen: set[tuple[str, str, str]] = set()
        deduped: list[ChainArtifactRef] = []
        for ref in refs:
            key = (ref.step_id, ref.run_id, ref.filename)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(ref)
        return deduped

    @staticmethod
    def _finalize_if_terminal(chain: ChainRunState, finished_at: str) -> None:
        terminal = {"completed", "partial", "failed", "skipped"}
        if not all(run.status in terminal for run in chain.steps.values()):
            return
        chain.promoted_artifacts = SkillChainExecutor._promoted_artifacts(chain)
        chain.missing_inputs = SkillChainExecutor._collect_missing_inputs(chain)
        chain.missing_outputs = SkillChainExecutor._collect_missing_outputs(chain)
        chain.input_request = SkillChainExecutor._build_input_request(chain)
        failed = any(run.status == "failed" for run in chain.steps.values())
        blocked = any(run.status == "skipped" and run.error for run in chain.steps.values())
        partial = (
            any(run.status == "partial" for run in chain.steps.values())
            or bool(chain.missing_inputs)
            or bool(chain.missing_outputs)
        )
        if failed or blocked:
            chain.status = "failed"
        elif partial:
            chain.status = "partial"
        else:
            chain.status = "completed"
        chain.finished_at = finished_at

    @classmethod
    def _collect_missing_inputs(cls, chain: ChainRunState) -> list[str]:
        seen: set[str] = set()
        missing: list[str] = []
        for run in chain.steps.values():
            for item in run.missing_inputs:
                cleaned = str(item).strip()
                if cleaned and cleaned not in seen:
                    seen.add(cleaned)
                    missing.append(cleaned)
        return missing

    @classmethod
    def _collect_missing_outputs(cls, chain: ChainRunState) -> list[str]:
        seen: set[str] = set()
        missing: list[str] = []
        for run in chain.steps.values():
            for item in run.missing_outputs:
                cleaned = str(item).strip().lower()
                if cleaned and cleaned not in seen:
                    seen.add(cleaned)
                    missing.append(cleaned)
        expected = cls._expected_output_formats(chain)
        present = {
            cls._artifact_extension(ref.filename)
            for ref in chain.promoted_artifacts
            if cls._artifact_extension(ref.filename)
        }
        for ext in expected:
            if ext and ext not in present and ext not in seen:
                missing.append(ext)
        return missing

    @staticmethod
    def _build_input_request(chain: ChainRunState) -> dict[str, Any]:
        resume_step_id = ""
        for step in chain.spec.steps:
            run = chain.steps.get(step.id)
            if run and run.status == "partial" and run.missing_inputs:
                resume_step_id = step.id
                return {
                    "needed": True,
                    "step_id": step.id,
                    "skill": run.skill,
                    "missing_inputs": list(run.missing_inputs),
                    "resume_step_id": step.id,
                }
        if chain.missing_inputs:
            return {
                "needed": True,
                "step_id": resume_step_id,
                "skill": "",
                "missing_inputs": list(chain.missing_inputs),
                "resume_step_id": resume_step_id,
            }
        return {}

    @classmethod
    def _promoted_artifacts(cls, chain: ChainRunState) -> list[ChainArtifactRef]:
        expected_formats = cls._expected_output_formats(chain)
        terminal_ids = cls._terminal_step_ids(chain.spec)
        promoted: list[ChainArtifactRef] = []
        for step_id in terminal_ids:
            run = chain.steps.get(step_id)
            if not run or run.status not in {"completed", "partial"}:
                continue
            for artifact in run.artifacts:
                filename = str(artifact.get("filename") or artifact.get("name") or "")
                if not filename:
                    continue
                ext = cls._artifact_extension(filename)
                if expected_formats and ext not in expected_formats:
                    continue
                if ext not in cls._OUTCOME_FORMAT_HINTS:
                    continue
                promoted.append(
                    ChainArtifactRef(
                        step_id=step_id,
                        skill=run.skill,
                        run_id=run.run_id,
                        filename=filename,
                        path=str(Path(run.run_dir) / "artifacts" / filename) if run.run_dir else "",
                        display_name=str(artifact.get("display_name") or filename),
                        mime=str(artifact.get("mime") or ""),
                        size=cls._artifact_size(artifact),
                        products=[
                            str(product).strip().lower()
                            for product in artifact.get("products") or []
                            if str(product).strip()
                        ],
                    )
                )
        if promoted or expected_formats:
            return cls._dedupe_artifacts(promoted)

        fallback: list[ChainArtifactRef] = []
        for step_id in terminal_ids:
            run = chain.steps.get(step_id)
            if not run or run.status not in {"completed", "partial"}:
                continue
            for artifact in run.artifacts:
                filename = str(artifact.get("filename") or artifact.get("name") or "")
                ext = cls._artifact_extension(filename)
                if ext not in cls._OUTCOME_FORMAT_HINTS:
                    continue
                fallback.append(
                    ChainArtifactRef(
                        step_id=step_id,
                        skill=run.skill,
                        run_id=run.run_id,
                        filename=filename,
                        path=str(Path(run.run_dir) / "artifacts" / filename) if run.run_dir else "",
                        display_name=str(artifact.get("display_name") or filename),
                        mime=str(artifact.get("mime") or ""),
                        size=cls._artifact_size(artifact),
                        products=[
                            str(product).strip().lower()
                            for product in artifact.get("products") or []
                            if str(product).strip()
                        ],
                    )
                )
        return cls._dedupe_artifacts(fallback)

    @classmethod
    def _expected_output_formats(cls, chain: ChainRunState) -> list[str]:
        raw = str(chain.spec.context.get("expected_outcome") or "").lower()
        if not raw:
            return []
        expected: list[str] = []
        for ext, hints in cls._OUTCOME_FORMAT_HINTS.items():
            if any(hint in raw for hint in hints):
                expected.append(ext)
        return expected

    @staticmethod
    def _terminal_step_ids(spec: ChainSpec) -> list[str]:
        upstream_ids = {
            dependency
            for step in spec.steps
            for dependency in step.depends_on
        }
        return [step.id for step in spec.steps if step.id not in upstream_ids]

    @staticmethod
    def _artifact_extension(filename: str) -> str:
        return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    @staticmethod
    def _artifact_size(artifact: dict[str, Any]) -> int:
        try:
            return int(artifact.get("size") or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _extract_missing_inputs(response: str) -> list[str]:
        """Parse explicit user-supply gap lists from dedicated sections only."""
        lines = str(response or "").splitlines()
        collecting = False
        missing: list[str] = []
        seen: set[str] = set()
        success_markers = (
            "artifact `",
            "artifact complete",
            "handoff complete",
            "json is ready",
            "json ready for",
            "emitted with",
            "coverage note",
        )
        section_triggers = (
            "missing inputs:",
            "missing input:",
            "exact gaps:",
            "gaps the user must supply:",
            "gaps the customer must supply:",
        )
        for raw in lines:
            stripped = raw.strip()
            lowered = stripped.lower()
            if any(marker in lowered for marker in success_markers):
                collecting = False
                continue
            if lowered.startswith("##") and any(token in lowered for token in ("missing", "gap")):
                collecting = True
                continue
            if "**exact gaps" in lowered or "**gap identified" in lowered:
                collecting = True
                continue
            triggered = False
            for trigger in section_triggers:
                if lowered.startswith(trigger):
                    collecting = True
                    triggered = True
                    remainder = stripped[len(trigger) :].strip()
                    if remainder.startswith(("- ", "* ")):
                        cleaned = remainder[2:].strip()
                        if cleaned and cleaned not in seen:
                            seen.add(cleaned)
                            missing.append(cleaned)
                    break
            if triggered:
                continue
            if collecting and stripped.startswith(("- ", "* ")):
                cleaned = stripped[2:].strip()
                if cleaned and cleaned not in seen:
                    seen.add(cleaned)
                    missing.append(cleaned)
                continue
            if collecting and stripped and not stripped.startswith(("- ", "* ")):
                break
        return missing

    @classmethod
    def _extract_missing_outputs(cls, artifacts: list[dict[str, Any]]) -> list[str]:
        missing: list[str] = []
        seen: set[str] = set()
        for artifact in artifacts:
            if str(artifact.get("render_status") or "").strip().lower() != "failed":
                continue
            targets = artifact.get("render_targets") or []
            for target in targets:
                ext = cls._artifact_extension(str(target or ""))
                if ext and ext not in seen:
                    seen.add(ext)
                    missing.append(ext)
        return missing

    @staticmethod
    def _build_step_entity_payload(
        base_payload: dict[str, Any],
        *,
        input_artifacts: list[ChainArtifactRef],
        step_context: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(base_payload)
        if input_artifacts:
            merged["input_artifacts"] = [
                {
                    "step_id": ref.step_id,
                    "skill": ref.skill,
                    "run_id": ref.run_id,
                    "filename": ref.filename,
                    "path": ref.path,
                    "display_name": ref.display_name or ref.filename,
                    "mime": ref.mime,
                    "size": ref.size,
                    "products": list(ref.products),
                }
                for ref in input_artifacts
            ]
        else:
            merged.pop("input_artifacts", None)
        if step_context:
            merged["chain_step_context"] = step_context
        else:
            merged.pop("chain_step_context", None)
        return merged

    @staticmethod
    def _compose_step_prompt(chain: ChainRunState, step: ChainStepSpec) -> str:
        upstream = {
            step_id: run.model_dump()
            for step_id, run in chain.steps.items()
            if run.status in {"completed", "partial"}
        }
        handoff = {
            "chain_id": chain.chain_id,
            "chain_name": chain.spec.name,
            "chain_prompt": chain.spec.prompt,
            "chain_context": chain.spec.context,
            "step_id": step.id,
            "step_context": step.context,
            "artifact_requirements": [
                requirement.model_dump() for requirement in step.artifact_requirements
            ],
            "input_artifacts": [
                artifact.model_dump()
                for artifact in chain.steps[step.id].input_artifacts
            ],
            "upstream_steps": upstream,
        }
        return (
            (step.prompt or chain.spec.prompt or "Run this chain step.").strip()
            + "\nUse input_artifacts[].path when a tool needs an upstream file path; do not reconstruct paths from run_dir."
            + (
                f"\nSkill-specific retrieval hook: {step.context.get('retrieval_query')}"
                if step.context.get("retrieval_query")
                else ""
            )
            + (
                "\n\n## User-Supplied Missing Input\n"
                + chain.resume_notes.strip()
                if chain.resume_notes.strip()
                else ""
            )
            + "\nIf critical evidence is missing, emit an explicit missing-input list the user can supply and still produce the best partial artifact."
            + (
                "\n\n## Platform gate gaps (retrieve retry)\n"
                + "\n".join(f"- {gap}" for gap in step.context.get("platform_gate_gaps")[:12])
                + "\nAddress these with additional retrieval or honest claim_gaps[] — platform expander handles coverage ratio."
                if isinstance(step.context.get("platform_gate_gaps"), list)
                and step.context.get("platform_gate_gaps")
                else ""
            )
            + "\n\n## Theseus Chain Handoff\n"
            + "```json\n"
            + json.dumps(handoff, ensure_ascii=False, indent=2, default=str)
            + "\n```"
        )


__all__ = ["SkillChainExecutor"]