# tea_leaves_handoff.json schema

Tea-leaves slice only. Pains, eval, workload, modernization, win-themes belong in sibling skills.

## Required shape

```json
{
  "importance_signals": [
    {
      "signal": "What repeats or echoes across package",
      "source_role": "program_office | contracting_officer",
      "confidence": "high | medium | low",
      "alternate_read": "Optional second interpretation when confidence is not high",
      "source_chunk_ids": ["chunk-…"]
    }
  ],
  "implicit_criteria": [
    {
      "criterion": "Unstated but evidenced eval/acquisition read",
      "source_role": "program_office | contracting_officer",
      "confidence": "high | medium | low",
      "alternate_read": "Optional when confidence is not high",
      "source_chunk_ids": ["chunk-…"]
    }
  ],
  "claim_gaps": ["Named missing signal/criteria evidence"]
}
```

## Retrieve contract

1. `kg_entities` once (`customer_priority`, `evaluation_factor`, `requirement`, `document_section`)
2. **One** `kg_chunks` for `tea_leaves` surface per `retrieval_plan.json`
3. `plan_complete: true` → write handoff once → stop

## Out of scope

- `customer_pain_points[]` → pains
- `win_theme_candidates[]` → win-themes
- `eval_crosswalk[]` → eval