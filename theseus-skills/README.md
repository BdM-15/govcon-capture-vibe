# theseus-skills/

This directory is the **Theseus-side organizational view** of the agent skills authored under [`.github/skills/`](../.github/skills/).

We do **not** duplicate skill content here — both VS Code/Copilot and the Theseus runtime read directly from `.github/skills/` (the official `agentskills.io` location). This folder exists only to:

1. Provide a discoverable entry point for repo browsers who don't know the `.github/` convention
2. Host any **Theseus-runtime-only** tooling (eval harnesses, mock context fixtures, integration tests) that should not pollute the agent-discoverable directory
3. Document Theseus-specific invocation contracts that go beyond the cross-platform SKILL.md

## Skill tiers

Every skill under `.github/skills/` falls into exactly one of three tiers, controlled by `metadata:` in the skill's SKILL.md frontmatter:

| Tier                 | `metadata.developer_only`            | Shown in Theseus UI?                | Queries KG / workspace? |
| -------------------- | ------------------------------------ | ----------------------------------- | ----------------------- |
| **Theseus platform** | absent or `false`                    | ✅ Yes                              | ✅ Yes                  |
| **Developer-only**   | `true`                               | ❌ No (filtered by `list_skills()`) | ❌ No                   |
| **Dual-purpose**     | absent or `false` + KG-optional body | ✅ Yes                              | Optional                |

All skills under `.github/skills/` are Copilot Chat skills by the agentskills.io spec — both tiers are invokable from Copilot Chat by a developer. Copilot Chat is developer-side only and does not serve as a Theseus platform agent for end users. The tier distinction controls only what appears in the Theseus UI.

When adding a new skill, pick the tier first and set `metadata.developer_only` accordingly. The `src/skills/manager.py` `list_skills()` method enforces the UI filter automatically.

## Index — Theseus platform skills

Skills shown in the Theseus govcon UI. Query the active workspace KG and use govcon personas.

| Skill                     | Source of truth                                              | Theseus runtime adapter        |
| ------------------------- | ------------------------------------------------------------ | ------------------------------ |
| proposal-generator        | `.github/skills/proposal-generator/`                         | `src/skills/manager.py` (auto) |
| compliance-auditor        | `.github/skills/compliance-auditor/`                         | `src/skills/manager.py` (auto) |
| competitive-intel         | `.github/skills/competitive-intel/`                          | `src/skills/manager.py` (auto) |
| price-to-win              | `.github/skills/price-to-win/`                               | `src/skills/manager.py` (auto) |
| oci-sweeper               | `.github/skills/oci-sweeper/`                                | `src/skills/manager.py` (auto) |
| subcontractor-sow-builder | `.github/skills/subcontractor-sow-builder/`                  | `src/skills/manager.py` (auto) |
| rfp-reverse-engineer      | `.github/skills/rfp-reverse-engineer/`                       | `src/skills/manager.py` (auto) |
| ot-prototype-strategist   | `.github/skills/ot-prototype-strategist/`                    | `src/skills/manager.py` (auto) |
| workload-analyzer         | `.github/skills/workload-analyzer/`                          | `src/skills/manager.py` (auto) |
| data-analyzer             | `.github/skills/data-analyzer/`                              | `src/skills/manager.py` (auto) |
| govcon-ontology           | `.github/skills/govcon-ontology/`                            | `src/skills/manager.py` (auto) |
| huashu-design             | `.github/skills/huashu-design/` (vendored — see UPSTREAM.md) | `src/skills/manager.py` (auto) |
| renderers                 | `.github/skills/renderers/`                                  | `src/skills/manager.py` (auto) |
| skill-creator             | `.github/skills/skill-creator/` (vendored — see UPSTREAM.md) | `src/skills/manager.py` (auto) |

## Index — Developer-only skills

Not shown in the Theseus UI (`metadata.developer_only: true`). Invokable from Copilot Chat only. Do not query the KG or govcon workspace.

| Skill                         | Source of truth                                                              | Notes                                                           |
| ----------------------------- | ---------------------------------------------------------------------------- | --------------------------------------------------------------- |
| improve-codebase-architecture | `.github/skills/improve-codebase-architecture/` (vendored — see UPSTREAM.md) | Uses `graphify-out/GRAPH_REPORT.md` as dependency map           |
| diagnose                      | `.github/skills/diagnose/` (vendored — see UPSTREAM.md)                      | Reproduce → minimise → hypothesise → fix → regression-test loop |
| tdd                           | `.github/skills/tdd/` (vendored — see UPSTREAM.md)                           | Red-green-refactor TDD loop                                     |
| grill-me                      | `.github/skills/grill-me/` (vendored — see UPSTREAM.md)                      | Generic plan stress-tester                                      |
| grill-with-docs               | `.github/skills/grill-with-docs/` (vendored — see UPSTREAM.md)               | Grills plan against CONTEXT.md + ADRs; updates docs inline      |
| prototype                     | `.github/skills/prototype/` (vendored — see UPSTREAM.md)                     | Terminal or UI throwaway prototype builder                      |
| to-prd                        | `.github/skills/to-prd/` (vendored — see UPSTREAM.md)                        | Converts conversation context to PRD; files to GitHub Issues    |
| to-issues                     | `.github/skills/to-issues/` (vendored — see UPSTREAM.md)                     | Breaks plan into vertical-slice GitHub issues                   |
| triage                        | `.github/skills/triage/` (vendored — see UPSTREAM.md)                        | Issue triage state machine (needs-triage → ready-for-agent)     |
| handoff                       | `.github/skills/handoff/` (vendored — see UPSTREAM.md)                       | Compacts conversation into a handoff doc for another agent      |
| write-a-skill                 | `.github/skills/write-a-skill/` (vendored — see UPSTREAM.md)                 | Author new skills with proper structure and evals               |
| setup-pre-commit              | `.github/skills/setup-pre-commit/` (vendored — see UPSTREAM.md)              | Husky pre-commit hooks with lint-staged + type-check + tests    |
| git-guardrails-claude-code    | `.github/skills/git-guardrails-claude-code/` (vendored — see UPSTREAM.md)    | Blocks destructive git ops before they execute                  |
| caveman                       | `.github/skills/caveman/` (vendored — see UPSTREAM.md)                       | Ultra-compressed communication mode (~75% token reduction)      |
| zoom-out                      | `.github/skills/zoom-out/` (vendored — see UPSTREAM.md)                      | Steps back to reframe a problem at the right level              |
| setup-matt-pocock-skills      | `.github/skills/setup-matt-pocock-skills/` (vendored — see UPSTREAM.md)      | Re-vendor or update the MP developer skill bundle               |

## Adding a Theseus-only Test Fixture

Place mock workspace context payloads under `theseus-skills/fixtures/<skill-name>/` for use by `tests/test_skills_*.py`. Do not place them under `.github/skills/` — Copilot would try to load them as references.

## Adding a Theseus-only Eval

Place eval scenarios under `theseus-skills/evals/<skill-name>/scenario-*.md`. The `SkillManager.run_evals()` helper walks this tree.
