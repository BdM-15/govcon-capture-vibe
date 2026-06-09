---
name: workload-analyzer
description: "Analyzes federal contract workload attachments (Section J spreadsheets, PWS data tables, site lists, demand history) to identify pricing risks, demand trends, geographic concentration, and hidden modeling assumptions — then produces a structured handoff to price-to-win. USE WHEN the user uploads or references a workload spreadsheet, sites list, demand history table, staffing table, CLIN volume estimate, or any Section J attachment with quantitative data. Also triggers on 'analyze this workload', 'what does this data tell us about staffing', 'help me understand site scope', 'workload trend', 'CM volume', 'site count', or 'what should I price for option years'. Builds on data-analyzer's statistical foundation — do not use data-analyzer directly for govcon workload data; use this skill."
license: MIT
metadata:
  personas_primary: cost_estimator
  personas_secondary: [capture_manager]
  shipley_phases: [capture, strategy]
  capability: analyze
  category: govcon-platform
  version: 1.0.0
  status: active
  runtime: tools
---

# Workload Analyzer

Govcon-specific workload analysis skill that classifies any Section J quantitative
attachment into a known data archetype, applies the matching analytical framework
(borrowing from `data-analyzer`'s EDA and comparative workflows), and emits a
structured pricing-risk summary for `price-to-win` consumption.

**Foundation:** This skill composes `data-analyzer`'s statistical methods — see
`data-analyzer/references/statistical-methods.md` for test selection and
`data-analyzer/references/pitfalls.md` for analytical guardrails. Do not
re-implement those; reference them when depth is needed.

**References (load when needed):**

- `references/archetypes.md` — 4 workload data archetypes + recognition signals
- `references/analysis-frameworks.md` — per-archetype analytical playbook
- `references/ptw-handoff.md` — structured output envelope format for price-to-win
- `assets/report_template.md` — report structure for workload analysis output

---

## Workflow 0: Schema Recognition (always run first)

**Objective:** Classify what data you have before doing any analysis. Let the data
structure and content determine the approach — never assume column names or schema.

1. **Inventory the data** — count sheets/tabs, rows, columns; note column headers
   verbatim; identify any totals rows, notes, or footnotes
2. **Classify each sheet** into one or more archetypes (load `references/archetypes.md`):
   - Geographic Scope
   - Demand/Volume History
   - Manning/Staffing
   - CLIN/Task Structure
3. **Identify the join key** — the field that links sheets together (site code, CLIN ID,
   location name, etc.)
4. **Extract hidden assumptions** — footnotes, adjustment factors, phone-resolution
   percentages, exclusion notes, any multipliers applied to raw data
5. **State what you have** — brief plain-language summary of data shape, date range,
   coverage, and any gaps before proceeding to analysis

> If multiple archetypes are present, run the relevant workflows and synthesize in Workflow 3.

---

## Workflow 1: Geographic Scope Analysis

**Applies to:** Geographic Scope archetype — site lists, location tables, AOR assignments.

1. **Count and classify sites** — total count, CONUS vs. OCONUS split, breakdown by
   country/state/region; flag any unusual locations (remote islands, combat zones, areas
   with restricted access)
2. **Identify geographic concentration** — what percentage of sites are in which regions;
   any single country or state that dominates scope
3. **OCONUS risk tier each location** — use travel burden, SOFA/access constraints,
   per-diem differential, and labor availability as risk dimensions; load
   `references/analysis-frameworks.md` for the tiering rubric
4. **Flag scope anomalies** — duplicate entries, missing location fields, ambiguous
   site names, sites that appear in one sheet but not another
5. **Produce scope summary** — total sites, CONUS/OCONUS counts, high-risk OCONUS
   count, concentration index

---

## Workflow 2: Demand / Volume Analysis

**Applies to:** Demand/Volume History archetype — case counts, ticket volumes, service
requests, PM/CM events, or any unit-of-work × time × location table.

1. **Establish the time series** — identify years/periods covered; compute totals per
   period; calculate year-over-year growth rate
2. **Apply adjustment factors** — locate any phone-resolution ratios, exclusion
   percentages, or multipliers noted in footnotes; apply them to get field-touch volume;
   document each factor explicitly
3. **Run Pareto on site-level volume** — which sites drive 20/50/80% of total volume;
   identify the high-volume outliers by name
4. **Trend analysis** — is volume growing, flat, or declining? Apply `data-analyzer`
   Workflow 2 (Pattern Detection) to the time series; project volume into option years
   using observed growth rate
5. **Volatility analysis** — coefficient of variation per site; flag sites with
   year-over-year swings >30% as pricing risk
6. **Cross-tab with geography** (if sites data available) — join on the shared key;
   compute volume per OCONUS site vs. CONUS site; surface the OCONUS sites with
   highest volume as highest-exposure pricing items

---

## Workflow 3: Synthesis & PTW Handoff

**Objective:** Combine workflow outputs into a ranked pricing-risk list and structured
handoff for price-to-win.

1. **Build the risk register** — each site or CLIN gets a risk score combining:
   - Volume tier (high/medium/low based on Pareto)
   - Geographic tier (OCONUS remote / OCONUS standard / CONUS)
   - Trend direction (growing / flat / declining)
   - Volatility flag (high variance = pricing risk)
2. **Identify the top pricing traps** — items where PWS projections appear flat but
   historical data shows growth; adjustment factors that inflate or deflate apparent
   demand; scope with high OCONUS concentration
3. **Validate PWS vs. actuals** (if both are present) — compare government estimates
   against historical actuals; calculate the gap; assess whether the government is
   underestimating, overestimating, or has a plausible rationale
4. **Produce option-year projections** — apply observed growth rate to base-year
   estimate; show the range (conservative/base/optimistic) for each option period
5. **Format PTW handoff** — load `references/ptw-handoff.md`; emit the structured
   envelope; call out any assumptions the estimator must validate

**Deliverable:** Use `assets/report_template.md` for the output structure.

---

## Quick Reference

| Trigger                                 | Workflow                                    |
| --------------------------------------- | ------------------------------------------- |
| "What sites are covered?"               | Workflow 0 → Workflow 1                     |
| "How much work is there?"               | Workflow 0 → Workflow 2                     |
| "What should I price for option years?" | All three workflows                         |
| "Is the PWS estimate realistic?"        | Workflow 0 → Workflow 2 → Workflow 3 step 3 |
| "Where are my biggest pricing risks?"   | Workflow 3                                  |
| "Analyze this spreadsheet"              | Start at Workflow 0 always                  |

---

## Guardrails

- **Never assume schema** — run Workflow 0 first, every time; column names vary by contract
- **Surface every adjustment factor** — hidden multipliers are pricing traps for the
  estimator who only reads the totals row
- **Distinguish statistical significance from pricing significance** — a site averaging
  0.5 CMs/year is statistically unremarkable but pricing-significant if it is in Diego Garcia
- **Do not extrapolate beyond observed range without flagging it** — option-year
  projections are estimates; label confidence explicitly
- **Cross-reference `data-analyzer/references/pitfalls.md`** before drawing trend
  conclusions from fewer than 3 data points
