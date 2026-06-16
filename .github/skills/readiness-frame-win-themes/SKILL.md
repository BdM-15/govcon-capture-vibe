---
name: readiness-frame-win-themes
description: >
  Retrieves customer needs/wants and Shipley win-theme seeds; emits win_themes_handoff.json
  with priority-ranked win_theme_candidates[]. Use for readiness-frame-win-themes solo/chain
  node. Not for pains, eval, workload, modernization, or tea-leaves.
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
    deliverables: [win_themes_handoff.json]
    frame_artifact: win_themes_handoff.json
    min_kg_chunks_passes: 2
  max_turns: 12
  depth_extension_turns: 0
---

# Readiness Frame — Win Themes

Micro-skill for **customer needs/wants** retrieval and **win-theme candidate seeds** only.

Read before writing:
- `references/readiness_output_contract.md`
- `references/win_themes_handoff_schema.md`

## Out of scope

Ignore chain prompts asking for pains, eval crosswalk rows, workload enablers, modernization, or tea-leaves. Do not emit `customer_pain_points[]`, `eval_crosswalk[]`, or `importance_signals[]` in this handoff.

## Workflow

### 1. Inventory (one call)

`kg_entities` once with `customer_priority`, `evaluation_factor`, `requirement`, `pain_point`. Do not repeat.

### 2. Retrieve (one kg_chunks per surface — one per turn)

Follow `artifacts/retrieval_plan.json` sequentially. Surfaces: `shipley_needs_wants`, then `shipley_win_themes`.

For each turn while `plan_complete` is false:
- Read `next_step.suggested_query`
- Run **exactly one** `kg_chunks`
- Advance on the following turn

Never fire multiple `kg_chunks` in one assistant turn.

When every surface is `retrieved` or `saturated`, **stop calling kg_chunks and kg_entities**.

### 3. Draft (write handoff once)

When `plan_complete: true`, write `artifacts/win_themes_handoff.json` per `references/win_themes_handoff_schema.md`:
- `win_theme_candidates[]` — ≥3 **objects** with `theme`, `priority`, `rationale_chain`, `proof_required[]`, `evaluation_factor_links[]`, `source_chunk_ids[]`
- `claim_gaps[]` — honest named gaps

Use real `source_chunk_ids` from the scratchpad. Do not emit plain-string theme rows. Field `theme` = short label — not `theme_seed`. If `write_file` is blocked in retrieve phase, run the next planned `kg_chunks` instead of retrying write.

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
- `win_theme_candidates` ≥ 3 cited object rows; `theme` ≥ 12 chars; `rationale_chain` ≥ 70 chars
- Each row: non-empty `proof_required[]` and `evaluation_factor_links[]` plus `source_chunk_ids`
- No sibling-slice fields (pains, eval, tea-leaves)
- `claim_gaps[]` names missing needs/wants evidence honestly when thin

Eval cases: `evals/evals.json`.