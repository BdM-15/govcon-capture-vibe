"""Parametrized smoke test for every installed skill.

For each skill the server reports as installed, this test:

1. Picks a representative prompt (from the skill's own ``evals/evals.json``
   first entry; falls back to a per-skill default below).
2. Invokes the skill via the HTTP API.
3. Asserts the tool loop completed without erroring.
4. Asserts the response is non-empty.
5. Asserts grounding signals: at least one of (a) a chunk-id citation in the
   response, (b) ``entities_used`` non-empty in the envelope, (c) a non-empty
   transcript with KG retrieval calls (probed via the run-detail endpoint).

Skills that emit a deliverable (artifact) get an additional check that the
``run_dir/artifacts/`` directory was populated.

When ``RUN_GROUNDING_AUDIT=1`` is set, each skill's transcript is also fed
through ``tools/audit_skill_grounding.py`` and a grounding ratio is logged.
With ``ENFORCE_GROUNDING_RATIO=1`` (off by default) the run hard-fails any
skill below ``MIN_GROUNDING_RATIO`` (default 0.80); without it, sub-threshold
ratios are recorded as ``xfail`` while citation rules are tightened.

The harness is intentionally permissive on response *content* — branch 147
adds the quantified grounding-ratio audit. This branch only proves the loop
runs end-to-end + the audit infrastructure works.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx
import pytest

from .conftest import invoke_skill, load_run_transcript

# ---------- Per-skill default prompts (used if no evals.json) -------------

# Prompts are written against the AFCAP V FOPR for Al Dhafra Air Base (UAE)
# Installation Support Services (ISS) — workspace ``afcap5_adab_iss``.
# The seed corpus contains: Amend 4 FOPR (FA8051-26-R-1002), the PWS, the
# CLIN price schedule, and one related attachment.
DEFAULT_PROMPTS: dict[str, str] = {
    "proposal-generator": (
        "Draft a one-paragraph executive summary opening for our response "
        "to the AFCAP V Al Dhafra Air Base ISS FOPR (FA8051-26-R-1002), "
        "grounded in the PWS scope and the evaluation subfactors."
    ),
    "compliance-auditor": (
        "Audit the FOPR for the top 5 'shall' requirements that lack a "
        "clearly mapped deliverable or evaluation factor. Cite chunks."
    ),
    "competitive-intel": (
        "Who is the likely incumbent on installation support services at "
        "Al Dhafra Air Base, and what recent AFCAP V task orders should "
        "we benchmark against?"
    ),
    "price-to-win": (
        "Build a rough price-to-win cost stack for the base-year MEP "
        "(Subfactor 1.2) labor on this Al Dhafra ISS effort. Use OCONUS "
        "per diem assumptions and call out wrap-rate sensitivity."
    ),
    "ot-prototype-strategist": (
        "Confirm whether this AFCAP V FOPR is a FAR-based vehicle or an "
        "OT prototype. If FAR-based, state that clearly and stop."
    ),
    "mission-readiness-framer": (
        "Build the Mission Readiness Frame for this Al Dhafra ISS FOPR. "
        "What readiness outcome is the program office buying, what pain "
        "points matter, and what win-theme candidates should we seed?"
    ),
    "rfp-reverse-engineer": (
        "Reverse-engineer the CO's hidden priorities on this Al Dhafra "
        "ISS FOPR. Surface hot buttons, ghost language, and the "
        "transition-risk emphasis."
    ),
    "subcontractor-sow-builder": (
        "Draft a brief subcontractor SOW skeleton for the MEP scope "
        "(Subfactor 1.2) we plan to push to a teaming partner on this "
        "Al Dhafra ISS opportunity."
    ),
    "oci-sweeper": (
        "Sweep this Al Dhafra ISS FOPR for OCI risks per FAR 9.5 — focus "
        "on incumbent transition and any A-E / construction-management "
        "crossover."
    ),
    "govcon-ontology": (
        "Validate the workspace's entity inventory against the 33-type "
        "ontology and flag any unusual gaps for an ISS FOPR of this size."
    ),
    "renderers": (
        "Render a small compliance-matrix DOCX from 3 sample "
        "requirement/evaluation pairs drawn from this Al Dhafra ISS FOPR "
        "to verify the render_docx script path works."
    ),
    "huashu-design": (
        "Sketch a hi-fi HTML mockup for a one-page proposal cover sheet "
        "for the AFCAP V Al Dhafra ISS opportunity."
    ),
}

# Skills whose primary deliverable is a file under run_dir/artifacts/
ARTIFACT_SKILLS = {
    "proposal-generator",
    "compliance-auditor",
    "renderers",
    "subcontractor-sow-builder",
    "price-to-win",
    "competitive-intel",
}

# Skills that don't produce the standard tools-mode transcript shape.
# Skip the transcript-call assertion for these.
LEGACY_SKILLS: set[str] = set()

# Pure utility skills that don't (and shouldn't) consult the workspace KG.
# They operate on inputs handed to them by other skills (e.g. renderers takes
# a Markdown path + flags, runs pandoc, returns a file). Grounding signal is
# satisfied by the presence of any tool call (read_file / run_script).
UTILITY_SKILLS = {"renderers"}

CHUNK_CITE_RE = re.compile(r"chunk-[0-9a-f]{4,}", re.IGNORECASE)
KG_TOOLS = {"kg_chunks", "kg_query", "kg_entities"}


def _evals_prompt(skill_name: str) -> str | None:
    """Pull the first prompt from the skill's evals/evals.json, if present."""
    repo_root = Path(__file__).resolve().parents[3]
    evals_path = repo_root / ".github" / "skills" / skill_name / "evals" / "evals.json"
    if not evals_path.exists():
        return None
    try:
        data = json.loads(evals_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    prompts = data.get("prompts") or data.get("evals") or []
    if isinstance(prompts, list) and prompts:
        first = prompts[0]
        if isinstance(first, dict):
            return first.get("prompt") or first.get("input")
        if isinstance(first, str):
            return first
    return None


def _resolve_prompt(skill_name: str) -> str:
    return _evals_prompt(skill_name) or DEFAULT_PROMPTS.get(
        skill_name,
        "Provide a brief grounded summary using the active workspace.",
    )


def _skill_names(installed_skills: list[dict[str, Any]]) -> list[str]:
    return sorted(s["name"] for s in installed_skills if isinstance(s, dict) and "name" in s)


@pytest.fixture(scope="module")
def skill_names(installed_skills: list[dict[str, Any]]) -> list[str]:
    names = _skill_names(installed_skills)
    if not names:
        pytest.skip("server reports zero installed skills")
    return names


def test_server_reports_skills(skill_names: list[str]) -> None:
    """Sanity: server should expose at least the 11 we expect."""
    assert len(skill_names) >= 11, f"Expected ≥11 skills, got {len(skill_names)}: {skill_names}"


@pytest.mark.parametrize("skill_name", sorted(DEFAULT_PROMPTS.keys()))
def test_skill_invoke_smoke(
    skill_name: str,
    skill_names: list[str],
    http_client: httpx.Client,
    base_url: str,
) -> None:
    """End-to-end: invoke the skill, verify the loop completed and grounded."""
    if skill_name not in skill_names:
        pytest.skip(f"skill {skill_name!r} not installed on this server")

    prompt = _resolve_prompt(skill_name)

    envelope = invoke_skill(http_client, base_url, skill_name, prompt)

    # 1. Loop completed: envelope present + non-empty response
    assert envelope.get("skill") == skill_name
    response = envelope.get("response") or ""
    assert isinstance(response, str) and response.strip(), (
        f"{skill_name}: empty response in envelope"
    )

    # 2. Grounding: at least one signal that workspace data was consulted
    cites_chunk = bool(CHUNK_CITE_RE.search(response))
    entities_used = envelope.get("entities_used") or {}
    has_entities = bool(entities_used) and (
        any(entities_used.values()) if isinstance(entities_used, dict) else True
    )

    transcript_has_kg_call = False
    transcript_has_any_tool_call = False
    run_id = envelope.get("run_id")
    if run_id and skill_name not in LEGACY_SKILLS:
        try:
            run_detail = load_run_transcript(http_client, base_url, skill_name, run_id)
            transcript = run_detail.get("transcript") or run_detail.get("turns") or []
            if isinstance(transcript, list):
                for turn in transcript:
                    if not isinstance(turn, dict):
                        continue
                    # Pattern A: assistant turn with tool_calls=[{name: ...}, ...]
                    for call in turn.get("tool_calls") or []:
                        if not isinstance(call, dict):
                            continue
                        name = (call.get("name") or "").lower()
                        if name:
                            transcript_has_any_tool_call = True
                            if name in KG_TOOLS:
                                transcript_has_kg_call = True
                    # Pattern B: tool result turn with kind="tool", name="<tool>"
                    if (turn.get("kind") or "").lower() == "tool":
                        name = (turn.get("name") or turn.get("tool") or "").lower()
                        if name:
                            transcript_has_any_tool_call = True
                            if name in KG_TOOLS:
                                transcript_has_kg_call = True
        except Exception:  # noqa: BLE001
            pass  # absence of run-detail endpoint shouldn't block the smoke

    if skill_name in UTILITY_SKILLS:
        # Utility skills (renderers, etc.) don't consult the KG. Grounding =
        # "actually invoked at least one tool" rather than "called a kg_* tool".
        grounded = cites_chunk or has_entities or transcript_has_any_tool_call
        gap_msg = "no chunk citation, no entities_used, no tool call at all"
    else:
        grounded = cites_chunk or has_entities or transcript_has_kg_call
        gap_msg = "no chunk citation, no entities_used, no kg_* tool call"
    assert grounded, (
        f"{skill_name}: no grounding signal ({gap_msg}). "
        f"Envelope keys: {list(envelope)}"
    )

    # 3. Artifact emitted where declared
    if skill_name in ARTIFACT_SKILLS:
        run_dir = envelope.get("run_dir")
        if run_dir:
            artifacts_dir = Path(run_dir) / "artifacts"
            if artifacts_dir.exists():
                files = list(artifacts_dir.iterdir())
                # Soft assertion — some skills may legitimately produce no
                # artifact when the prompt doesn't request one. Log but
                # don't hard-fail until branch 147.
                if not files:
                    pytest.xfail(
                        f"{skill_name}: ARTIFACT_SKILLS member but no artifact "
                        f"emitted — investigate in branch 147"
                    )

    # 4. Grounding-ratio audit (opt-in via RUN_GROUNDING_AUDIT=1).
    # Branch 147 establishes the baseline; the hard ``ratio >= 0.80`` assertion
    # is gated behind ``ENFORCE_GROUNDING_RATIO=1`` until each skill's SKILL.md
    # citation rules are tightened. UTILITY + LEGACY skills are exempt — pure
    # render utilities legitimately produce zero workspace claims.
    import os as _os
    if (
        _os.getenv("RUN_GROUNDING_AUDIT", "").strip().lower() in {"1", "true", "yes"}
        and skill_name not in UTILITY_SKILLS
        and skill_name not in LEGACY_SKILLS
        and run_id
    ):
        repo_root = Path(__file__).resolve().parents[3]
        ws = _os.getenv("THESEUS_E2E_WORKSPACE", "afcap5_adab_iss")
        transcript_path = (
            repo_root / "rag_storage" / ws / "skill_runs" / skill_name / run_id / "transcript.json"
        )
        if transcript_path.exists():
            # Local import keeps tools/ off the import path for non-audit runs
            import sys as _sys
            _sys.path.insert(0, str(repo_root / "tools"))
            try:
                from audit_skill_grounding import (  # noqa: WPS433
                    audit as _audit,
                    MIN_GROUNDING_RATIO_PER_SKILL as _FLOORS,
                    DEFAULT_GROUNDING_FLOOR as _DEFAULT_FLOOR,
                )
            finally:
                _sys.path.pop(0)
            report = _audit(transcript_path)
            ratio = report.get("grounding_ratio", 0.0)
            # Per-skill floor (147.9): each skill has an honest floor in
            # MIN_GROUNDING_RATIO_PER_SKILL. MIN_GROUNDING_RATIO env var
            # overrides for ad-hoc runs.
            override = _os.getenv("MIN_GROUNDING_RATIO")
            min_required = float(override) if override else _FLOORS.get(skill_name, _DEFAULT_FLOOR)
            print(
                f"\n[grounding] {skill_name}: ratio={ratio:.2f} "
                f"(floor={min_required:.2f}, "
                f"{report['claims_grounded']}/{report['claims_total']} "
                f"grounded, {report['claims_exempt']} exempt)"
            )
            if _os.getenv("ENFORCE_GROUNDING_RATIO", "").strip().lower() in {"1", "true", "yes"}:
                assert ratio >= min_required, (
                    f"{skill_name}: grounding_ratio={ratio:.2f} "
                    f"< required {min_required:.2f}. "
                    f"Unsourced examples: {report['unsourced_examples'][:3]}"
                )
            elif ratio < min_required:
                pytest.xfail(
                    f"{skill_name}: grounding_ratio={ratio:.2f} "
                    f"< {min_required:.2f} (xfail until SKILL.md citation rules tightened)"
                )
