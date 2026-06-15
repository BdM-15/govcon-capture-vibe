# win_themes_handoff.json schema

Win-themes slice only. Pains, eval, workload, modernization, and tea-leaves belong in sibling skills.

## Required shape

```json
{
  "win_theme_candidates": [
    {
      "theme": "Short Shipley win-theme label — customer language",
      "priority": 1,
      "rationale_chain": "2–4 sentences linking need/want → eval factor → proof hook with cited consequence",
      "proof_required": ["Concrete artifacts evaluators will look for"],
      "evaluation_factor_links": ["Factor 1 — Management", "Factor 2 — Technical"],
      "source_chunk_ids": ["chunk-…"]
    }
  ],
  "claim_gaps": [
    "Named missing needs/wants or win-theme evidence"
  ]
}
```

## Retrieve contract

1. `kg_entities` once (`customer_priority`, `evaluation_factor`, `requirement`, `pain_point`)
2. For each surface in `retrieval_plan.json`, run **one** `kg_chunks` per turn (`shipley_needs_wants`, then `shipley_win_themes`)
3. When `plan_complete: true` → write `win_themes_handoff.json` once and **stop**

## Out of scope

- `customer_pain_points[]` → pains skill
- `eval_crosswalk[]` → eval skill
- `importance_signals[]` / `implicit_criteria[]` → tea-leaves skill

## Voice

See `readiness_output_contract.md`. Seeds only — no proposal prose. Expand acronyms as Full Term (ACR).