# pains_handoff.json schema

Pains slice only. Eval, workload, modernization, tea-leaves, and win-themes belong in sibling skills.

## Required shape

```json
{
  "customer_pain_points": [
    {
      "visibility": "explicit | latent | structural",
      "challenge_type": "Short label — customer language",
      "rationale": "2–4 sentences with cited program-office consequence; name document anchors",
      "readiness_link": "How this pain connects to readiness outcome the customer owns",
      "source_chunk_ids": ["chunk-…", "doc-…-chunk-…"]
    }
  ],
  "claim_gaps": [
    "Named missing pain evidence or document the customer could supply"
  ]
}
```

## Retrieve contract

1. `kg_entities` once (`pain_point`, `customer_priority`, `requirement`)
2. Read `retrieval_plan.json` → **one** `kg_chunks` for `shipley_pains` using `next_step.suggested_query`
3. When `plan_complete: true` → write `pains_handoff.json` once and **stop**

## Out of scope in this slice

- `eval_crosswalk[]` → eval skill
- `current_methods[]` / `innovation_opportunities[]` → modernization skill
- `workload_enablers[]` → workload skill

## Voice

See `readiness_output_contract.md`. Cover explicit, latent, and structural pains when evidence supports them.