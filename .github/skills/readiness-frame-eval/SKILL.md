---
name: readiness-frame-eval
description: >
  Retrieves evaluation-factor evidence in deterministic batches and emits
  eval_handoff.json with eval_crosswalk rows — one per material Section M
  factor/subfactor. Use when building eval crosswalk slices, readiness-frame-eval
  solo/chain node, or Mission Readiness Frame evaluation coverage. Always run
  scripts/list_eval_batches.py before retrieval. Do not use for workload,
  pains, modernization, tea-leaves, or win-themes — sibling slice skills.
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
  version: 2.0.0
  status: active
  research_harness:
    plan_surfaces_path: references/plan_surfaces.json
    deliverables: [eval_handoff.json]
    frame_artifact: eval_handoff.json
    min_kg_chunks_passes: 4
    coverage_contract:
      artifact_path: eval_handoff.json
      required_entity_types: [evaluation_factor, subfactor]
      rule: one_row_per_entity
      rows_key: eval_crosswalk
      min_coverage_ratio: 0.8
  max_turns: 16
  depth_extension_turns: 0
---

# Readiness Frame — Evaluation

Micro-skill for **evaluation cross-walk** only.

Read before writing:
- `references/readiness_output_contract.md`
- `references/eval_handoff_schema.md`

## Out of scope

Ignore chain prompts asking for workload, pains, modernization, tea-leaves, or win-themes — sibling skills own those fields.

## Workflow (scripted batch retrieve)

### 0. Batch manifest (script — run first)

```
run_script scripts/list_eval_batches.py <workspace_name> --out {artifacts}/eval_batch_manifest.json
```

The manifest lists `batches[].factors` for coverage and row labels only — **not** kg_chunks queries. After inventory, read `artifacts/retrieval_plan.json` for every retrieve turn.

### 1. Inventory (one call)

`kg_entities` once with `evaluation_factor` + `subfactor`. Do not repeat.

### 2. Retrieve (one kg_chunks per batch surface — one per turn)

Follow `artifacts/retrieval_plan.json` **sequentially**. Surfaces: `eval_batch_1` … `eval_batch_4` (see `references/plan_surfaces.json`).

For each turn while `plan_complete` is false:
- Read `retrieval_plan.json` → `next_step.surface_id` and `next_step.suggested_query`
- Run **exactly one** `kg_chunks` with that suggested query (short plan-surface query — **not** the long manifest `suggested_kg_chunks_query`)
- Append evidence to scratchpad; advance to the next surface on the following turn

**Never** fire multiple `kg_chunks` in one assistant turn. Manifest batch queries overlap and the plan guard will mark them duplicate — wasting turns.

When every surface is `retrieved` or `saturated` (`plan_complete: true`), **stop calling kg_chunks and kg_entities**. The platform blocks redundant queries — do not fight the plan guard.

### 3. Draft (write handoff once — only after plan complete)

When `retrieval_plan.json` shows `plan_complete: true`, write `artifacts/eval_handoff.json` per `references/eval_handoff_schema.md`:
- One row per material factor you grounded (use manifest `batches[].factors` for verbatim labels)
- Missing factors → `claim_gaps[]` by **name** — never scaffold rows

If `write_file` returns a retrieve-phase error, **do not retry write_file**. Run the `next_step` `kg_chunks` from `retrieval_plan.json` instead.

### 4. Stop

Do not `read_file` the scratchpad — evidence is already in tool results. After handoff JSON is written, **stop**. Platform finalize runs outside this loop.

## Retrieval discipline (latency)

Target: **≤16 turns, ≤180s** on `mcpp_rfp`-class packages.

| Step | Budget |
|------|--------|
| list_eval_batches script | 1 turn |
| kg_entities | 1 turn |
| kg_chunks (4 batches) | 4 turns |
| write / revise handoff | 2–3 turns |

Never run 15 `kg_chunks` passes on one surface. One `kg_chunks` per assistant turn. If chunks overlap, advance to the next batch surface via `retrieval_plan.json`.

## Quality bar (production)

Capture-grade eval handoff — not just row count:
- `evaluation_factor` labels **verbatim** from `eval_batch_manifest.json` / `kg_entities` inventory — no invented "Factor N" shorthand when inventory has the full name
- `readiness_link` — 2–4 sentences (~90+ chars): program-office readiness consequence, not generic "weak evidence undermines confidence"
- `proof_expected` — concrete proposal artifacts (~70+ chars): volumes, matrices, plans evaluators expect per Section L
- `source_chunk_ids[]` on every row — diversify across batch surfaces (no one chunk in >45% of rows)
- **Accounting:** every material inventory entity → crosswalk row **or** `claim_gaps[]` entry containing the **verbatim** entity name
- Missing factors: `claim_gaps[]` line like `Material factor <verbatim name> — no grounded chunk evidence after batch retrieval`

Platform finalize may expand thin crosswalks — do not burn retrieve turns fighting gates. Draft best effort from scratchpad, log honest verbatim gaps, stop.

Eval cases: `evals/evals.json`.