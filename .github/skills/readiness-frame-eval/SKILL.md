---
name: readiness-frame-eval
description: Retrieves and structures evaluation-factor / subfactor evidence from the active solicitation KG. Emits eval_handoff.json with eval_crosswalk rows — one per material Section M factor/subfactor. USE WHEN building eval cross-walk slices for mission readiness or proposal strategy. Chain upstream of mission-readiness-framer.
license: MIT
metadata:
  personas_primary: capture_manager
  shipley_phases: [capture, strategy]
  capability: analyze
  skill_role: slice
  skill_family: readiness-frame
  skill_family_label: Mission Readiness Frame
  runtime: tools
  category: capture_intelligence
  version: 1.1.0
  status: active
  research_harness:
    plan_surfaces_path: references/plan_surfaces.json
    deliverables: [eval_handoff.json]
    frame_artifact: eval_handoff.json
    min_kg_chunks_passes: 1
    coverage_contract:
      artifact_path: eval_handoff.json
      required_entity_types: [evaluation_factor, subfactor]
      rule: one_row_per_entity
      rows_key: eval_crosswalk
      min_coverage_ratio: 0.8
  max_turns: 36
---

# Readiness Frame — Evaluation

Micro-skill for **evaluation cross-walk** evidence only.

## Workflow (batched entity-first)

1. **Inventory** — one `kg_entities` call with `evaluation_factor` + `subfactor`. Build the material factor list (exclude rating-scale / methodology meta labels).
2. **Batch** — group factors into batches of **5–8**. For each batch:
   - Run targeted `kg_chunks` queries anchored on that batch's factor names and related PWS/Section M language.
   - Synthesize `eval_crosswalk[]` rows **only for factors in the current batch**.
   - Every row must follow `references/readiness_output_contract.md` (customer terms, cited `source_chunk_ids`, no boilerplate).
3. **Gaps** — factors you cannot ground after retrieval → `claim_gaps[]` only. Never emit scaffold/template rows.
4. **Emit** — `artifacts/eval_handoff.json` with `eval_crosswalk[]` and `claim_gaps[]`.

## Output contract

Read `references/readiness_output_contract.md` before writing. Return only valid JSON for `eval_handoff.json`. Do not draft `brief.md` — parent `mission-readiness-framer` compiles the narrative.

### Required JSON shape

```json
{
  "eval_crosswalk": [],
  "claim_gaps": []
}
```