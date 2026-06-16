---
name: readiness-frame-modernization
description: >
  Retrieves PWS-implied current methods and customer-grounded innovation openings;
  emits modernization_handoff.json with current_methods[] and innovation_opportunities[].
  Use for readiness-frame-modernization solo/chain node or Mission Readiness Frame
  modernization slice. Do not use for pains, eval, workload, tea-leaves, or win-themes.
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
    deliverables: [modernization_handoff.json]
    frame_artifact: modernization_handoff.json
    min_kg_chunks_passes: 2
  max_turns: 12
  depth_extension_turns: 0
---

# Readiness Frame — Modernization / Innovation

Micro-skill for **current methods** and **innovation opportunities** only.

Read before writing:
- `references/readiness_output_contract.md`
- `references/modernization_handoff_schema.md`

## Out of scope

Ignore chain prompts asking for pains, eval crosswalk, workload enablers, tea-leaves, or win-themes. Do not emit `customer_pain_points[]` or `win_theme_candidates[]` in this handoff.

## Workflow

### 1. Inventory (one call)

`kg_entities` once with `system`, `tool`, `requirement`, `performance_standard`. Do not repeat.

### 2. Retrieve (one kg_chunks per surface — one per turn)

Follow `artifacts/retrieval_plan.json` sequentially. Surfaces: `methods_modernization`, then `innovation_inquiry`.

For each turn while `plan_complete` is false:
- Read `next_step.suggested_query`
- Run **exactly one** `kg_chunks`
- Advance on the following turn

Never fire multiple `kg_chunks` in one assistant turn.

When every surface is `retrieved` or `saturated`, **stop calling kg_chunks and kg_entities**.

### 3. Draft (write handoff once)

When `plan_complete: true`, write `artifacts/modernization_handoff.json` per `references/modernization_handoff_schema.md`:
- `current_methods[]` — ≥3 **objects** with `method`, `implied_by`, `tooling`, `fit_to_scope`, `source_chunk_ids[]` — PWS/QASP/CDRL-implied incumbent processes only
- `innovation_opportunities[]` — ≥2 **objects** with `opportunity`, `value` (quality up / cost down / both), `customer_grounded`, `fit_to_scope`, `source_chunk_ids[]`
- `claim_gaps[]` — honest named gaps

Use real `source_chunk_ids` from the scratchpad. Do not emit plain strings for method/innovation rows. If `write_file` is blocked in retrieve phase, run the next planned `kg_chunks` instead of retrying write.

Do not `read_file` the scratchpad — evidence is in tool results.

### 4. Stop

After handoff JSON is written, **stop**. Platform finalize runs outside this loop.

## Retrieval discipline (latency)

Target: **≤12 turns, ≤120s** on `mcpp_rfp`-class packages.

| Step | Budget |
|------|--------|
| kg_entities | 1 turn |
| kg_chunks (2 surfaces) | 2 turns |
| write handoff | 1–2 turns |

## Quality bar (production / platform gate)

Capture-grade handoff — not just non-empty JSON:
- `current_methods` ≥ 3 object rows, each with `method`, `implied_by` (≥50 chars), `source_chunk_ids`
- `innovation_opportunities` ≥ 2 object rows, each with `opportunity`, `value` (≥50 chars), `source_chunk_ids`
- `fit_to_scope` = high | medium | low when set; no sibling-slice fields (pains, eval, win-themes)
- `claim_gaps[]` names missing tooling/method evidence honestly when thin

Eval cases: `evals/evals.json`.