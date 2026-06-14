# Readiness output contract

Applies to all `readiness-frame-*` handoffs and the compiled `mission_readiness_frame.json` / `brief.md`.

## Voice and terminology

- Plain English capture reasoning — write like a strong capture lead briefing the team.
- Use customer document terminology (factor names, PWS section labels, deliverable titles) verbatim when grounded.
- Expand acronyms on first use: **Full Term (ACR)** — e.g. Quality Assurance Surveillance Plan (QASP).
- Every substantive claim cites `source_chunk_ids[]` or `[chunk-…]` in prose.

## eval_crosswalk row shape

```json
{
  "evaluation_factor": "Factor 2 — Technical Approach",
  "pws_clusters": ["PWS 3.2 Production planning", "CDRL A001 staffing plan"],
  "readiness_link": "2–3 sentences: how weak performance on this factor degrades the program-office readiness outcome the customer owns.",
  "proof_expected": "Concrete artifacts evaluators will look for — past performance narrative, staffing matrix, transition schedule — tied to Section L instructions.",
  "source_chunk_ids": ["chunk-abc123"]
}
```

### BAD (boilerplate — never emit)

| Field | Example |
| --- | --- |
| `pws_clusters` | `["Section M / PWS task clusters — refine during capture review"]` |
| `readiness_link` | `Weak performance on Factor 1 degrades program readiness and eval confidence.` |
| `proof_expected` | `Proposal must demonstrate compliant approach, staffing, and proof for Factor 1.` |

### GOOD

| Field | Example |
| --- | --- |
| `pws_clusters` | `["PWS 2.1 Shipboard maintenance milestones", "QASP Table 4 on-time delivery"]` |
| `readiness_link` | `The program office needs continuous fleet readiness; Factor 2 proof must show the contractor can meet production-planning CDRLs without compounding maintenance delays cited in Section M.` |
| `proof_expected` | `Volume III must map each PWS 2.1 task to a named production-control method, cite surge staffing for hull availability, and cross-reference the 40-page technical limit in Section L.` |

## Coverage discipline

- One row per **material** `evaluation_factor` / `subfactor` retrieved — no collapsing subfactors.
- Exclude KG meta labels (rating scales, SSDD boilerplate, methodology descriptors).
- Missing factors → `claim_gaps[]` only. **Never** auto-scaffold rows.

## Batched eval workflow (`readiness-frame-eval`)

1. `kg_entities` with `evaluation_factor` + `subfactor` — inventory all material factors.
2. Batch factors in groups of **5–8**; per batch run targeted `kg_chunks` on that batch's neighborhood.
3. Synthesize `eval_crosswalk[]` rows **only for the current batch** before advancing.
4. Repeat until inventory is covered or remaining factors are logged in `claim_gaps[]`.

## Compiler (`mission-readiness-framer`)

- Merge upstream `*_handoff.json` artifacts — do not re-reason slices already present in handoffs.
- Produce `mission_readiness_frame.json` + analytical `brief.md` with an Eval cross-walk section mirroring substantive rows.