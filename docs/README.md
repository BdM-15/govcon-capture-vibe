# GovCon-Capture-Vibe Documentation

Living documentation index for Project Theseus.

## Quick Start

- Repo overview and setup: [../README.md](../README.md)
- Agent rules and architecture philosophy: [../.github/copilot-instructions.md](../.github/copilot-instructions.md)
- UI work: [STYLE_GUIDE.md](STYLE_GUIDE.md)
- Skills platform overview: [SKILLS.md](SKILLS.md)
- Skill authoring and audit rules: [SKILL_SPEC_COMPLIANCE.md](SKILL_SPEC_COMPLIANCE.md)
- Skill taxonomy and closed vocabularies: [SKILL_TAXONOMY.md](SKILL_TAXONOMY.md)

## Current docs

| Document                                                                 | Description                                                 |
| ------------------------------------------------------------------------ | ----------------------------------------------------------- |
| [README.md](../README.md)                                                | Repo overview, setup, backlog, and current runtime guidance |
| [STYLE_GUIDE.md](STYLE_GUIDE.md)                                         | Capture Workbench UI constraints and token system           |
| [SKILLS.md](SKILLS.md)                                                   | Dual-use skills platform, authoring contract, install flow  |
| [SKILL_SPEC_COMPLIANCE.md](SKILL_SPEC_COMPLIANCE.md)                     | Open Agent Skills compliance audit and migration notes      |
| [SKILL_TAXONOMY.md](SKILL_TAXONOMY.md)                                   | Persona, Shipley phase, and capability vocabularies         |
| [../.github/copilot-instructions.md](../.github/copilot-instructions.md) | Repo-specific coding rules and cross-cutting checklists     |

## Notes

- Historical architecture and white-paper docs were removed during repo cleanup. Use git history if you need archived context.
- Current system facts live in [../README.md](../README.md) and [../.github/copilot-instructions.md](../.github/copilot-instructions.md), not in deleted design memos.
- Pydantic v3 migration is a future item blocked by upstream dependency constraints (`<3` in key packages); see [../README.md](../README.md) section "Known Dependency Constraint (Pydantic v3)".
