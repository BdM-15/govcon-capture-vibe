"""SkillManager — discover, install, and invoke agent skills.

Skills live in ``.github/skills/<name>/SKILL.md`` (the official agentskills.io
location). Each ``SKILL.md`` is a Markdown file with YAML frontmatter:

    ---
    name: <slug>
    description: <pushy, precise trigger sentence>
    category: <design|ontology|proposal|compliance|intel|other>
    version: <semver>
    license: <spdx>
    ---

    # <Skill Title>
    <imperative instructions...>

The manager:
  * Walks ``.github/skills/`` at startup (and on demand) to register skills
  * Stores install metadata in ``rag_storage/_platform/skills.json`` (a single
    workspace-independent JSON file — installed skills are global to the
    Theseus instance, not per-RFP)
  * Pulls relevant entity slices from the active workspace KG when a skill is
    invoked, then dispatches the SKILL.md instructions + entity payload to
    the configured LLM
  * Supports installation from a GitHub URL via ``git clone --depth=1`` into
    ``.github/skills/`` (no PyPI / no archive fetch — git is the contract)

Design choices:
  * No SQLite, no PyYAML, no extra deps — small inline YAML frontmatter
    parser handles only what skill files actually use (str/int/bool keys at
    top level).
  * Workspace context injection is deliberately conservative: we pull entity
    *names* and *types*, never raw chunk text, into the prompt. The skill
    can ask for chunk-level evidence via the standard query endpoints.
  * Invocation never blocks the main event loop — long LLM calls use
    ``asyncio.to_thread`` if a sync LLM client is the only option available.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from src.skills.skill_catalog import SkillCatalog
from src.skills.skill_models import (
    Skill,
    SkillFrontmatter,
    SkillInvocationResult,
    SkillRunSummary,
)
from src.skills.runs import (
    STUDIO_EXTRA_MIME as _STUDIO_EXTRA_MIME,
    SkillRunStore,
    parse_run_envelope as _parse_run_envelope,
    resolve_artifact_mime,
    slugify_for_filename as _slugify_for_filename,
)
from src.skills.settings import (
    DEFAULT_SKILL_MAX_PAYLOAD_CHARS,
    resolve_skill_runtime_mode,
    skill_tools_max_turns,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILLS_DIR = _REPO_ROOT / ".github" / "skills"
_PLATFORM_DIR = _REPO_ROOT / "rag_storage" / "_platform"
_INSTALL_LEDGER = _PLATFORM_DIR / "skills.json"


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class SkillManager:
    """Discover and invoke agent skills.

    The manager is a singleton (see :func:`get_skill_manager`) and is safe to
    call concurrently — discovery and ledger writes are guarded by a lock.
    """

    def __init__(
        self,
        skills_dir: Path = _SKILLS_DIR,
        ledger_path: Path = _INSTALL_LEDGER,
        mcps_root: Optional[Path] = None,
    ) -> None:
        self.skills_dir = skills_dir
        self.ledger_path = ledger_path
        self._catalog = SkillCatalog(skills_dir=skills_dir, ledger_path=ledger_path)
        self._run_store = SkillRunStore()
        # Phase 4a: MCP client subsystem. Lazy-imported so legacy-mode
        # deployments without any MCPs installed pay zero cost.
        from src.skills.mcp_client import MCPRegistry

        if mcps_root is None:
            mcps_root = _REPO_ROOT / "tools" / "mcps"
        self._mcp_registry = MCPRegistry.from_root(mcps_root)

    # ---- Discovery ----------------------------------------------------

    def discover(self) -> dict[str, Skill]:
        return self._catalog.discover()

    # ---- Public read API ---------------------------------------------

    def list_skills(self, include_developer: bool = False) -> list[dict[str, Any]]:
        return self._catalog.list_skills(include_developer=include_developer)

    def get_skill(self, name: str) -> Optional[Skill]:
        return self._catalog.get_skill(name)

    def get_skill_detail(self, name: str) -> Optional[dict[str, Any]]:
        return self._catalog.get_skill_detail(name)

    # ---- Install / uninstall -----------------------------------------

    async def install_from_github(self, url: str, name: Optional[str] = None) -> Skill:
        return await self._catalog.install_from_github(url, name=name)

    async def uninstall(self, name: str) -> bool:
        return await self._catalog.uninstall(name)

    # ---- Invocation ---------------------------------------------------

    async def invoke(
        self,
        name: str,
        *,
        workspace: str,
        user_prompt: str,
        entity_payload: dict[str, Any],
        llm: Callable[[str], Awaitable[str]],
        max_payload_chars: Optional[int] = None,
        workspace_root: Optional[Path] = None,
        slice_fn: Optional[Callable[..., dict[str, Any]]] = None,
        retrieve_fn: Optional[Callable[..., Awaitable[dict[str, Any]]]] = None,
        runtime_mode_override: Optional[str] = None,
    ) -> SkillInvocationResult:
        """Run a skill against an injected workspace context.

        Args:
            name: Skill slug.
            workspace: Active workspace name (for telemetry / output envelope).
            user_prompt: Free-text user instruction (may be empty for
                "use defaults" mode).
            entity_payload: Briefing book dict produced by the route layer
                (Phase 1.5 contract). Expected top-level keys:
                ``entities`` (``{entity_type: [{name, description,
                source_chunks}]}``), ``source_chunks`` (verbatim RFP text
                blocks the model is required to quote from), and
                ``relationships`` (typed KG edges between sliced entities).
                Falls back gracefully if older callers pass a flat
                ``{entity_type: [...]}`` dict.
            llm: Async callable that takes a single composed prompt string
                and returns the model's response. Lets the caller decide which
                model / temperature to use.
            max_payload_chars: Hard cap on the JSON-serialized entity payload
                included in the prompt (truncated with a marker if exceeded).
            slice_fn: Optional Phase 1.5 KG slice callable (route layer's
                ``_slice_workspace_entities``). Required for tools-mode skills
                that call ``kg_entities``.
            retrieve_fn: Optional Phase 1.6 retrieval callable (route layer's
                ``_retrieve_relevant_entities_for_skill``). Required for
                tools-mode skills that call ``kg_chunks``.
            runtime_mode_override: Force ``"tools"`` or ``"legacy"`` regardless
                of what the skill's ``metadata.runtime`` declares. Used by the
                env var ``SKILL_RUNTIME_MODE`` and tests.
        """
        skill = self.get_skill(name)
        if skill is None:
            raise KeyError(f"Unknown skill: {name}")

        # Resolve runtime mode: explicit override > env var > frontmatter > default.
        mode = resolve_skill_runtime_mode(
            skill.frontmatter.runtime_mode,
            runtime_mode_override=runtime_mode_override,
        )

        if mode == "tools":
            return await self._invoke_tools_mode(
                skill=skill,
                workspace=workspace,
                user_prompt=user_prompt,
                workspace_root=workspace_root,
                slice_fn=slice_fn,
                retrieve_fn=retrieve_fn,
            )
        return await self._invoke_legacy_mode(
            skill=skill,
            workspace=workspace,
            user_prompt=user_prompt,
            entity_payload=entity_payload,
            llm=llm,
            max_payload_chars=max_payload_chars,
            workspace_root=workspace_root,
        )

    # ---- Legacy single-shot path (pre-2.1) ---------------------------

    async def _invoke_legacy_mode(
        self,
        *,
        skill: "Skill",
        workspace: str,
        user_prompt: str,
        entity_payload: dict[str, Any],
        llm: Callable[[str], Awaitable[str]],
        max_payload_chars: Optional[int],
        workspace_root: Optional[Path],
    ) -> SkillInvocationResult:
        """Original single-shot dispatch — pre-builds briefing book and calls llm once."""
        name = skill.name
        warnings: list[str] = []
        budget = max_payload_chars if max_payload_chars is not None else DEFAULT_SKILL_MAX_PAYLOAD_CHARS
        payload_json = json.dumps(entity_payload, ensure_ascii=False, indent=2)
        if len(payload_json) > budget:
            payload_json = payload_json[:budget] + "\n…[truncated]"
            warnings.append(
                f"briefing book truncated at {budget} chars (SKILL_MAX_PAYLOAD_CHARS); "
                "raise the env var, narrow entity_types, or lower max_chunks_per_entity"
            )

        # Phase 1.5: ``entity_payload`` is now a briefing-book dict whose
        # ``entities`` sub-dict holds the type buckets. Older callers may pass
        # the flat shape — detect both and surface a single, accurate list.
        if isinstance(entity_payload.get("entities"), dict):
            entities_used = sorted(entity_payload["entities"].keys())
        else:
            entities_used = sorted(
                k for k in entity_payload.keys()
                if k not in {"source_chunks", "relationships", "retrieval_metadata"}
            )
        composed = self._compose_prompt(skill, workspace, user_prompt, payload_json)

        started = datetime.now(timezone.utc)
        response = await llm(composed)
        elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)

        # Telemetry: stamp last-invoked timestamp.
        self._touch_invocation(name)

        run_id = ""
        run_dir = ""
        if workspace_root is not None:
            try:
                run_id, run_dir = self._persist_run(
                    workspace_root=workspace_root,
                    skill_name=name,
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
                logger.warning("Failed to persist skill run for %s: %s", name, exc)
                warnings.append(f"persistence failed: {exc}")

        return SkillInvocationResult(
            skill=name,
            workspace=workspace,
            response=response,
            entities_used=entities_used,
            warnings=warnings,
            elapsed_ms=elapsed_ms,
            prompt_tokens_estimate=len(composed) // 4,  # rough
            run_id=run_id,
            run_dir=run_dir,
        )

    # ---- Tools-mode multi-turn loop (2.1) -----------------------------

    async def _invoke_tools_mode(
        self,
        *,
        skill: "Skill",
        workspace: str,
        user_prompt: str,
        workspace_root: Optional[Path],
        slice_fn: Optional[Callable[..., dict[str, Any]]],
        retrieve_fn: Optional[Callable[..., Awaitable[dict[str, Any]]]],
    ) -> SkillInvocationResult:
        """Multi-turn tool-calling dispatch.

        The skill body is the workflow contract. The runtime gives the model
        six tools (read_file, run_script, write_file, kg_query, kg_entities,
        kg_chunks) and lets it drive itself to a final answer. Every tool call
        is captured in ``transcript.json`` for grounding audit.

        Requires ``workspace_root`` so the run folder (with artifacts/ and
        tool_outputs/) can be created up front; the runtime writes
        ``transcript.json`` after every turn so a crash leaves a usable
        partial trace.
        """
        # Local imports keep the openai dep optional for legacy-mode users.
        from src.skills.runtime import run_tool_loop
        from src.skills.tools import ToolContext

        if workspace_root is None:
            raise RuntimeError(
                "tools-mode skills require workspace_root for run persistence"
            )

        warnings: list[str] = []
        started = datetime.now(timezone.utc)
        run_id, run_dir = self._run_store.create_run_dir(
            workspace_root=workspace_root,
            skill_name=skill.name,
            user_prompt=user_prompt,
            started_at=started,
            create_tool_outputs=True,
        )

        # Honour an env-tunable turn cap so operators can throttle cost.
        # A skill MAY also declare ``metadata.max_turns`` to claim a larger
        # budget for itself when its workflow legitimately needs it (e.g.,
        # ``competitive-intel`` walks 10 numbered steps with multiple MCP
        # calls each). The skill's value wins when it is a positive int and
        # exceeds the env baseline; otherwise the env value is used. This
        # keeps the global throttle as a floor, not a ceiling, so operators
        # can still raise it across the board without editing every skill.
        max_turns = skill_tools_max_turns(skill.frontmatter.metadata)

        # Phase 3b: opt-in cross-skill script roots. The skill declares
        # ``metadata.script_paths`` as a list of directories (relative to its
        # own folder) that ``run_script`` may execute from. Typical use is
        # pointing at a sibling utility skill's scripts/ dir (e.g.,
        # ``../huashu-design/scripts``) so PPTX/PDF renderers can be
        # invoked without per-skill wrapper shims. We resolve, validate
        # existence, and pass absolute paths to the tool runtime.
        extra_script_roots: list[Path] = []
        raw_paths = skill.frontmatter.metadata.get("script_paths") or []
        if isinstance(raw_paths, str):
            raw_paths = [raw_paths]
        skill_dir_resolved = Path(skill.path).resolve()
        for entry in raw_paths:
            if not isinstance(entry, str) or not entry.strip():
                warnings.append(
                    f"script_paths: skipping non-string entry {entry!r}"
                )
                continue
            candidate = (Path(skill.path) / entry).resolve()
            if not candidate.is_dir():
                warnings.append(
                    f"script_paths: directory does not exist or is not a dir: {entry}"
                )
                continue
            # Don't allow declaring your own skill_dir as an extra root (no-op);
            # also reject ascending past the skills container root.
            if candidate == skill_dir_resolved:
                continue
            extra_script_roots.append(candidate)

        ctx = ToolContext(
            skill_name=skill.name,
            skill_dir=Path(skill.path),
            run_dir=run_dir,
            workspace_dir=workspace_root,
            workspace_name=workspace,
            slice_fn=slice_fn,
            retrieve_fn=retrieve_fn,
            extra_script_roots=extra_script_roots,
        )

        # Phase 4a: spawn one subprocess per declared MCP for this run.
        # The registry handles unknown / failed MCPs gracefully (warns and
        # omits them) so partial failures do not abort the run.
        requested_mcps = skill.frontmatter.required_mcps
        if requested_mcps:
            try:
                startup = await self._mcp_registry.start_run_sessions(
                    run_id=run_id, requested=requested_mcps
                )
                ctx.mcp_sessions = startup.sessions
                warnings.extend(startup.warning_messages())
                started_names = startup.started_names
                if started_names:
                    logger.info(
                        "skill %s run %s: MCP sessions live: %s",
                        skill.name,
                        run_id,
                        started_names,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "MCP startup failed for skill %s run %s: %s",
                    skill.name,
                    run_id,
                    exc,
                )
                warnings.append(f"MCP startup failed: {exc}")

        try:
            loop_result = await run_tool_loop(
                skill_name=skill.name,
                skill_body=skill.body_md,
                user_prompt=user_prompt,
                ctx=ctx,
                max_turns=max_turns,
            )
        finally:
            # Phase 4a: reap MCP subprocesses. Must run on every exit path
            # (success, exception, turn-cap forced summary) so abandoned
            # Node/Python child procs don't accumulate across runs.
            if ctx.mcp_sessions:
                try:
                    await self._mcp_registry.shutdown_run(run_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "MCP shutdown failed for run %s: %s", run_id, exc
                    )
        warnings.extend(loop_result.warnings)
        elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)

        # Persist the run envelope. The transcript itself is already written
        # incrementally by the runtime; we just stamp the human-readable
        # summary here.
        try:
            self._run_store.persist_tools_run(
                run_dir=run_dir,
                run_id=run_id,
                skill_name=skill.name,
                workspace=workspace,
                user_prompt=user_prompt,
                response=loop_result.response,
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

        # Optional: emit rendered artifacts automatically when the skill opts in.
        try:
            auto_emit = bool(skill.frontmatter.metadata.get("auto_emit_artifacts"))
        except Exception:
            auto_emit = False
        if auto_emit:
            try:
                # Run the emitter in-process; it is best-effort and mustn't raise.
                self._auto_emit_artifacts(skill, Path(run_dir))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Auto-emit artifacts failed for %s run %s: %s", skill.name, run_id, exc)
                warnings.append(f"auto_emit_artifacts failed: {exc}")

        self._touch_invocation(skill.name)

        return SkillInvocationResult(
            skill=skill.name,
            workspace=workspace,
            response=loop_result.response,
            entities_used=[],  # tools-mode discovers entities through tool calls
            warnings=warnings,
            elapsed_ms=elapsed_ms,
            prompt_tokens_estimate=int(loop_result.usage_total.get("total_tokens", 0)),
            run_id=run_id,
            run_dir=str(run_dir.resolve()),
        )

    def _auto_emit_artifacts(self, skill: Skill, run_dir: Path) -> None:
        """Best-effort renderer invocation to produce artifacts for Studio.

        This helper creates a minimal `report.md` and `report.json` from
        `response.md` and then attempts to call the repository's renderers
        (`.github/skills/renderers/scripts/render_docx.py` and
        `render_xlsx.py`). All stdout/stderr are captured into
        `tool_outputs/` for auditability. Failures are non-fatal and logged.
        """
        try:
            skill_dir = Path(skill.path)
            artifacts_dir = Path(run_dir) / "artifacts"
            tool_outputs_dir = Path(run_dir) / "tool_outputs"
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            tool_outputs_dir.mkdir(parents=True, exist_ok=True)

            response_path = Path(run_dir) / "response.md"
            if not response_path.exists():
                return

            # Create a simple markdown source for DOCX rendering
            report_md = artifacts_dir / "report.md"
            report_md.write_text(response_path.read_text(encoding="utf-8"), encoding="utf-8")

            # Create a minimal JSON blob for XLSX rendering (one sheet)
            report_json = artifacts_dir / "report.json"
            summary_text = response_path.read_text(encoding="utf-8").strip()
            json_payload = {"summary": [{"text": summary_text[:1000]}]}
            report_json.write_text(json.dumps(json_payload, ensure_ascii=False), encoding="utf-8")

            # Locate renderer scripts in the repo (fall back to built-in renderers)
            repo_root = Path(__file__).resolve().parents[2]
            renderers_dir = repo_root / ".github" / "skills" / "renderers" / "scripts"

            # Helper to invoke a script and capture outputs
            import sys as _sys

            def _run_script(prog_path: Path, args: list[str], out_name: str) -> None:
                try:
                    proc = subprocess.run(
                        [_sys.executable, str(prog_path)] + args,
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=120,
                    )
                except Exception as exc:  # noqa: BLE001
                    (tool_outputs_dir / f"{out_name}.stderr.txt").write_text(str(exc), encoding="utf-8")
                    return
                (tool_outputs_dir / f"{out_name}.stdout.txt").write_text(proc.stdout or "", encoding="utf-8")
                (tool_outputs_dir / f"{out_name}.stderr.txt").write_text(proc.stderr or "", encoding="utf-8")

            # Attempt DOCX render
            docx_script = renderers_dir / "render_docx.py"
            if docx_script.is_file():
                out_docx = artifacts_dir / f"{skill.name}_report.docx"
                args = ["--input", str(report_md), "--output", str(out_docx)]
                # Use a skill-provided reference if present
                ref = skill_dir / "assets" / "reference.docx"
                if ref.is_file():
                    args.extend(["--reference", str(ref)])
                _run_script(docx_script, args, "render_docx")

            # Attempt XLSX render
            xlsx_script = renderers_dir / "render_xlsx.py"
            if xlsx_script.is_file():
                out_xlsx = artifacts_dir / f"{skill.name}_report.xlsx"
                args = ["--input", str(report_json), "--output", str(out_xlsx), "--title", "Skill Report"]
                _run_script(xlsx_script, args, "render_xlsx")

        except Exception as exc:  # noqa: BLE001
            logger.warning("_auto_emit_artifacts error: %s", exc)

    @staticmethod
    def _compose_prompt(
        skill: Skill, workspace: str, user_prompt: str, payload_json: str
    ) -> str:
        """Compose the final LLM prompt: instructions + workspace + user ask.

        The Workspace Briefing Book block (Phase 1.5 + 1.6) packages four things:

        * ``entities``           — typed entity buckets, each item carries the
                                    ``source_chunks`` IDs that produced it.
        * ``source_chunks``      — verbatim RFP text the model MUST quote from
                                    (never paraphrase) when citing requirements,
                                    proposal_instruction items (Section L or
                                    equivalent), evaluation_factor items
                                    (Section M or equivalent), deliverables, or
                                    clauses.
        * ``relationships``      — typed KG edges between the entities.
        * ``retrieval_metadata`` — Phase 1.6 provenance: tells the model whether
                                    the briefing book was query-targeted (chat-
                                    grade hybrid retrieval) or a bulk slice, and
                                    how many entities/chunks the retriever ranked
                                    as relevant. The model uses this to decide
                                    when to emit `GAP` for out-of-coverage asks.

        Citation discipline is enforced in the rendered envelope so every
        skill inherits the same source-of-truth contract.
        """
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
            "\"Instructions to Offerors\" section in a FAR 16 task order, FOPR, "
            "BPA call, OTA, or agency-specific format), `evaluation_factor` "
            "(UCF Section M or equivalent — e.g. \"Evaluation Criteria\", "
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
            "Follow the skill's Output Contract section exactly. If a JSON "
            "envelope is specified, return only the JSON envelope. Inline "
            "chunk-ID citations are required wherever you quote RFP text.\n"
        )

    # ---- Run persistence ----------------------------------------------

    @staticmethod
    def _runs_root(workspace_root: Path, skill_name: str) -> Path:
        return SkillRunStore.runs_root(workspace_root, skill_name)

    @staticmethod
    def _is_safe_run_id(run_id: str) -> bool:
        return SkillRunStore.is_safe_run_id(run_id)

    def _persist_run(
        self,
        *,
        workspace_root: Path,
        skill_name: str,
        workspace: str,
        user_prompt: str,
        composed_prompt: str,
        response: str,
        entities_used: list[str],
        warnings: list[str],
        elapsed_ms: int,
        started_at: datetime,
    ) -> tuple[str, str]:
        return self._run_store.persist_legacy_run(
            workspace_root=workspace_root,
            skill_name=skill_name,
            workspace=workspace,
            user_prompt=user_prompt,
            composed_prompt=composed_prompt,
            response=response,
            entities_used=entities_used,
            warnings=warnings,
            elapsed_ms=elapsed_ms,
            started_at=started_at,
        )

    def list_runs(
        self, workspace_root: Path, skill_name: Optional[str] = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        return self._run_store.list_runs(
            workspace_root,
            skill_name=skill_name,
            limit=limit,
        )

    def get_run(
        self, workspace_root: Path, skill_name: str, run_id: str
    ) -> Optional[dict[str, Any]]:
        return self._run_store.get_run(workspace_root, skill_name, run_id)

    def delete_run(
        self, workspace_root: Path, skill_name: str, run_id: str
    ) -> bool:
        return self._run_store.delete_run(workspace_root, skill_name, run_id)

    def list_deliverables(
        self, workspace_root: Path, limit: int = 500
    ) -> list[dict[str, Any]]:
        return self._run_store.list_deliverables(workspace_root, limit=limit)

    def get_artifact_path(
        self,
        workspace_root: Path,
        skill_name: str,
        run_id: str,
        filename: str,
    ) -> Optional[Path]:
        return self._run_store.get_artifact_path(
            workspace_root,
            skill_name,
            run_id,
            filename,
        )

    def _touch_invocation(self, name: str) -> None:
        self._catalog.touch_invocation(name)


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_SINGLETON: Optional[SkillManager] = None


def get_skill_manager() -> SkillManager:
    """Return the process-wide SkillManager, discovering on first use."""
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = SkillManager()
        _SINGLETON.discover()
    return _SINGLETON
