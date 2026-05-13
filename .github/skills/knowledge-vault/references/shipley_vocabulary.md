# Shipley Vocabulary → Ontology Type Mapping

Use this table when translating raw, informal capture notes into structured Shipley-aligned vault notes. The left column contains the informal or Shipley term; the right column shows which VALID_ENTITY_TYPES to apply.

## Core Capture Vocabulary

| Raw / Informal Term | Shipley Term | Entity Type |
|--------------------|-------------|-------------|
| "hot button" | Customer Priority / Pain Point | `customer_priority` or `pain_point` |
| "discriminator" | Discriminator | `strategic_theme` (theme_type: discriminator) |
| "win theme" | Win Theme | `strategic_theme` (theme_type: win_theme) |
| "ghost language" | Ghost Language | `strategic_theme` (theme_type: ghost_language) |
| "proof point" | Proof Point / Evidence | `past_performance_reference` |
| "FAB statement" | Feature → Advantage → Benefit | `strategic_theme` (theme_type: fab_chain) |
| "shall" requirement | Requirement | `requirement` |
| "shall provide" deliverable | Deliverable | `deliverable` |
| "Section L instruction" | Proposal Instruction | `proposal_instruction` |
| "Section M criterion" | Evaluation Factor | `evaluation_factor` |
| "subfactor" | Subfactor | `evaluation_factor` (use same type, note it's a subfactor) |
| "page limit" | Proposal Instruction | `proposal_instruction` |
| "base period" / "option year" | Period of Performance | `period_of_performance` |
| "wrap rate" / "fee" / "ODC" | Pricing Element | `pricing_element` |
| "CLIN" | Contract Line Item | `contract_line_item` |
| "PWS paragraph" / "SOW task" | Work Scope Item | `work_scope_item` |
| "key personnel" / "LCAT" | Labor Category | `labor_category` |
| "AQL" / "SLA" / "QASP metric" | Performance Standard | `performance_standard` |
| "installed equipment" / "GFE" | Government Furnished Item | `government_furnished_item` |
| "CMMC level" / "NIST SP 800" | Regulatory Reference | `regulatory_reference` |

## Note Quality Signals

A note is **ready to polish** when it contains at least one of:
- A verbatim quote from the RFP/PWS/SOW with an identifiable entity type
- A named customer priority or pain point
- A requirement with "shall" language
- A reference to a specific contract number, CLIN, or PoP date

A note is **too thin** when:
- It is a single sentence with no Shipley concept
- It contains only a file name or a "see page X" reference
- It uses only informal terms with no traceable source phrase

## Polishing Checklist

When polishing a fleeting note:

1. **Identify the RFP source** — which section did this come from? (Proposal instruction → Section L; Evaluation factor → Section M; Requirement → PWS/SOW)
2. **Restate in Shipley terms** — replace "they want us to…" with "Requirement: the offeror shall…"
3. **Extract entity proposals** — minimum 1 entity per polished note; aim for 2-3
4. **Add context** — which workspace, which document, which page/section?
5. **Suggest links** — are there related notes covering the same theme?

## Evergreen Promotion Checklist

A note is ready for evergreen status when:
- At least one entity proposal has been reviewed and accepted (or rejected with reason)
- The note body is ≥ 50 words with Shipley vocabulary
- The note has been cross-referenced to at least one workspace KG entity (chunk_id cited)
- The note title is descriptive and would make sense to a future reader without context
