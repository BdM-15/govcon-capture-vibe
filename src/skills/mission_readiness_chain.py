"""Preset skill-chain spec for RFP Intelligence mission-readiness slice."""

from __future__ import annotations

from src.skills.chain_models import ChainArtifactRequirement, ChainSpec, ChainStepSpec
from src.skills.external_research_intent import detect_external_research_intent

_COMPILER_PROMPT = (
    "Compile upstream readiness handoffs into artifacts/mission_readiness_frame.json "
    "and artifacts/brief.md. Merge eval, workload, pains, modernization, tea-leaves, "
    "and win-theme JSON handoffs — do not re-reason from scratch when handoff rows exist. "
    "Write plain-English capture reasoning with customer document terminology; expand "
    "acronyms on first use as Full Term (ACR).\n"
    "Compiler discipline:\n"
    "- Uniform depth: every narrative section (pains, signals, tea leaves, methods/innovation, "
    "win themes, clarifications) gets multi-paragraph analytical prose — no compressed tail.\n"
    "- Eval cross-walk: one substantive row per material factor/subfactor; readiness_link and "
    "proof_expected are 2–4 sentences each; source_chunk_ids must be real doc-/chunk-/tb- IDs.\n"
    "- Cite evidence in brief.md with numbered markers [N] only; full source names live in the "
    "References section at document end — never inline long citations in narrative prose.\n"
    "- Mirror claim_gaps[] from JSON in a Clarifications / missing-coverage section of brief.md.\n"
    "- Do NOT add capability overlay unless the user addendum names a vendor or URL.\n"
    "- End brief with a short executive synthesis tying readiness outcome to top win themes.\n"
    "Return brief.md verbatim as final message."
)

_MICRO_SKILL_CONTEXT = (
    "Follow references/readiness_output_contract.md. Use batched entity-first retrieval "
    "when factor count exceeds eight. Log missing coverage in claim_gaps[] only — "
    "never emit scaffold or template crosswalk rows."
)

_STEP_RETRIEVE_CONTEXT = (
    "Retrieve must produce a handoff that passes the same gate as solo assess — coverage, "
    "citations, acronyms, substance. Log honest claim_gaps[] for missing factors; never "
    "emit scaffold rows. Platform finalize repairs known acronyms then re-validates."
)


def _pipeline_context(*, slice_name: str = "", extra: dict | None = None) -> dict:
    ctx: dict = {
        "langgraph_step_pipeline": True,
        # Micro-skill: LLM retrieves evidence; platform finalize owns handoff synthesis.
        "chain_retrieve_only": True,
        "eval_retrieve_only": True,  # legacy alias — same flag
        "workflow": f"{_MICRO_SKILL_CONTEXT}\n{_STEP_RETRIEVE_CONTEXT}",
    }
    if slice_name:
        ctx["slice"] = slice_name
    if extra:
        ctx.update(extra)
    return ctx


def _compose_prompt(base_prompt: str, user_addendum: str) -> str:
    parts = [str(base_prompt or "").strip()]
    extra = str(user_addendum or "").strip()
    if extra:
        parts.append(extra)
    return "\n\n".join(part for part in parts if part)


def build_mission_readiness_chain_spec(
    prompt: str,
    *,
    user_addendum: str = "",
) -> ChainSpec:
    """Build the decomposed readiness-frame chain ending in mission-readiness-framer."""
    full_prompt = _compose_prompt(prompt, user_addendum)
    # External overlay is user-directed only — catalog prompts mention "technology" generically.
    external = detect_external_research_intent(user_addendum)

    # Serial micro-skill waves — parallel kg_chunks/rerank crashed LightRAG ("Already borrowed").
    steps: list[ChainStepSpec] = [
        ChainStepSpec(
            id="workload",
            skill="readiness-frame-workload",
            prompt=full_prompt,
            context=_pipeline_context(slice_name="package"),
        ),
        ChainStepSpec(
            id="eval",
            skill="readiness-frame-eval",
            prompt=full_prompt,
            depends_on=["workload"],
            context=_pipeline_context(slice_name="evaluation"),
        ),
        ChainStepSpec(
            id="pains",
            skill="readiness-frame-pains",
            prompt=full_prompt,
            depends_on=["eval"],
            context=_pipeline_context(),
        ),
        ChainStepSpec(
            id="modernization",
            skill="readiness-frame-modernization",
            prompt=full_prompt,
            depends_on=["pains"],
            context=_pipeline_context(),
        ),
        ChainStepSpec(
            id="tea-leaves",
            skill="readiness-frame-tea-leaves",
            prompt=full_prompt,
            depends_on=["modernization"],
            context=_pipeline_context(),
        ),
        ChainStepSpec(
            id="win-themes",
            skill="readiness-frame-win-themes",
            prompt=full_prompt,
            depends_on=["tea-leaves"],
            context=_pipeline_context(),
        ),
    ]

    # LangGraph fires a node once per incoming edge — compile must depend only on
    # terminal slice step(s), not every upstream handoff (artifact_requirements
    # still bind all six handoffs at run time).
    compile_depends = ["win-themes"]
    if external is not None:
        steps.append(
            ChainStepSpec(
                id="external",
                skill="readiness-frame-external-research",
                prompt=full_prompt,
                depends_on=["tea-leaves"],
                context=_pipeline_context(
                    extra={
                        "external_research": {
                            "vendor_hint": external.vendor_hint,
                            "seed_urls": list(external.seed_urls),
                        },
                    }
                ),
            )
        )
        compile_depends = ["external", "win-themes"]

    compile_requirements: list[ChainArtifactRequirement] = [
        ChainArtifactRequirement(
            id="eval-handoff",
            from_steps=["eval"],
            products=["eval_handoff"],
            name_contains=["eval_handoff.json"],
            extensions=["json"],
        ),
        ChainArtifactRequirement(
            id="workload-handoff",
            from_steps=["workload"],
            products=["workload_handoff"],
            name_contains=["workload_handoff.json"],
            extensions=["json"],
        ),
        ChainArtifactRequirement(
            id="pains-handoff",
            from_steps=["pains"],
            products=["pains_handoff"],
            name_contains=["pains_handoff.json"],
            extensions=["json"],
        ),
        ChainArtifactRequirement(
            id="modernization-handoff",
            from_steps=["modernization"],
            products=["modernization_handoff"],
            name_contains=["modernization_handoff.json"],
            extensions=["json"],
        ),
        ChainArtifactRequirement(
            id="tea-leaves-handoff",
            from_steps=["tea-leaves"],
            products=["tea_leaves_handoff"],
            name_contains=["tea_leaves_handoff.json"],
            extensions=["json"],
        ),
        ChainArtifactRequirement(
            id="win-themes-handoff",
            from_steps=["win-themes"],
            products=["win_themes_handoff"],
            name_contains=["win_themes_handoff.json"],
            extensions=["json"],
        ),
    ]
    if external is not None:
        compile_requirements.append(
            ChainArtifactRequirement(
                id="external-handoff",
                from_steps=["external"],
                products=["capability_overlay_handoff"],
                name_contains=["capability_overlay_handoff.json"],
                extensions=["json"],
                required=False,
            )
        )

    steps.append(
        ChainStepSpec(
            id="compile",
            skill="mission-readiness-framer",
            prompt=full_prompt + "\n\n" + _COMPILER_PROMPT,
            depends_on=compile_depends,
            context={
                "role": "compiler",
                "langgraph_step_pipeline": True,
                "workflow": _MICRO_SKILL_CONTEXT,
            },
            artifact_requirements=compile_requirements,
        )
    )

    return ChainSpec(
        name="mission-readiness-chain",
        prompt=full_prompt,
        context={
            "preset": "mission-readiness",
            "external_research": external is not None,
        },
        steps=steps,
    )