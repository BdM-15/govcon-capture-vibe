# modernization_handoff.json schema

Modernization slice only. Pains, eval, workload, tea-leaves, and win-themes belong in sibling skills.

## Required shape

```json
{
  "current_methods": [
    {
      "method": "Named incumbent or PWS-implied approach",
      "implied_by": "PWS/QASP/CDRL anchor language",
      "tooling": "Systems or manual tools cited in package",
      "fit_to_scope": "high | medium | low",
      "source_chunk_ids": ["chunk-…"]
    }
  ],
  "innovation_opportunities": [
    {
      "opportunity": "Customer-grounded improvement — methods not only technology",
      "value": "Quality up / cost down / both — plain English",
      "customer_grounded": true,
      "fit_to_scope": "high | medium | low",
      "source_chunk_ids": ["chunk-…"]
    }
  ],
  "claim_gaps": [
    "Named missing methods or innovation evidence"
  ]
}
```

## Retrieve contract

1. `kg_entities` once (`system`, `tool`, `requirement`, `performance_standard`)
2. For each surface in `retrieval_plan.json`, run **one** `kg_chunks` per turn (`methods_modernization`, then `innovation_inquiry`)
3. When `plan_complete: true` → write `modernization_handoff.json` once and **stop**

## Out of scope

- `customer_pain_points[]` → pains skill
- `win_theme_candidates[]` → win-themes skill
- `eval_crosswalk[]` → eval skill

## Voice

See `readiness_output_contract.md`. Cite real chunk IDs from scratchpad — no vendor invention without evidence.