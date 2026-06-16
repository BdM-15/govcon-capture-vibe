# Project Theseus (govcon-capture-vibe) — Grok agent rules

Full agent rules: [.github/copilot-instructions.md](.github/copilot-instructions.md)

## Skill work (mandatory)

Before creating or materially changing any skill under `.github/skills/`:

1. Load **skill-creator** — [.grok/skills/skill-creator/SKILL.md](.grok/skills/skill-creator/SKILL.md) → canonical [.github/skills/skill-creator/SKILL.md](.github/skills/skill-creator/SKILL.md)
2. Follow the skill-creator eval loop (`evals/evals.json`, observed run, iterate)
3. Affirm in commit message that skill-creator was loaded this turn

No direct SKILL.md edits that skip the eval loop.

## Mission readiness micro-skills

Build and validate each readiness-frame skill **independently** before chaining:

`workload` → `eval` → `pains` → `modernization` → `tea-leaves` → `win-themes` → `compile`

LangGraph orchestration is wiring only — content quality is proven at the skill level.

## Tests

Run from project `.venv`: `.venv\Scripts\python.exe -m pytest ...`