# workload_handoff.json schema

Workload slice output only. Eval crosswalk, pains, win themes, and tea leaves belong in sibling slice skills.

## Required shape

```json
{
  "readiness_outcome": "2–4 sentences: program-office readiness the customer owns — lead with outcome, anchor with PWS/QASP metrics (e.g. FMC, PO attainment) when chunk evidence supports them.",
  "workload_enablers": [
    {
      "enabler": "Named PWS section, CDRL, QASP clause, or transition requirement — how contract work instruments the readiness outcome",
      "readiness_link": "One sentence tying this workload cluster to the program-office outcome",
      "source_chunk_ids": ["chunk-abc123"]
    }
  ],
  "failure_modes_feared": [
    {
      "failure_mode": "Concrete degradation path if contractor misses the enabler",
      "customer_impact": "Metric, inspection, or activation consequence the program office bears",
      "source_chunk_ids": ["chunk-def456"]
    }
  ],
  "claim_gaps": [
    "Named missing package surface or document the customer could supply"
  ]
}
```

Minimum counts: `workload_enablers` ≥ 3, `failure_modes_feared` ≥ 3. Every enabler and failure row must carry `source_chunk_ids[]` from scratchpad evidence.

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

See `readiness_output_contract.md`. Expand acronyms on first use as Full Term (ACR) when defined in retrieved chunk prose.