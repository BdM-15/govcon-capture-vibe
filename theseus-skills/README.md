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

| Skill                 | Source of truth                                                  | Theseus runtime adapter                                                                   |
| --------------------- | ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| huashu-design         | `.github/skills/huashu-design/` (vendored — see UPSTREAM.md)     | `src/skills/manager.py` (auto)                                                            |
| govcon-ontology       | `.github/skills/govcon-ontology/`                                | `src/skills/manager.py` (auto)                                                            |
| proposal-generator    | `.github/skills/proposal-generator/`                             | `src/skills/manager.py` (auto)                                                            |
| compliance-auditor    | `.github/skills/compliance-auditor/`                             | `src/skills/manager.py` (auto)                                                            |
| competitive-intel     | `.github/skills/competitive-intel/`                              | `src/skills/manager.py` (auto)                                                            |
| grill-me-govcon       | `.github/skills/grill-me-govcon/`                                | `src/skills/manager.py` (auto)                                                            |
| grill-me-bid-strategy | `.github/skills/grill-me-bid-strategy/`                          | `src/skills/manager.py` (auto)                                                            |
| grill-me-capture      | `.github/skills/grill-me-capture/`                               | `src/skills/manager.py` (auto)                                                            |
| grill-me-proposal     | `.github/skills/grill-me-proposal/`                              | `src/skills/manager.py` (auto)                                                            |
| grill-me-ptw          | `.github/skills/grill-me-ptw/`                                   | `src/skills/manager.py` (auto)                                                            |
| global-idea-capturer  | `.github/skills/global-idea-capturer/`                           | Global-first capture to `global/inbox/`; workspace promotion deferred to `phase-promoter` |
| obsidian-markdown     | `.github/skills/obsidian-markdown/` (vendored — see UPSTREAM.md) | Dual-purpose — powers MD authoring in workspace evergreen layer + dev note-taking         |
| idea-capturer         | `.github/skills/idea-capturer/` (vendored — see UPSTREAM.md)     | Dual-purpose — capture/brainstorm for both govcon ideation and dev research               |

## Index — Developer-only skills

Not shown in the Theseus UI (`metadata.developer_only: true`). Invokable from Copilot Chat only. Do not query the KG or govcon workspace.

| Skill                         | Source of truth                                                              | Notes                                                                                                                                            |
| ----------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| improve-codebase-architecture | `.github/skills/improve-codebase-architecture/` (vendored — see UPSTREAM.md) | Uses `graphify-out/GRAPH_REPORT.md` as dependency map                                                                                            |
| caveman                       | `.github/skills/caveman/` (vendored — see UPSTREAM.md)                       | Ultra-compressed communication mode; no KG access                                                                                                |
| grill-me                      | `.github/skills/grill-me/` (vendored — see UPSTREAM.md)                      | Generic plan stress-tester; govcon variants in platform tier above                                                                               |
| to-prd                        | `.github/skills/to-prd/` (vendored — see UPSTREAM.md)                        | Converts conversation context to PRD; files to GitHub Issues                                                                                     |
| to-issues                     | `.github/skills/to-issues/` (vendored — see UPSTREAM.md)                     | Breaks plan into vertical-slice GitHub issues                                                                                                    |
| tdd                           | `.github/skills/tdd/` (vendored — see UPSTREAM.md)                           | Red-green-refactor TDD loop with 5 reference files                                                                                               |
| obsidian-markdown             | `.github/skills/obsidian-markdown/` (vendored — see UPSTREAM.md)             | Also a platform skill (see above). Listed here because devs invoke it for repo notes / docs authoring too.                                       |
| idea-capturer                 | `.github/skills/idea-capturer/` (vendored — see UPSTREAM.md)                 | Also a platform skill (see above). Listed here because devs use it for non-govcon ideation; basis for `global-idea-capturer` derivative (174.2). |

## Adding a Theseus-only Test Fixture

Place mock workspace context payloads under `theseus-skills/fixtures/<skill-name>/` for use by `tests/test_skills_*.py`. Do not place them under `.github/skills/` — Copilot would try to load them as references.

## Adding a Theseus-only Eval

Place eval scenarios under `theseus-skills/evals/<skill-name>/scenario-*.md`. The `SkillManager.run_evals()` helper walks this tree.
