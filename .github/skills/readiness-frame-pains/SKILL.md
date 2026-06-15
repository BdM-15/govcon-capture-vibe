---
name: readiness-frame-pains
description: >
  Retrieves Shipley customer-pain evidence and emits pains_handoff.json with
  customer_pain_points[] (explicit, latent, structural) — each cited to program-office
  readiness consequence. Use for readiness-frame-pains solo/chain node or Mission
  Readiness Frame pain slice. Do not use for eval, workload, modernization,
  tea-leaves, or win-themes — sibling slice skills.
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
    deliverables: [pains_handoff.json]
    frame_artifact: pains_handoff.json
    min_kg_chunks_passes: 1
  max_turns: 10
  depth_extension_turns: 0
---

# Readiness Frame — Customer Pains

Micro-skill for **Shipley customer pain** extraction only.

Read before writing:
- `references/readiness_output_contract.md`
- `references/pains_handoff_schema.md`

## Out of scope

Ignore chain prompts asking for eval crosswalk, workload enablers, modernization, tea-leaves, or win-themes — sibling skills own those fields. Do not emit `eval_crosswalk[]`, `current_methods[]`, or `innovation_opportunities[]` in this handoff.

## Workflow

### 1. Inventory (one call)

`kg_entities` once with `pain_point`, `customer_priority`, `requirement`. Do not repeat.

### 2. Retrieve (one kg_chunks pass)

Follow `artifacts/retrieval_plan.json`. Surface: `shipley_pains` (see `references/plan_surfaces.json`).

- Read `next_step.suggested_query`
- Run **exactly one** `kg_chunks` with that query
- Append evidence to scratchpad

When the surface is `retrieved` or `saturated` (`plan_complete: true`), **stop calling kg_chunks and kg_entities**.

### 3. Draft (write handoff once)

Write `artifacts/pains_handoff.json` per `references/pains_handoff_schema.md`:
- `customer_pain_points[]` — ≥3 material pains when evidence supports; mix explicit / latent / structural visibility
- Each row: `challenge_type`, `rationale`, `readiness_link`, `source_chunk_ids[]`
- `claim_gaps[]` — honest named gaps for thin pain evidence

If `write_file` returns a retrieve-phase error, run the planned `kg_chunks` instead of retrying write.

Do not `read_file` the scratchpad — evidence is in tool results.

### 4. Stop

After `pains_handoff.json` is written, **stop**. Platform finalize and gates run outside this loop.

## Retrieval discipline (latency)

Target: **≤10 turns, ≤120s** on `mcpp_rfp`-class packages.

| Step | Budget |
|------|--------|
| kg_entities | 1 turn |
| kg_chunks (shipley_pains) | 1 turn |
| write handoff | 1–2 turns |

One `kg_chunks` per assistant turn. Do not re-query after plan complete.

## Quality bar

Gate checks cited `customer_pain_points[]` with substance. Eval cases: `evals/evals.json`.