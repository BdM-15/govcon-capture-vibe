# Skill Taxonomy — Three-Axis Classification

**Status:** Authoritative (Phase 4j, branch `135-phase-4j-skill-taxonomy`).
**Audience:** Skill authors, UI implementers, extraction-prompt maintainers,
agents discovering skills programmatically.
**Companion docs:** [SKILLS.md](SKILLS.md), [skills_roadmap.md](skills_roadmap.md),
[SKILL_SPEC_COMPLIANCE.md](SKILL_SPEC_COMPLIANCE.md).

---

## 1. Why three axes (not one, not free-form tags)

Skills answer different questions for different people. A flat `category`
field collapses them to one dimension; free-form tags drift. We adopt
three orthogonal axes so the same skill catalog can be sliced for
discovery without misclassification:

| Axis             | Question it answers                  | Discovery surface                               |
| ---------------- | ------------------------------------ | ----------------------------------------------- |
| `personas_*`     | **Who you are** on the capture team  | Filter pill row + "also for…" badge on cards    |
| `shipley_phases` | **When in the lifecycle** you'll use | Filter pill row at top of skills page           |
| `capability`     | **What action** you need right now   | Filter pill row + command-palette quick-routing |
| `skill_role`     | **How the skill is invoked**         | Skills page section: orchestrators vs slices    |
| `skill_family`   | **Which decomposition family**       | Skills page collapsible family sections         |

Each axis is closed-vocabulary: unknown values fail the contract test in
[tests/skills/test_skill_taxonomy.py](../tests/skills/test_skill_taxonomy.py).
Adding a new value requires updating this doc, the contract test, the
extraction prompt (for personas), and any UI filter chips in the same PR.

---

## 2. Persona vocabulary (8 IDs + `none`)

Mirrors the persona list in
`prompts/govcon_prompt.py` → `_build_v8_system_prompt()` Part A
verbatim. **If a persona is added/removed there, update both files in the
same commit.** Cross-Cutting Change Checklist item 7 enforces this.

| ID                  | Shipley role             | What they need                                            |
| ------------------- | ------------------------ | --------------------------------------------------------- |
| `capture_manager`   | Capture Manager          | Win themes, hot buttons, discriminators, competitor reads |
| `proposal_manager`  | Proposal Manager         | Compliance matrices, outlines, Section L↔M traceability   |
| `proposal_writer`   | Proposal Writer          | Requirement details, FAB chains, narrative drafts         |
| `cost_estimator`    | Cost Estimator / Pricer  | BOEs, wrap rates, PTW, workload drivers                   |
| `contracts_manager` | Contracts / Subcontracts | FAR/DFARS clauses, terms, CLINs, sub SOWs                 |
| `technical_sme`     | Technical SME            | Performance standards, specs, QA criteria                 |
| `legal_compliance`  | Legal / Compliance       | OCI sweeps, certs/reps, IP terms, regulatory obligations  |
| `program_manager`   | Program Manager          | CDRLs, deliverable schedules, milestones, post-award      |
| `none`              | (utility / meta)         | No persona — skill serves any agent (renderers, ontology) |

`personas_primary` is required (one ID). `personas_secondary` is optional
(zero or more IDs). `none` may only appear as `personas_primary`; it is
never a secondary.

---

## 3. Shipley phase vocabulary (6 phases)

Six phases of the Shipley Business Development Lifecycle. A skill MAY
span multiple phases (e.g., `price-to-win` works in capture AND
proposal-development). `shipley_phases` is a list; empty list means
"phase-agnostic utility".

| Phase                  | Trigger                                                               |
| ---------------------- | --------------------------------------------------------------------- |
| `pursuit`              | Pre-RFP qualification, opportunity ID, gate reviews                   |
| `capture`              | Customer engagement, competitive analysis, teaming, PWin shaping      |
| `strategy`             | Win strategy, theme development, solution architecting, color reviews |
| `proposal_development` | Outline, write, review, produce, submit                               |
| `negotiation`          | FPR, clarifications, BAFO, post-submission Q&A                        |
| `post_award`           | Kickoff, transition, CDRL execution, modifications, recompete prep    |

---

## 4. Capability vocabulary (7 verbs, closed)

What the skill **does**, in one verb. Used for command-palette quick
routing ("[draft] for [proposal_manager] in [proposal_development]").

| Verb       | Action                                                                  |
| ---------- | ----------------------------------------------------------------------- |
| `research` | Gathers from external sources (MCPs, web, USAspending, eCFR)            |
| `analyze`  | Examines KG / documents, produces findings, no new prose                |
| `draft`    | Produces narrative artifacts for proposals (outlines, sections, SOWs)   |
| `audit`    | Validates against rules / regulations / OCI / compliance matrices       |
| `estimate` | Produces quantitative models (cost stacks, PTW, workload rollups)       |
| `render`   | Converts structured content to deliverable formats (DOCX/XLSX/PDF/PPTX) |
| `meta`     | Operates on other skills or the ontology itself                         |

---

## 5. Frontmatter shape

Added to the existing `metadata:` block — **flat keys, no new top-level
YAML fields** (the in-tree YAML parser at
[src/skills/manager.py](../src/skills/manager.py) accepts only one level
of nesting under `metadata:`, and we keep it that way for spec
portability across Claude Code / Cursor / Copilot).

```yaml
---
name: price-to-win
description: …
license: MIT
metadata:
  # — Phase 4j taxonomy —
  personas_primary: cost_estimator
  personas_secondary: [capture_manager]
  shipley_phases: [capture, strategy, proposal_development]
  capability: estimate
  # — existing pre-4j keys, unchanged —
  runtime: tools
  category: pricing
  version: 0.2.0
  status: active
  mcps: [bls_oews, gsa_calc, gsa_perdiem]
---
```

Notes:

- `personas_primary` is a **scalar** string. `personas_secondary` and
  `shipley_phases` are **lists** (use `[a, b]` inline form for ≤3 items,
  block form for longer lists).
- `capability` is a single string.
- All four keys are required for skills with `personas_primary != none`.
  Utility skills (`personas_primary: none`) MAY omit `shipley_phases` (or
  leave it `[]`) but must still declare `capability`.
- The existing `category` key is **not removed** — it survives as a
  short, free-form badge for the card UI. Taxonomy axes drive grouping
  and filtering; `category` is decoration.

---

## 6. Backfill matrix (current state)

Core GovCon/platform skills use the closed taxonomy axes directly:

| Skill                       | `personas_primary` | `personas_secondary`                  | `shipley_phases`                                   | `capability` |
| --------------------------- | ------------------ | ------------------------------------- | -------------------------------------------------- | ------------ |
| `competitive-intel`         | capture_manager    | [cost_estimator, proposal_manager]    | [pursuit, capture, strategy]                       | research     |
| `compliance-auditor`        | legal_compliance   | [proposal_manager, contracts_manager] | [proposal_development, negotiation]                | audit        |
| `govcon-ontology`           | none               | []                                    | []                                                 | meta         |
| `huashu-design`             | none               | []                                    | [proposal_development]                             | render       |
| `oci-sweeper`               | legal_compliance   | [capture_manager, contracts_manager]  | [pursuit, capture]                                 | audit        |
| `price-to-win`              | cost_estimator     | [capture_manager]                     | [capture, strategy, proposal_development]          | estimate     |
| `proposal-generator`        | proposal_writer    | [proposal_manager, capture_manager]   | [proposal_development]                             | draft        |
| `data-analyzer`             | none               | []                                    | []                                                 | analyze      |
| `renderers`                 | none               | []                                    | []                                                 | render       |
| `workload-analyzer`         | cost_estimator     | [capture_manager]                     | [capture, strategy]                                | analyze      |
| `mission-readiness-framer`  | capture_manager    | [proposal_manager, program_manager]   | [capture, strategy]                                | analyze      |
| `rfp-reverse-engineer`      | capture_manager    | [proposal_manager]                    | [capture, strategy]                                | analyze      |
| `skill-creator`             | none               | []                                    | []                                                 | meta         |
| `subcontractor-sow-builder` | contracts_manager  | [program_manager, capture_manager]    | [strategy, proposal_development, post_award]       | draft        |

**Developer-tool skills** (not govcon platform skills — no KG queries; classified as `personas_primary: none`, `shipley_phases: []`, and `capability: meta`):

| Skill                           | Note                                                                                                  |
| ------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `caveman`                       | Communication mode modifier                                                                          |
| `diagnose`                      | Disciplined debugging / performance-regression loop                                                   |
| `git-guardrails-claude-code`    | Claude Code hook setup for dangerous git command blocking                                             |
| `grill-me`                      | Developer plan stress-tester; route govcon work to domain skills                                      |
| `grill-with-docs`               | Plan stress-testing against repo domain language and documentation                                    |
| `handoff`                       | Conversation handoff document writer                                                                 |
| `improve-codebase-architecture` | Architecture deepening / refactoring analysis                                                         |
| `prototype`                     | Throwaway prototype workflow                                                                          |
| `setup-matt-pocock-skills`      | Repository setup for the Matt Pocock engineering skill family                                         |
| `setup-pre-commit`              | Husky / lint-staged / test hook setup                                                                 |
| `tdd`                           | Red-green-refactor loop                                                                               |
| `to-issues`                     | Vertical-slice issue creator                                                                          |
| `to-prd`                        | PRD publisher                                                                                         |
| `triage`                        | Issue triage workflow                                                                                 |
| `write-a-skill`                 | Generic skill authoring workflow                                                                      |
| `zoom-out`                      | Higher-level codebase context request                                                                 |

---

## 7. UI consumption pattern

The **Agent Skills** page ([src/ui/static/views/skills-view.html](../src/ui/static/views/skills-view.html))
is the authoring/tuning surface — every skill card stays visible. **RFP Intelligence**
is the operator surface for heavy-lifting workflows (e.g. Mission Readiness Frame).

Skills page layout (view modes: **Families** · **Orchestrators** · **All flat**).
Sections use the same `<details class="acc">` accordion as Settings:

1. **Utility & Infrastructure** (top) — `personas_primary: none` or `capability: meta`.
2. **Orchestrators** — `skill_role: orchestrator`; open by default; subtitle shows `chain.accepts` handoffs.
3. **Family sections** — skills sharing `skill_family` (e.g. all `readiness-frame-*` slices).
4. **Standalone domain** — `skill_role: standalone` with no family.

Filter rail (orthogonal to grouping):

- **Persona / Phase / Capability pills** — toggleable OR-filters.
- **Search** — name + description tokens.

When a card has `personas_secondary`, those personas surface as small
"also relevant for: …" tags on the card itself.

### 7.1 `skill_role` vocabulary

| Value          | Meaning |
| -------------- | ------- |
| `standalone`   | User invokes directly; not a chain slice |
| `slice`        | Narrow handoff producer inside a family |
| `orchestrator` | Compiles multiple upstream handoffs into deliverables |

### 7.2 `skill_family` metadata

Optional slug grouping related skills. Known families:

| `skill_family`      | Label                    | Example skills |
| ------------------- | ------------------------ | -------------- |
| `readiness-frame`   | Mission Readiness Frame  | `readiness-frame-*`, `mission-readiness-framer` |
| `pricing`           | Pricing & Workload       | `workload-analyzer`, `price-to-win` |
| `proposal-pipeline` | Proposal Pipeline        | `proposal-generator`, `subcontractor-sow-builder` |
| `capture-intel`     | Capture Intelligence     | `competitive-intel` |
| `compliance`        | Compliance & Risk        | `compliance-auditor`, `oci-sweeper` |

Convention fallback: `readiness-frame-*` prefix → family `readiness-frame` when metadata omits `skill_family`.
Chain enrichment (`chain.accepts`, `chain.produces`, `upstream_skills`, `downstream_skills`) is attached in `enrich_skill_summary()` from [src/skills/chain_contracts.py](../src/skills/chain_contracts.py).

---

## 8. Cross-cutting change discipline

Updating any vocabulary in this doc requires (per Cross-Cutting Change
Checklist item 7 in [.github/copilot-instructions.md](../.github/copilot-instructions.md)):

1. Update this doc's vocabulary table(s).
2. Update `prompts/govcon_prompt.py` → `_build_v8_system_prompt()` Part A persona
   list (for `personas_*` changes only).
3. Bump every affected SKILL.md frontmatter in the same commit.
4. Update [tests/skills/test_skill_taxonomy.py](../tests/skills/test_skill_taxonomy.py)
   enums.
5. Update UI filter pills in `index.html` (and Tailwind class allowlist
   if a new persona needs a new color).
6. Run `.\.venv\Scripts\python.exe -m pytest tests/skills/ -v` and
   confirm the contract tests still pass.

No PR that adds/removes a persona, phase, or capability lands without
all six steps.
