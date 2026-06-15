---
name: mission-readiness-framer
description: Frames program-office customer intent from the full solicitation package (PWS/SOW, background, QASP, deliverables, evaluation criteria, amendments) in the active Theseus KG. Builds a Mission Readiness Frame — the readiness outcome the customer owns, workload enablers the contract instruments, pain points, importance signals, implicit criteria, and win-theme candidates. USE WHEN the user asks for mission readiness, customer intent, program office priorities, readiness frame, pain points, importance, hidden criteria, win-theme seeds, or what the customer really wants from this procurement. Emits mission_readiness_frame.json for proposal-generator. DO NOT USE FOR stated evaluation-factor tables (Intel Evaluation decoder), FAR clause audits (compliance-auditor), CO acquisition-trap forensics (deprecated rfp-reverse-engineer), or proposal prose (proposal-generator).
license: MIT
metadata:
  personas_primary: capture_manager
  personas_secondary: [proposal_manager, program_manager]
  shipley_phases: [capture, strategy]
  capability: analyze
  skill_role: orchestrator
  skill_family: readiness-frame
  skill_family_label: Mission Readiness Frame
  runtime: tools
  category: capture_intelligence
  version: 1.7.0
  status: active
  research_harness:
    plan_surfaces_path: references/plan_surfaces.json
    deliverables: [mission_readiness_frame.json, brief.md]
    frame_artifact: mission_readiness_frame.json
    always_resynthesize: true
    synthesis_max_tokens: 48000
    min_brief_chars: 12000
    min_brief_lines: 100
    coverage_contract:
      artifact_path: mission_readiness_frame.json
      required_entity_types: [evaluation_factor, subfactor]
      rule: one_row_per_entity
      rows_key: eval_crosswalk
  auto_emit_formats: md, json, docx
  max_turns: 40
  depth_extension_turns: 20
---

# Mission Readiness Framer (chain orchestrator / compiler)

## One-click briefing (user UX)

Intel → **Mission Readiness Frame** → Run triggers preset `mission-readiness` automatically. The user does **one** action; the platform runs six retrieve-only micro-skills in order, then this compiler step. No manual step picks, no Studio wiring, no separate solo invokes.

## Chain compiler mode (`role: compiler`)

When `chain_step_context.role` is **compiler** (solo `compile` step or final chain node):

1. **Do not retrieve** — platform merges upstream `*_handoff.json` artifacts deterministically.
2. **Do not** call `kg_entities` / `kg_chunks` — `retrieval_plan.json` is empty; harness marks retrieve complete.
3. Platform writes `mission_readiness_frame.json` + `brief.md` from merged handoffs — your tool loop should **stop immediately** after merge.
4. `brief.md` must pass depth gate: multi-paragraph analytical prose per section, numbered `[N]` citation markers, verbatim Section M factor labels in `eval_crosswalk[]` (inherited from eval handoff), acronyms as Full Term (ACR).
5. Upstream slice quality is proven at solo eval — compiler does not re-reason pains/eval/themes from scratch.

When invoked **standalone** (no compiler role), execute the full retrieval plan below. See `docs/SKILL_DECOMPOSITION.md` for the decomposition map.

## Philosophy (read first)

| Role | Who | Lens |
| ---- | --- | ---- |
| **Customer** | Program office / requirement owner | Readiness outcome they own |
| **Workload** | PWS/SOW tasks, deliverables, SLAs | How the contract instruments readiness |
| **Administrator** | CO / contracts shop | How workload is bought and scored |

**Contracts are not the mission.** They are workload that enables the greater mission the customer is accountable for — usually tied to some form of **readiness**.

## When to Use

- "Build the Mission Readiness Frame for this package"
- "What does the program office really care about?"
- "What readiness outcome is this procurement instrumenting?"
- "What are the customer pain points and importance signals?"
- "What are the tea leaves / implicit criteria?"
- "What win-theme candidates should we seed?"

## Operating discipline

- **Package-wide input.** UCF, FOPR, BPA call, task order, OTA — normalize silently. Always read **PWS/SOW + background + QASP + eval + amendments** as one signal field.
- **No invention.** Every entry cites `source_chunk_ids[]` or `[entity: …]` from tool output. Silent topics → `clarification_questions[]` or `claim_gaps[]`.
- **Program office first.** Do not describe the CO as the customer. CO/eval mechanics belong in `acquisition_read` or importance signals tagged `source_role: co`.
- **Seeds not prose.** `win_theme_candidates[]` only — no FAB chains, exec summary, or section drafts (`proposal-generator`).
- **Depth over speed.** A thin envelope with generic language is a failed run — not because it missed a number, but because it failed to **cover this solicitation**. Keep retrieving until the package surfaces below are addressed or honestly logged in `claim_gaps[]`.
- **Research harness (platform).** Retrieval evidence auto-accumulates in `artifacts/research_scratchpad.md`. Deliverable writes are blocked until the retrieve phase completes; the platform then **always** runs a **synthesis pass** (research-depth brief from the full scratchpad, target >=12K chars / ~8+ pages) and **reflexion revise** passes if depth audit fails. Your job in the tool loop: retrieve thoroughly, draft complete `mission_readiness_frame.json`, then stop — **do not** polish `brief.md`; platform synthesis writes the long-form narrative.

## Completeness contract (solicitation-driven — no fixed counts)

Coverage is measured against **what this RFP actually contains**, not universal minimums. After step 1, every material item you retrieved must be reflected in outputs or explicitly deferred in `claim_gaps[]`.

| Package surface | Completeness rule |
| --------------- | ----------------- |
| `evaluation_factor` / `subfactor` entities | **One `eval_crosswalk[]` row each** — never collapse multiple factors into one row |
| PWS/SOW task clusters & CDRL families | Represented in `workload_enablers[]`, `current_methods[]`, and cross-walk `pws_clusters[]` |
| QASP / performance standards | Reflected in pains, importance signals, or verbatim extracts |
| Background / amendments | Reflected where they change readiness read or eval emphasis |
| `customer_pain_points[]` | Every **material** program-office pain the package supports — include latent/structural where evidence exists; each with `rationale` |
| `innovation_opportunities[]` | Grounded opportunities for this scope — quality/cost lens; honest `fit_to_scope` |
| `verbatim_extracts[]` | Representative **verbatim** government phrases (≤ 40 words) for the spine of the procurement |
| `win_theme_candidates[]` | Priority-ranked seeds tied to the readiness story — as many as the package warrants |
| `brief.md` | Executive-ready capture narrative covering every section in step 8 — not a stub |

**Final response rule:** Your last assistant message MUST be the **full text of `brief.md`** (copy it verbatim into the chat response). **Never** return a cover note that only points at artifact paths — that is a failed run.

## Citation discipline (narrative)

**Class A (facts):** end with `[chunk-xxxx]`, `[entity: Name]`, `[see <jsonpath>.source_chunk_ids]`, or document section ids (`Section M.2`, `PWS 3.4`, `Attachment J-1`).

**Class B (judgment):** frame with `Our read:`, `Play:`, `Likely`, `In our capture experience,`, `Signal:`, `Pattern:` — do not use Class B to dodge citing facts.

## Workflow

### 1. Pull full-package context

```json
{
  "types": [
    "solicitation",
    "document_section",
    "requirement",
    "deliverable",
    "proposal_instruction",
    "evaluation_factor",
    "subfactor",
    "performance_standard",
    "transition_activity",
    "government_furnished_item",
    "clause",
    "amendment",
    "period_of_performance",
    "place_of_performance",
    "pain_point",
    "customer_priority"
  ],
  "limit": 400
}
```

Follow the platform **retrieval plan** injected at run start (`artifacts/retrieval_plan.json`):

1. One **`kg_entities`** pass on the type slice above (must include `evaluation_factor`, `subfactor`).
2. One **`kg_chunks`** pass per plan surface — in order:

| Phase | Surfaces | Feeds |
| ----- | -------- | ----- |
| Package mechanics | background → PWS/SOW → QASP → evaluation → transition | frame spine, eval cross-walk |
| Mission-connection | modernization → innovation → operational mission → tea leaves | `current_methods[]`, `innovation_opportunities[]`, `importance_signals[]`, `implicit_criteria[]` |
| **Shipley capture** | **pains** → **needs/wants** → **win themes** | `customer_pain_points[]`, buying vision / priorities, `win_theme_candidates[]` |

Shipley here means capture intelligence (pains, needs, theme **seeds**) — not proposal prose, FAB chains, or competitive ghosting (`proposal-generator`, `competitive-intel`).

Use the suggested query for each surface. Do **not** collapse innovation/modernization into the generic PWS pass — they are separate inquiry passes grounded in `differentiation_exploration.md`.

Do **not** repeat queries or re-hit a saturated surface (0 new chunks). If a surface lacks evidence, log it in `claim_gaps[]` and move on — do not loop retrieval indefinitely.

Only add extra `kg_chunks` for user-mentioned sections, **capability overlay** URLs/vendors, or explicit `write_file` blocks **after** the plan is complete.

### 2. Build Mission Readiness Frame

Load `references/readiness_signal_catalog.md`. Emit `mission_readiness_frame`:

- `readiness_outcome` — customer's priority (explicit or proxy)
- `failure_modes_feared[]`
- `workload_enablers[]` — PWS/SOW clusters linked to readiness
- `readiness_signals[]` — `explicit` or `proxy`
- `confidence` — honest when proxies dominate
- `our_read` — one-line judgment that contract = enabler, not mission

### 3. Map customer pain points

Load `references/customer_intent_signals.md` and `references/differentiation_exploration.md`. Emit `customer_pain_points[]` — **explicit and non-obvious** (latent/structural). Each entry: `visibility`, `challenge_type`, `rationale` (signal → readiness → response), `source_role: program_office`, `readiness_link`, `recommended_response_type`.

### 3b. Map current methods and innovation opportunities

From PWS/SOW and attachments, emit `current_methods[]` (what the customer already uses to perform the workload).  
Then emit `innovation_opportunities[]` — methods or technology that improve **quality, cost, or both**; cite scope fit honestly.

### 4. Cross-walk and importance signals

Triangulate background ↔ PWS/SOW ↔ QASP ↔ eval ↔ amendments. Emit `importance_signals[]` with correct `signal_type` and `source_role`.

### 5. Surface implicit criteria (tea leaves)

Emit `implicit_criteria[]` with `customer_read`, `acquisition_read`, `alternate_read` (required unless `confidence: high`), and `linked_evaluation_factors[]`.

### 6. Seed win-theme candidates

Priority-ranked entries (`priority` 1…n), each with `rationale_chain` (signal → consequence → angle → proof → differentiation hypothesis), `readiness_link`, `proof_required[]`, `evaluation_factor_links[]`.

### 6b. Verbatim extracts and eval cross-walk

Emit `verbatim_extracts[]` — quote the government's own phrases (not paraphrase).  

Emit `eval_crosswalk[]` — **one row per material evaluation factor and subfactor** surfaced in step 1 (`evaluation_factor`, `subfactor` entities). Do not collapse multiple technical factors into one row. Each row MUST include:

- `evaluation_factor` — exact government label
- `pws_clusters[]` — 2+ task areas / CDRL families tied to the factor
- `readiness_link` — 2–4 sentences on readiness consequence if the factor is weak
- `proof_expected` — what evidence the evaluator will look for
- `source_chunk_ids[]`

If a factor is missing from the package, document it in `claim_gaps[]` — never silently omit technical factors you retrieved.

### 6c. User-directed capability overlay (when prompt names vendor/platform/URL)

When the user asks whether a **named company, product, or platform** (with or without a URL) can address pains or add value:

1. Call `web_fetch` / `web_research` on every URL provided (and `web_search` for the vendor + product if needed).
2. Emit `capability_overlay` in JSON with `vendor`, `sources[]`, `platform_capabilities[]` (cited from web evidence), `pain_point_mappings[]` (link to relevant `customer_pain_points[]`), and `innovation_links[]` (link to `innovation_opportunities[]`).
3. Extend `innovation_opportunities[]` with entries that cite **both** solicitation scope (PWS/QASP chunk) **and** the external capability where applicable.
4. Write a dedicated brief section `## Capability overlay (user-directed)` — substantive capability summary, pain-by-pain applicability, risks/`fit_to_scope`, and what proof a capture lead would need next.

**Do not** satisfy an overlay request with a closing paragraph or two bullets. The overlay is a first-class deliverable when the user asks for it.

### 7. Assemble JSON envelope

Load `references/output_contract.md`. Write `{run_dir}/artifacts/mission_readiness_frame.json` via `write_file`.

### 8. Render brief

Platform synthesis writes `{run_dir}/artifacts/brief.md` after your JSON draft — a **research-depth, capture-manager-ready** narrative (not a summary stub):

1. Mission Readiness Frame (outcome, failure modes, enablers, our read)
2. Verbatim signal bank (top extracts with commentary)
3. Customer pain and importance — include **non-obvious** pains with rationale
4. Current methods vs innovation opportunities (quality/cost lens, value without bloat)
5. Eval cross-walk table — **full markdown table**, one row per factor/subfactor (not a 4-row sample)
6. Implicit criteria / tea leaves with alternate reads
7. Win-theme candidate spine (priority-ranked seeds + rationale chains + proof checklist)
8. Capability overlay (user-directed) — **required when prompt names vendor/platform/URL**
9. Clarification questions + claim gaps

Load `references/narrative_template.md` if losing structure.

### 9. Self-audit

Confirm solicitation completeness. Every retrieved eval factor cross-walked; every factual claim anchored; every judgment visibly framed; gaps in `claim_gaps[]`.

### 10. Return the brief as your final message

Copy the complete `brief.md` content into your final assistant response. Do not summarize or point at files.

## What this skill does NOT cover

- **Factor-by-factor eval tables** → Intel Evaluation decoder (chat)
- **FAR trap / CO error forensics** → `compliance-auditor` or deprecated `rfp-reverse-engineer`
- **Proposal prose / FAB / themes narrative** → `proposal-generator`
- **Competitor / incumbent fingerprinting** → `competitive-intel`
- **Pricing** → `price-to-win`

## References

- [references/output_contract.md](references/output_contract.md) — JSON envelope schema
- [references/readiness_signal_catalog.md](references/readiness_signal_catalog.md) — readiness and proxy patterns
- [references/customer_intent_signals.md](references/customer_intent_signals.md) — pain, importance, cross-walk, tea leaves
- [references/differentiation_exploration.md](references/differentiation_exploration.md) — latent pains, current methods, innovation, lean-delivery differentiation ideation
- [references/narrative_template.md](references/narrative_template.md) — optional bullet skeleton for brief.md