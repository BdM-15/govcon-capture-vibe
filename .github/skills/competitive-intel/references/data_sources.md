# Data Sources — what's wired, what's not (Phase 4e)

## Wired: USAspending MCP (`mcp__usaspending__*`)

55 read-only tools over the public USASpending.gov API. No API key. Vendored
via `tools/mcps/usaspending/theseus_manifest.json`. Full vendor + re-vendor
notes: [tools/mcps/usaspending/UPSTREAM.md](../../../../tools/mcps/usaspending/UPSTREAM.md).

### Tools the workflow uses

| Tool                      | Purpose                                                                                      | When in workflow              |
| ------------------------- | -------------------------------------------------------------------------------------------- | ----------------------------- |
| `autocomplete_naics`      | Resolve "custom computer programming" → 541512                                               | Step 2 (fuzzy code resolve)   |
| `autocomplete_psc`        | Resolve "IT support" → R499 etc.                                                             | Step 2                        |
| `get_psc_filter_tree`     | Drill down PSC hierarchy when prefix only                                                    | Step 2 (rare)                 |
| `list_toptier_agencies`   | Resolve "Air Force" → toptier code 5700                                                      | Step 2                        |
| `search_awards`           | Pull award history (the spine)                                                               | Workflow A Step 3             |
| `lookup_piid`             | Match a workspace PIID to its USAspending award_id                                           | Step 4                        |
| `spending_by_category`    | Top vendors / top NAICS aggregations for pricing benchmark                                   | Workflow A Step 6             |
| `autocomplete_recipient`  | Recipient name → recipient_hash                                                              | Step 5                        |
| `get_recipient_profile`   | Parent recipient, business types, total federal $                                            | Step 5                        |
| `get_recipient_children`  | Subsidiaries (for parent-vs-sub disambiguation)                                              | Step 5 (optional)             |
| `get_transactions`        | Modification-level obligations, action dates, and action-type metadata                       | Workflow A Step 7, Workflow B |
| `get_award_detail`        | Full single-award context (NAICS, PSC, place of perf, agency, award description, POP fields) | Step 4 (verification)         |
| `get_idv_children`        | Enumerate child orders under an IDV                                                          | Workflow B                    |
| `get_idv_activity`        | Child activity rollup for an IDV                                                             | Workflow B                    |
| `get_idv_amounts`         | Top-line parent IDV rollup                                                                   | Workflow B (optional)         |
| `spending_by_transaction` | Award transaction search when direct transaction pull is thin                                | Workflow B (fallback)         |

### Award type codes (used in `search_awards.filters.award_type_codes`)

| Code | Meaning                              |
| ---- | ------------------------------------ |
| A    | BPA Call                             |
| B    | Purchase Order                       |
| C    | Delivery Order                       |
| D    | Definitive Contract                  |
| IDV  | Indefinite Delivery Vehicle (parent) |

For competitive-intel Workflow A, `["A", "B", "C", "D"]` covers the
order/contract spectrum. For Workflow B (vehicle hierarchy / obligation
rollups), include `"IDV"` when parent-vehicle context is required.

## Linkage strategy for multiple-award IDIQs

Do not rely on solicitation identifier alone. Use this precedence:

1. **Parent/child IDV linkage** (`get_award_detail` + `get_idv_children`/`get_idv_activity`)
2. **PIID family context** (`lookup_piid` + award detail corroboration)
3. **Solicitation identifier clustering** (fallback only)

Why: solicitation identifier can over-cluster unrelated actions and under-link
cross-agency ordering behavior. Parent/child linkage is the strongest evidence
for competitor completeness in multiple-award vehicles.

### Scenario handling (Workflow B / C)

Theseus exposes a deterministic obligation helper named `collect_competitive_obligation_intel`. It orchestrates the sequence below, writes `artifacts/competitive_intel_obligation.json`, and returns a compact summary to the model so large child-order rollups no longer depend on turn budget or tool-payload truncation. Workflow B uses it for parent-level synthesis. Workflow C uses the same data for one-award grouped analysis. The collector also emits `insights.headline` plus ordered `insights.blocks[]` so the final cover note can start from deterministic story seeds instead of only raw rollups.

| Scenario            | Primary path                                                                                                              | Required outputs                                                 |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| Standalone contract | `lookup_piid` -> `get_award_detail` -> `get_transactions`                                                                 | total obligations, by-POP, by-FY, by-mod                         |
| Parent IDIQ         | `lookup_piid` -> `get_award_detail` -> `get_idv_children`/`get_idv_activity` -> per-child `get_transactions`              | parent vs children totals, by-order breakdown, child POP windows |
| IDIQ order          | `lookup_piid` -> `get_award_detail` (resolve parent) -> sibling pull via parent traversal -> per-order `get_transactions` | this-order totals, current POP, full-vehicle rollup              |

Always preserve negative obligation periods (deobligations). Report both gross
and net totals.

The collector also emits grouped `award_rollups` in tool output and `obligations.by_award` in the artifact so order-level prose can stay clean without re-sorting the flattened transaction list.

### Known detail quality limits

- **Fiscal year totals** are reliably derivable from transaction action dates.
- **Period-of-performance windows** are often available from `get_award_detail` and `get_idv_activity`, but they may reflect current or potential end dates rather than a perfect option-period segmentation. Per-modification POP start/end dates are **not** in the USAspending transaction payload — option-year boundaries must be inferred from the sequence of action-type G ("EXERCISE AN OPTION") action dates.
- **Modification descriptions** are not guaranteed on every transaction record. Preserve narrative text when present; otherwise keep the modification number, action date, and action-type metadata and emit a warning instead of fabricating a description.

### Derived fields (computed by the skill, not from USAspending)

These fields do **not** come from MCP calls — the skill computes them from fetched data:

| Derived field              | How computed                                                                                                                                                                                                       |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `cumulative_obligated_usd` | Running sum of `amount_usd` across `by_transaction`, sorted by `action_date` ascending. Respects negative deobligations.                                                                                           |
| `inferred_pop_segment`     | First transaction → `base_year`. Each action-type `G` in sequence → `option_year_1`, `option_year_2`, etc. Action-type `B`/`J` within a segment → `supplemental`. `M`/`X`/`R` → `admin`. Null/unknown → `unknown`. |
| `rate_analysis`            | Computed from `net_obligated_usd` and the strongest POP window in `by_period_of_performance`. `monthly_burn_usd` = net / months. `by_option_year` uses G-type action dates as segment boundaries.                  |
| `insights`                 | Deterministic narrative seed built from `rate_analysis`, `award_rollups`, child-order concentration, competitor completeness, PTW baseline, and warnings. `headline` is opener. `blocks[]` provide ordered prose anchors. |

Always include `derivation_notes` in `rate_analysis` to document which POP window and assumptions were used.

## NOT wired (declared `claim_gaps` in every output)

| Source             | Why not                                                       | Workaround                                       |
| ------------------ | ------------------------------------------------------------- | ------------------------------------------------ |
| SAM.gov entity API | Phase 4f — `sam-gov` MCP not yet vendored (key-gated)         | User confirms business size / set-aside manually |
| FPDS-NG ATOM       | Phase 4f — `fpds` MCP not yet vendored                        | USAspending covers most of the same data         |
| CPARS              | No public MCP source — DoD CAC + role required                | Manual export by user                            |
| Protest decisions  | No public MCP source                                          | GAO web search by user                           |
| News / leadership  | No web-search MCP wired yet                                   | User research                                    |
| GSA eLibrary       | Phase 4f — `gsa-calc` covers labor rates but not SIN coverage | Manual lookup                                    |

Always emit these in the output's `claim_gaps` so the user knows what's
missing before they walk into a red team.

## Politeness / rate limits

USAspending is unauthenticated and unmetered, but the upstream MCP server
already throttles + retries on 429. Don't hammer it — the workflow is
designed to need ~6-10 tool calls per run, not hundreds.
