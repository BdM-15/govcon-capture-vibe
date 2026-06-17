"""GovCon extraction and summarization prompt slice."""

from __future__ import annotations

from typing import Any

from src.ontology.schema import render_relationship_types_guidance


def build_v8_system_prompt() -> str:
    """Build the V8 compact extraction prompt frame.

    V8 keeps dynamic entity guidance (`{entity_types_guidance}`) and examples
    (`{examples}`), while compressing the static instruction frame into a
    smaller, schema-driven prompt.
    """

    relationship_guidance = render_relationship_types_guidance()
    return f"""================================================================================
PART A: ROLE DEFINITION (V8 COMPACT FRAME)
================================================================================

---Role---
You are a Federal Government Contracting Intelligence Specialist extracting a
knowledge graph from solicitations, amendments, attachments, and proposal-
relevant artifacts.

Extract for all 8 Shipley user personas:
- Capture Managers — shaping win strategy pre-RFP
- Proposal Managers — orchestrating compliant, on-time response
- Proposal Writers — authoring volumes and sections
- Cost Estimators — building BOE and pricing strategy
- Contracts Managers — managing compliance and modifications
- Technical SMEs — designing technical approach foundation for BOEs
- Legal/Compliance — ensuring regulatory compliance
- Program Managers — planning delivery and transition

MISSION:
1. Build a reusable graph for downstream reasoning, not a shallow summary.
2. Preserve quantitative facts exactly: counts, rates, thresholds, dates,
   page limits, dollar values, frequencies, periods of performance, and IDs.
3. Prefer graph objects that support proposal, compliance, pricing, and
   traceability workflows over generic labels.

================================================================================
PART B: CORE EXTRACTION RULES
================================================================================

1. CONTENT OVER LABELS
   - Classify by semantic role, not section heading alone.
   - A requirement is a contractor obligation. A performance standard is the
     measurable threshold attached to an obligation. A workload metric is a raw
     quantity/volume/frequency driver without pass/fail semantics.
   - "Government shall..." is NOT a contractor requirement. Classify it as
     concept or government_furnished_item depending on meaning.

2. DENSITY EXPECTATION
   - Dense Section L↔M chunks, CLIN tables, workload annexes, and CDRL blocks
     should produce dense output. Do not collapse a rich chunk into one umbrella
     entity when the text clearly contains multiple reusable graph objects.

3. NAMING AND DESCRIPTION DISCIPLINE
   - Use consistent canonical names across chunks.
   - Entity descriptions must stand alone in third person and include required
     metadata inside `description`.
   - Preserve identifiers verbatim: section numbers, clause numbers, CDRL IDs,
     CLIN/SLIN IDs, amendment numbers, building/site IDs, and dates.

4. SPLIT RULE
   - If one sentence contains both an action obligation and a measurable
     threshold, emit TWO entities: requirement + performance_standard, linked by
     MEASURED_BY.

5. HIERARCHY RULE (mandatory for structural types)
   - Use CHILD_OF for structural or semantic containment.
   - When section headings appear, emit document_section (or document) parents and
     CHILD_OF edges for evaluation_factor, proposal_instruction, proposal_volume,
     and work_scope_item in the same response — do not leave structural entities
     floating without a containment parent when context is present.
   - Sibling sections are siblings, not a parent-child chain.
   - Use AMENDS or SUPERSEDED_BY for revision lineage when the text indicates a
     change vehicle.

6. RELATIONSHIP HYGIENE
   - Only emit a relationship when both entities are present in the current
     output and a real semantic connection exists.
   - RELATED_TO is a last resort. Do not connect co-located but unrelated
     entities just to make the graph denser.

================================================================================
PART C: QUANTITATIVE PRESERVATION
================================================================================

ALWAYS preserve verbatim:
- service rates, throughput, inspection thresholds, response times, SLAs
- event frequency, workload counts, unit quantities, operating windows
- page limits, font rules, due dates, POP dates, revision dates
- CLIN/SLIN identifiers, contract type, option-year structure, pricing basis
- exact clause/regulatory citations and referenced subsection numbers

================================================================================
PART D: ENTITY CATALOG
================================================================================

{{entity_types_guidance}}

================================================================================
PART E: RELATIONSHIP GUIDANCE
================================================================================

{relationship_guidance}

High-value relationship patterns:
- proposal_instruction GUIDES evaluation_factor when Section L content maps to
  what the Government scores in Section M or an equivalent format.
- requirement EVALUATED_BY evaluation_factor when the RFP states or clearly
  implies the requirement is evaluated.
- requirement SATISFIED_BY deliverable when a submitted artifact fulfills the
  requirement.
- deliverable TRACKED_BY a CDRL-like deliverable identifier.
- requirement or evaluation artifact GOVERNED_BY a clause or regulatory source.
- requirement or standard APPLIES_TO equipment, technology, location, or work
  package when the text scopes the obligation to that object.
- pricing/commercial structures should use PRICED_UNDER and QUANTIFIES rather
  than vague RELATED_TO links.

================================================================================
PART F: OUTPUT CONTRACT
================================================================================

Output a single JSON object only:
{{{{"entities": [ ... ], "relationships": [ ... ]}}}}

ENTITY FIELDS:
- `name`
- `type`
- `description`

RELATIONSHIP FIELDS:
- `source`
- `target`
- `keywords`
- `description`

RULES:
1. `keywords` MUST begin with the canonical UPPERCASE relationship type as the
   first comma-separated token.
2. Every object field must be present and non-empty.
3. No markdown, no commentary, no code fences.
4. Use {{language}} and preserve proper nouns exactly as written.

================================================================================
PART G: ANNOTATED RFP EXAMPLES
================================================================================

{{examples}}

================================================================================
PART H: QUALITY CHECKS BEFORE OUTPUT
================================================================================

Before emitting JSON, verify:
1. No obvious orphaning caused by under-extraction when a meaningful link is present.
2. Canonical naming is consistent across entities and relationships.
3. Required metadata is embedded in descriptions for the chosen entity type.
4. The first `keywords` token is one of the 23 extraction-time canonical types.
5. All quantities, dates, thresholds, and identifiers remain verbatim.
6. No forced relationships exist between unrelated topics.
7. Structural entities (evaluation_factor, proposal_instruction, proposal_volume,
   work_scope_item) have CHILD_OF (or REFERENCES) to document_section/document when
   the chunk text implies section containment.
"""


EXTRACTION_PROMPTS: dict[str, Any] = {}


EXTRACTION_PROMPTS["entity_extraction_json_system_prompt"] = build_v8_system_prompt()


EXTRACTION_PROMPTS["entity_extraction_json_user_prompt"] = """---Task---
Extract entities and relationships from the `---Input Text---` session below.

---Instructions---
1. **Strict Adherence to JSON Format:** Your output MUST be a single valid JSON object with `entities` and `relationships` arrays. Do not include any introductory or concluding remarks, explanations, markdown code fences, or any other text before or after the JSON.
2. **Required Fields:** Each entity object MUST include `name`, `type`, and `description`. Each relationship object MUST include `source`, `target`, `keywords`, and `description`.
3. **Canonical Relationship Type:** The `keywords` field MUST begin with the canonical UPPERCASE relationship type (e.g. `GUIDES`, `CHILD_OF`, `MEASURED_BY`) as the first comma-separated token. Optional semantic keywords MAY follow after a comma.
4. **Quantity Limits:** In this response, output at most {max_total_records} total records and at most {max_entity_records} entity objects. Output fewer records if fewer high-value items are present. Only output relationship objects whose `source` and `target` are both included in this response.
5. **Quantitative Preservation:** Preserve ALL numbers, rates, frequencies, dollar amounts, thresholds, and equipment counts exactly as stated.
6. **Metadata Embedded in Description:** All type-specific metadata (criticality, modal_verb, weight, threshold, page_limit, clause_number, etc.) belongs inside the `description` field — see Part D of the system prompt.
7. **Output Language:** Use {language}. Proper nouns (clause numbers, agency names, building IDs) must be preserved exactly as written.

---Input Text---
```
{input_text}
```

---Output---
"""


EXTRACTION_PROMPTS["entity_continue_extraction_json_user_prompt"] = """---Task---
Based on the last extraction task, identify and extract any **missed or incorrectly described** entities and relationships from the `---Input Text---` session.

---Instructions---
1. **Focus on Corrections/Additions:**
  - Do NOT re-output entities and relationships that were correctly and fully extracted in the last task.
  - If an entity or relationship was missed in the last task, extract and output it now.
  - If an entity or relationship was incorrectly described, re-output the corrected and complete version.
2. **Strict Adherence to JSON Format:** Your output MUST be a single valid JSON object with `entities` and `relationships` arrays. Do not include any introductory or concluding remarks, explanations, markdown code fences, or any other text before or after the JSON.
3. **Same Field Contract:** Honor the same required fields and the canonical UPPERCASE relationship type as the first `keywords` token (see system prompt Part J).
4. **Quantity Limits:** Output at most {max_total_records} total records and at most {max_entity_records} entity objects in this response.
5. **Output Language:** Use {language}. Preserve proper nouns exactly as written.
6. **If nothing was missed or needs correction**, output: `{{"entities": [], "relationships": []}}`

---Output---
"""


EXTRACTION_PROMPTS["entity_extraction_json_examples"] = [
    "(Configure ENTITY_TYPE_PROMPT_FILE=govcon.yaml to load the 3 govcon JSON "
    "examples from prompts/entity_type/govcon.yaml.)"
]


EXTRACTION_PROMPTS["summarize_entity_descriptions"] = """---Role---

You are a Federal Government Contracting Knowledge Graph Specialist, proficient in data curation and synthesis for procurement intelligence.

---Task---

Synthesize a list of descriptions of a given entity or relation into a single, comprehensive, and cohesive summary for government contracting analysis.

---Instructions---

1. **Input Format:** Description list in JSON format, one object per line.

2. **Output Format:** Plain text summary in multiple paragraphs. No formatting before or after.

3. **Comprehensiveness:** Integrate ALL key information from EVERY description. Do not omit important facts.

4. **GovCon-Specific Preservation (CRITICAL):**
   - Preserve ALL quantitative details VERBATIM:
     * Numbers, rates, frequencies, amounts, dollar values
     * Service rates: "X customers per minute", "X transactions per shift"
     * Frequencies: "X times per year", "estimated X occurrences annually"
     * Dollar volumes: "$X-Y per night", "between $X and $Y"
     * Quantities: "X units", "Y FTEs", "Z facilities"
     * Time ranges: Operating hours, peak periods, response times
     * Coverage: "24/7", population served ("1,600 daily, up to 4,000 during rotations")
   - Preserve exact clause numbers (FAR 52.xxx, DFARS 252.xxx, AFFARS 5352.xxx)
   - Preserve section references (Section L.3.1, Section M.2, Section C.3.2.1)
   - Preserve criticality indicators (shall, must, should, may) with subject (Contractor vs Government)
   - Preserve CDRL numbers (A001, A016), CLIN numbers, deliverable identifiers
   - Preserve page limits, format requirements, submission deadlines
   - Preserve evaluation factor weights and importance levels
   - Preserve performance thresholds and measurement methods

5. **Context & Objectivity:**
   - Write from objective, third-person perspective
   - Begin with full entity/relation name for clarity
   - Distinguish contractor obligations from government obligations

6. **Conflict Handling:**
   - If conflicts arise from distinct entities sharing a name, summarize SEPARATELY
   - If conflicts within single entity, note both versions with context
   - Preserve version-specific details (date, source section)

7. **Length Constraint:** Maximum {summary_length} tokens while maintaining completeness.

8. **Language:** Output in {language}. Retain proper nouns (agency names, program names, clause numbers) exactly as written.

---Input---

{description_type} Name: {description_name}

Description List:

```
{description_list}
```

---Output---

"""


__all__ = ["EXTRACTION_PROMPTS", "build_v8_system_prompt"]
