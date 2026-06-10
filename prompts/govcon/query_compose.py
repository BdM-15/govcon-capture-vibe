"""Compose GovCon query prompts on top of LightRAG's rag_response spine."""

from __future__ import annotations

def lightrag_query_prompts() -> dict[str, str]:
    from lightrag.prompt import PROMPTS

    return {
        "rag_response": PROMPTS["rag_response"],
        "naive_rag_response": PROMPTS["naive_rag_response"],
    }


def _split_instructions(template: str) -> tuple[str, str, str]:
    """Split a LightRAG query template into step/grounding, formatting tail, context."""
    body = template.split("---Instructions---", 1)[1]
    formatting_marker = "3. Formatting & Language:"
    context_marker = "---Context---"
    fmt_idx = body.index(formatting_marker)
    step_and_grounding = body[:fmt_idx].rstrip()
    tail_and_context = body[fmt_idx:]
    ctx_idx = tail_and_context.index(context_marker)
    formatting_tail = tail_and_context[:ctx_idx].rstrip()
    context_footer = tail_and_context[ctx_idx:].strip()
    return step_and_grounding, formatting_tail, context_footer


def _split_step_and_grounding(step_and_grounding: str) -> tuple[str, str]:
    grounding_marker = "2. Content & Grounding:"
    idx = step_and_grounding.index(grounding_marker)
    return step_and_grounding[:idx].rstrip(), step_and_grounding[idx:].rstrip()


def _enhance_references_format(formatting_tail: str) -> str:
    extra = (
        "  - Place inline `[N]` citation markers next to each factual claim; "
        "`N` must match the corresponding entry in `### References`.\n"
        "  - When page numbers or section references are available in the retrieved "
        "context, include them in reference list entries "
        '(e.g., "[1] PWS Section C.2.5, p.12").\n'
    )
    anchor = "  - The Document Title in the citation must retain its original language."
    if anchor not in formatting_tail:
        return formatting_tail
    return formatting_tail.replace(anchor, extra + anchor, 1)


RAG_STEP_ADDENDUM = """
  - Place inline `[N]` markers next to factual claims; numbers must match `### References`.
  - Apply GovCon domain expertise to interpret retrieved facts when the question benefits from explanation — separate cited facts from framework reasoning.
  - For exploratory queries, prioritize Knowledge Graph entities related to the question (requirements, work_scope_item, evaluation_factor, deliverable) rather than generic methodology lectures.
  - When the user follows up on a prior turn, develop that thread without restarting from scratch.
  - Do not append unsolicited win-theme lectures or capture strategy unless the user asks for strategy, evaluation alignment, or win themes."""

NAIVE_STEP_ADDENDUM = """
  - Place inline `[N]` markers next to factual claims; numbers must match `### References`.
  - Apply GovCon domain expertise to interpret retrieved facts when the question benefits from explanation — separate cited facts from framework reasoning.
  - When the user follows up on a prior turn, develop that thread without restarting from scratch.
  - Do not append unsolicited win-theme lectures or capture strategy unless the user asks for strategy, evaluation alignment, or win themes."""

_GOVCON_GROUNDING_ADDENDUM = """
  - You ARE encouraged to reason about, interpret, and draw strategic implications from retrieved facts when the question benefits from analysis.
  - You ARE encouraged to apply Shipley methodology and FAR/DFAR expertise to analyze grounded data.
  - Proactively surface risks, opportunities, and recommendations when the user asks for strategic analysis or when a material compliance gap appears in cited context.
  - Expand acronyms on first use (e.g., "Firm Fixed Price (FFP)").
  - Prefer thoroughness over brevity when the user asks for overview, comprehension, walkthrough, or completeness.
  - **Ontology vs Fact (CRITICAL):** Shipley methodology, FAR/DFAR rules, and evaluator heuristics are FRAMEWORK knowledge — use them to shape HOW you analyze. NEVER assert them as facts about THIS RFP unless the Context contains direct evidence. Attribute clearly: "The RFP states X [N]; Shipley practice suggests Y because Z."
  - Do not invent prior debrief findings, incumbent vulnerabilities, or competitor moves unless explicitly in the Context.
  - **Template placeholders:** Customer templates (CLIN cost worksheets, staffing matrices, etc.) may contain example dollar amounts and quantities that are NOT normative. When a chunk shows placeholder signals (`$0.00`, "example", "for illustration"), flag it: "**Template — extract structure, not values.**" Never weave placeholder values into strategic narratives.
  - **Pattern recognition** (when the question asks about compliance, traceability, evaluation alignment, or risks): surface contradictions between proposal_instruction and evaluation_factor entities; flag evaluation weight vs page-limit mismatches or template placeholders when the Context shows them."""


def compose_govcon_rag_response(
    lightrag_template: str,
    *,
    govcon_preamble: str,
    goal_block: str,
    step_addendum: str,
) -> str:
    """Build a GovCon query prompt: domain preamble + LightRAG formatting spine."""
    step_and_grounding, formatting_tail, context_footer = _split_instructions(
        lightrag_template
    )
    step_block, grounding_block = _split_step_and_grounding(step_and_grounding)
    formatting_tail = _enhance_references_format(formatting_tail)

    instructions = "\n\n".join(
        [
            step_block + step_addendum,
            grounding_block + _GOVCON_GROUNDING_ADDENDUM,
            formatting_tail,
        ]
    )

    return "\n\n".join(
        [
            govcon_preamble.rstrip(),
            goal_block.rstrip(),
            "---Instructions---",
            "",
            instructions,
            "",
            context_footer,
        ]
    )


def lightrag_prompt_version() -> str:
    """Return installed LightRAG version for changelog/tests."""
    from importlib import metadata

    try:
        return metadata.version("lightrag-hku")
    except metadata.PackageNotFoundError:
        return "unknown"