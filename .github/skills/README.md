# Project Theseus — Agent Skills

This directory contains [Agent Skills](https://agentskills.io) packaged for **dual-use**:

1. **VS Code / GitHub Copilot** — auto-discovered by tools that scan `.github/skills/` (the official location).
2. **Theseus Capture Workbench** — surfaced in the web UI under **Tools → Skills** and invokable against the active workspace's RFP knowledge graph.

Each skill is a self-contained folder with a `SKILL.md` file (YAML frontmatter + imperative instructions) plus optional `scripts/`, `references/`, `assets/`, and `evals/` subdirectories.

## Representative Skills

See the directory listing for the full live inventory. This table highlights the main skill families.

| Skill                                             | Category   | Purpose                                                                                                                                                                 |
| ------------------------------------------------- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`huashu-design`](./huashu-design/)               | design     | Vendored verbatim from [alchaincyf/huashu-design](https://github.com/alchaincyf/huashu-design) under Personal Use License. High-fidelity HTML prototypes → PPTX / PDF / MP4 / GIF, animation engine, 24 prebuilt showcases, 20-philosophy design vocabulary. Format-agnostic — for govcon visuals, drive it with content drafted by `proposal-generator`. |
| [`govcon-ontology`](./govcon-ontology/)           | ontology   | Portable, agent-readable spec of the 33-entity / 35-relationship Theseus ontology with extraction rules, validation logic, common pitfalls, and how-to-extend workflow. |
| [`proposal-generator`](./proposal-generator/)     | proposal   | Shipley-methodology proposal outline generator with win themes, FAB chains, traceability matrices, compliance citations, govcon design tokens, and HTML render templates suitable for `huashu-design` to convert to PPTX/PDF. |
| [`compliance-auditor`](./compliance-auditor/)     | compliance | FAR/DFARS clause linker and regulatory-reference validator across the active workspace.                                                                                 |
| [`competitive-intel`](./competitive-intel/)       | intel      | Roadmap placeholder — basic structure for future incumbent / market analysis.                                                                                           |

## How Skills Are Discovered

### Copilot / VS Code

The Copilot extension (and other agentskills-compatible tools) scan `.github/skills/*/SKILL.md` at project open. The YAML frontmatter `description` field is the trigger — when the user's intent overlaps the description, the agent loads the skill before acting.

### Theseus Web UI

The `SkillManager` at [`src/skills/manager.py`](../../src/skills/manager.py) discovers the same files at startup (and after install events). The list is exposed at `GET /api/ui/skills`, rendered in the **Skills** page, and invoked via `POST /api/ui/skills/{name}/invoke` — which injects relevant entities from the active workspace KG into the LLM call alongside the skill's instructions.

## Authoring Conventions

Skills in this repo follow the `skill-creator` best-practices:

- **Frontmatter `description` is pushy and precise** — names concrete triggers (e.g., "USE WHEN…"; "DO NOT USE FOR…") so the dispatcher can route confidently.
- **Progressive disclosure** — `SKILL.md` stays under ~500 lines; deep references live in `references/*.md` and are loaded only when needed.
- **Imperative voice** — "Extract the CLINs", not "You may want to extract the CLINs".
- **Why, not just what** — every non-obvious step explains the GovCon rationale (the proposal_instruction ↔ evaluation_factor golden thread — UCF Section L↔M or non-UCF equivalent — Shipley discriminator framing, etc.).
- **Output assets** — every skill that produces an artifact ships an asset under `assets/`.
- **Examples** — at least one worked example per skill (typically under `references/examples.md`).

## Adding a New Skill

1. Copy `competitive-intel/` as a starter (smallest, most generic shape).
2. Edit `SKILL.md` frontmatter (`name`, `description`, `category`, `version`).
3. Place imperative instructions in `SKILL.md` (target ≤500 lines).
4. Offload reference material to `references/`, scripts to `scripts/`, output assets to `assets/`.
5. Restart the Theseus server — the skill auto-registers. Copilot picks it up on next workspace re-index.

See [docs/SKILLS.md](../../docs/SKILLS.md) for end-to-end usage in both contexts.
