---
name: readiness-frame-tea-leaves
description: >
  Retrieves importance signals and implicit criteria (tea leaves) from solicitation
  package; emits tea_leaves_handoff.json. Use for readiness-frame-tea-leaves solo/chain
  node. Not for pains, eval, workload, modernization, or win-themes.
license: MIT
metadata:
  personas_primary: capture_manager
  personas_secondary: [proposal_manager]
  shipley_phases: [capture, strategy]
  capability: analyze
  skill_role: slice
  skill_family: readiness-frame
  skill_family_label: Mission Readiness Frame
  runtime: tools
  category: capture_intelligence
  version: 2.0.0
  status: active
  research_harness:
    plan_surfaces_path: references/plan_surfaces.json
    deliverables: [tea_leaves_handoff.json]
    frame_artifact: tea_leaves_handoff.json
    min_kg_chunks_passes: 1
  max_turns: 10
  depth_extension_turns: 0
---

# Readiness Frame — Tea Leaves

Micro-skill for **importance signals** and **implicit criteria** only.

Read: `references/readiness_output_contract.md`, `references/tea_leaves_handoff_schema.md`

## Out of scope

No `customer_pain_points[]`, `win_theme_candidates[]`, `eval_crosswalk[]` in this handoff.

## Workflow

### 1. Inventory (one call)

`kg_entities` once: `customer_priority`, `evaluation_factor`, `requirement`, `document_section`. No repeat.

### 2. Retrieve (one kg_chunks)

Follow `artifacts/retrieval_plan.json` → surface `tea_leaves` → **one** `kg_chunks` with `next_step.suggested_query`.

`plan_complete: true` → stop kg tools.

### 3. Draft (once)

Write `artifacts/tea_leaves_handoff.json`:
- `importance_signals[]` — repetition, hot buttons, eval echoes
- `implicit_criteria[]` — unstated acquisition reads
- `source_role`: program_office vs contracting_officer
- `alternate_read` when `confidence` not high
- `claim_gaps[]` for thin evidence

No `read_file` scratchpad. Retrieve-phase write block → run planned kg_chunks, don't retry write.

### 4. Stop

After handoff written, stop. Platform finalize outside loop.

## Latency target

**≤10 turns, ≤120s** on `mcpp_rfp`.

Eval cases: `evals/evals.json`.