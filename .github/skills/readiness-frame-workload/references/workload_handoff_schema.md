# workload_handoff.json schema

Workload slice output only. Eval crosswalk, pains, win themes, and tea leaves belong in sibling slice skills.

## Required shape

```json
{
  "readiness_outcome": "2–4 sentences: program-office readiness the customer owns — not CO contract administration.",
  "workload_enablers": [
    "PWS/QASP/CDRL/transition cluster — how this contract work instruments the readiness outcome [chunk-…]"
  ],
  "failure_modes_feared": [
    "Concrete degradation path if contractor misses enabler — tied to customer metric or inspection"
  ],
  "claim_gaps": [
    "Named missing package surface or document the customer could supply"
  ]
}
```

## Optional (only when scratchpad evidence supports)

- `readiness_signals[]` — short bullets with `source_chunk_ids`
- `scope_summary` — one paragraph of package scope anchors

## Do not emit in this slice

- `eval_crosswalk[]` → `readiness-frame-eval`
- `customer_pain_points[]` → `readiness-frame-pains`
- `current_methods[]` / `innovation_opportunities[]` → `readiness-frame-modernization`
- `importance_signals[]` / `implicit_criteria[]` → `readiness-frame-tea-leaves`
- `win_theme_candidates[]` → `readiness-frame-win-themes`

## Voice

See `readiness_output_contract.md`. Expand acronyms on first use: Full Term (ACR).