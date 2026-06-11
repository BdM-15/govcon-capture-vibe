# Customer Intent Signals — Pain, Importance, Tea Leaves

> Infer **program-office** intent from the **full solicitation package** — not the cover document alone.

## Cross-walk step (mandatory)

Triangulate the same priority language across:

| Source | What it reveals |
| ------ | --------------- |
| Background / Section 1.2 | Customer-stated mission context and pain confessions |
| PWS/SOW task areas | Workload the customer is buying |
| QASP / performance standards | Where performance anxiety is highest |
| Evaluation criteria (Section M) | How acquisition will **score** the enabler story |
| Amendments / Q&A (if in KG) | What the customer fixed vs left open |

When a noun phrase or priority appears in **three or more** places → emit `importance_signals[]` with `signal_type: repetition`.

## Pain point patterns (`customer_pain_points[]`)

| Pattern | Example language | `recommended_response_type` |
| ------- | ---------------- | --------------------------- |
| Transition confession | "previous transition was challenging" | `transition` |
| Incumbent performance failure | "prior contract experienced delays" | `mitigation` |
| Audit / inspection finding | "corrective actions required" | `proof` |
| Staffing / coverage gap | "insufficient coverage during surge" | `mitigation` |
| Single-point dependency | named system / certification lock | `proof` |

`source_role` is always `program_office` for pain points unless the pain is purely contractual (then use acquisition slice / compliance-auditor).

## Importance signals (`importance_signals[]`)

| `signal_type` | Detection rule |
| ------------- | -------------- |
| `explicit_weight` | "significantly more important than", numeric weights, relative importance tables |
| `section_order` | First evaluation factor or first PWS task area when weights silent (low confidence alone) |
| `repetition` | Same priority phrase in background + PWS + eval |
| `qasp_consequence` | Payment consequence or CPARS-adjacent language in QASP rows |
| `amendment_emphasis` | Amendment adds/clarifies one topic repeatedly |
| `background_eval_echo` | Background priority echoed verbatim in evaluation language |

Tag `source_role`:

- `program_office` — mission/pain/readiness language
- `co` — pure acquisition mechanics
- `both` — echoed in mission and eval sections

## Implicit criteria / tea leaves (`implicit_criteria[]`)

Each entry needs:

- `customer_read` — what the program office likely prioritizes
- `acquisition_read` — how the contracts shop encoded it (eval structure, instructions)
- `alternate_read` — honest second interpretation (required unless `confidence: high`)
- `linked_evaluation_factors[]` when eval language is involved

Common tea-leaf patterns:

| Signal | Customer read | Acquisition read | Alternate read |
| ------ | ------------- | ---------------- | -------------- |
| Eval uses vendor-specific jargon | Incumbent or favored approach | Template reuse | CO marketing drift — low signal |
| No transition section on recompete | Accepts incumbent advantage OR amendment coming | Omission | Customer indifference to transition risk |
| Extreme QASP density on one task | That task instruments critical readiness | Overspec from prior failure | CO lawer CYA — still customer anxiety |
| "Lowest price technically acceptable" | Price is hygiene | LPTA structure | Technical still wins if factors are pass/fail |

## Win theme candidates (`win_theme_candidates[]`)

Rules:

- Max **3** candidates with `priority` 1–3.
- Each must include `readiness_link` to `mission_readiness_frame.readiness_outcome`.
- `proof_required[]` lists evidence types (past performance cite, methodology proof, metric), not prose.
- `linked_hooks[]` may reference pain point or importance signal IDs (`PP-*`, `IS-*`).

**Do not** write FAB chains, executive summary, or section drafts.

## Acquisition lens (secondary)

For stated factor-by-factor decode, point users to Intel **Evaluation decoder** (chat). This skill may **reference** eval factors in links but does not replace the decoder table.

For FAR traps and CO errors, hand off to `compliance-auditor` or deprecated `rfp-reverse-engineer` via Briefings related skill.