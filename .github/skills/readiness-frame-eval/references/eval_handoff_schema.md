# eval_handoff.json schema

Eval slice only. Workload, pains, modernization, tea-leaves, and win-themes belong in sibling skills.

## Required shape

```json
{
  "eval_crosswalk": [
    {
      "evaluation_factor": "Verbatim Section M factor or subfactor label",
      "pws_clusters": ["PWS section or CDRL anchor"],
      "readiness_link": "2–4 sentences — how weak proof degrades program-office readiness",
      "proof_expected": "Concrete artifacts evaluators seek in the proposal",
      "source_chunk_ids": ["chunk-…", "doc-…-chunk-…"]
    }
  ],
  "claim_gaps": [
    "Material factor <name> — no grounded chunk evidence after batch retrieval"
  ]
}
```

## Batched retrieve contract

1. `run_script scripts/list_eval_batches.py <workspace> --out {artifacts}/eval_batch_manifest.json`
2. `kg_entities` once (`evaluation_factor`, `subfactor`)
3. For each `eval_batch_N` surface, read `retrieval_plan.json` → run **one** `kg_chunks` per turn using `next_step.suggested_query` (plan surface query — not the long manifest query)
4. Use manifest `batches[].factors` only for row labels and `claim_gaps[]` coverage — draft rows in step 5, not during retrieve
5. When `plan_complete: true` → write `eval_handoff.json` once and **stop**

## Out of scope in this slice

- `readiness_outcome`, `workload_enablers` → workload skill
- `customer_pain_points[]` → pains skill

## Voice

See `readiness_output_contract.md`. Platform finalize repairs acronyms and expands coverage after retrieve — do not burn turns fighting gates in the tool loop.