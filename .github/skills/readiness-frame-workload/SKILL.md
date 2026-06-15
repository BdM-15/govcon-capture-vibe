---
name: readiness-frame-workload
description: >
  Retrieves package-mechanics evidence (background, PWS/SOW, QASP, transition) and
  emits workload_handoff.json with program-office readiness_outcome, workload_enablers,
  and failure_modes_feared. Use when building Mission Readiness Frame workload slice,
  package-mechanics handoff, readiness enablers, or solo/chain workload node on
  readiness-frame-* pipelines. Do not use for eval crosswalk, pains, modernization,
  tea-leaves, or win-themes — those are sibling slice skills.
license: MIT
metadata:
  personas_primary: capture_manager
  personas_secondary: [proposal_manager, program_manager]
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
    deliverables: [workload_handoff.json]
    frame_artifact: workload_handoff.json
    min_kg_chunks_passes: 4
  max_turns: 12
---

# Readiness Frame — Workload / Package Mechanics

Micro-skill for **PWS/SOW, background, QASP, transition** only. Program office = customer; contract = workload enabler for readiness.

Read before writing:
- `references/readiness_output_contract.md` — voice, citations
- `references/workload_handoff_schema.md` — JSON shape and slice boundaries

## Out of scope (sibling skills own these)

Do not emit `eval_crosswalk`, `customer_pain_points`, `current_methods`, `innovation_opportunities`, `importance_signals`, `implicit_criteria`, or `win_theme_candidates` in this handoff. Chain prompts may mention them — ignore for this slice.

## Workflow

### 1. Inventory (one call)

Run `kg_entities` once for package types: `requirement`, `deliverable`, `performance_standard`, `document_section`, `amendment`. Do not repeat.

### 2. Retrieve (one pass per surface)

Follow `artifacts/retrieval_plan.json`. Surfaces: `background`, `pws_sow`, `qasp`, `transition` (see `references/plan_surfaces.json`).

For each surface:
- Run **one** targeted `kg_chunks` query using the suggested query or a tight variant anchored on that surface.
- Append evidence to `artifacts/research_scratchpad.md`.
- Advance to the next surface.

When every surface is `retrieved` or `saturated`, **stop calling kg_chunks and kg_entities**. The platform blocks redundant queries — do not fight the plan guard.

### 3. Draft (write handoff once)

Write `artifacts/workload_handoff.json` per `references/workload_handoff_schema.md`:
- `readiness_outcome` — program-office outcome in plain English
- `workload_enablers[]` — ≥3 cited links from PWS/QASP/CDRL/transition to that outcome
- `failure_modes_feared[]` — ≥3 concrete degradation paths
- `claim_gaps[]` — honest named gaps for thin surfaces

Use real `source_chunk_ids` from the scratchpad. Never invent section numbers or CDRL IDs without grounding.

### 4. Stop

After `workload_handoff.json` is written, **stop**. Platform finalize and gates run outside this tool loop. Do not burn turns re-retrieving or rewriting to chase gate errors — partial handoff + `claim_gaps[]` is correct behavior.

## Retrieval discipline (latency)

Target: **≤12 turns, ≤120s** on `mcpp_rfp`-class packages.

- One `kg_entities` + up to four `kg_chunks` passes — not fifteen.
- If a surface returns overlapping chunks, move on; do not rephrase the same query.
- Draft from scratchpad evidence; do not poll KG again during draft.

## Quality bar (platform gate)

Gate checks substance after retrieve:
- Non-empty `readiness_outcome` or `workload_enablers`
- Cited chunk IDs on material claims

Eval cases: `evals/evals.json`.