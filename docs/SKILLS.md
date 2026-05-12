# Project Theseus — Agent Skills Platform

This document describes the **dual-use Agent Skills platform** introduced in branch `118-agent-skills-platform`. The same skill files are read by:

1. **VS Code / GitHub Copilot** — when this repo is opened in an Agent-Skills-aware client (the spec at <https://agentskills.io>), the agent discovers `SKILL.md` files under `.github/skills/` and uses them as additional capability modules.
2. **The Theseus runtime** — the in-app **Tools → Agent Skills** page lists, installs, and invokes the same skills against the active workspace's knowledge graph.

There is one source of truth: `.github/skills/<name>/SKILL.md`. Edit it once, both surfaces pick it up.

---

## Why dual-use?

A capture team using Theseus already pays the cost of standing up an ontology-aware RAG. The same authored knowledge (Shipley methodology, FAR/DFARS shorthand, design tokens, compliance-audit checklists) is exactly what makes a Copilot/VS Code agent useful when an engineer is editing prompts, ontologies, or proposal drafts in their IDE.

By writing skills to the agentskills.io standard, we get:

- One place to author capability — no parallel "Theseus prompts" vs "Copilot prompts" drift
- Discoverability for outside contributors (Copilot users see them as soon as they clone)
- A clean install path (`git clone --depth=1` into `.github/skills/`)
- Future portability to any other agent runtime that honors the standard

---

## Skill anatomy

```
.github/skills/<slug>/
├── SKILL.md              # YAML frontmatter + instructions (required)
├── references/           # On-demand reference material (loaded via "see references/X.md")
├── assets/               # Output skeletons or bundled artifacts (Markdown, HTML, JSON, fonts)
├── scripts/              # Optional executables (Python, Node, shell)
└── evals/                # Optional eval scenarios (theseus-skills/evals/ preferred)
```

**Frontmatter contract:**

```yaml
---
name: my-skill # slug, must match folder name
description: One sentence trigger # used by Copilot for skill selection
license: MIT
compatibility: {} # optional
metadata:
  category: design|ontology|proposal|compliance|intel|other
  version: 0.1.0
  status: stable|experimental
  upstream: org/repo
---
```

The body is Markdown — write **imperative instructions** (the agent's playbook), not descriptive prose. Reference any deeper material via `see references/<name>.md` so the agent loads it on demand (progressive disclosure).

---

## Current skills (selected)

| Slug                                                                                      | Category   | What it does                                                                                                                          |
| ----------------------------------------------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| [huashu-design](../.github/skills/huashu-design/SKILL.md)                                 | design     | Vendored upstream HTML→PPTX/PDF/MP4 design engine (Personal Use License). Drive with `proposal-generator` content for govcon visuals. |
| [govcon-ontology](../.github/skills/govcon-ontology/SKILL.md)                             | ontology   | Authoritative reference for the 33 entity / 35 relationship schema                                                                    |
| [proposal-generator](../.github/skills/proposal-generator/SKILL.md)                       | proposal   | Shipley capture mentor: compliance spine → win themes → FAB → outlines + govcon HTML render templates                                 |
| [compliance-auditor](../.github/skills/compliance-auditor/SKILL.md)                       | compliance | 8-check audit (clause coverage, regulatory resolution, L↔M, cyber, …)                                                                 |
| [competitive-intel](../.github/skills/competitive-intel/SKILL.md)                         | intel      | Live incumbent, award-history, and competitor research via USAspending                                                                |
| [improve-codebase-architecture](../.github/skills/improve-codebase-architecture/SKILL.md) | developer  | Developer-only deepening skill: find shallow modules, increase leverage/locality                                                      |
| [grill-me](../.github/skills/grill-me/SKILL.md)                                           | developer  | Developer-only stress-test skill for plans and designs                                                                                |
| [tdd](../.github/skills/tdd/SKILL.md)                                                     | developer  | Developer-only red-green-refactor loop focused on deep, simple modules                                                                |

Redundant `grill-me-*` variants were removed during repo cleanup. Use
`grill-me` for generic developer stress-testing and keep govcon work routed
through purpose-built domain skills.

---

## Theseus runtime integration

### Discovery

`SkillManager.discover()` walks `.github/skills/` at server start and on demand (`POST /api/ui/skills/refresh`). Each `SKILL.md` is parsed for its YAML frontmatter and body Markdown. Results are kept in memory.

### Workspace context injection

When a skill is invoked from the UI, the runtime:

1. Reads the active workspace's `kv_store_full_entities.json`
2. Buckets entities by `entity_type`, optionally filtered to a recommended slice
3. Embeds the slice into the LLM prompt above the user's free-text instruction
4. Sends the full composed prompt to `llm_func` (currently the same `llm_model_func` LightRAG uses)
5. Returns the raw model response plus `entities_used`, `elapsed_ms`, and any warnings

Skills should specify their preferred entity slice in their SKILL.md "Workspace Context Injection" section so the UI / API can pre-select sensible defaults.

### API surface

| Method   | Path                           | Purpose                                                                        |
| -------- | ------------------------------ | ------------------------------------------------------------------------------ |
| `GET`    | `/api/ui/skills`               | List discovered skills                                                         |
| `POST`   | `/api/ui/skills/refresh`       | Re-walk the directory                                                          |
| `GET`    | `/api/ui/skills/{name}`        | Full SKILL.md body + supporting-file inventory                                 |
| `POST`   | `/api/ui/skills/install`       | `{url, name?}` — clone a GitHub repo into `.github/skills/`                    |
| `DELETE` | `/api/ui/skills/{name}`        | Remove an installed (non-builtin) skill                                        |
| `POST`   | `/api/ui/skills/{name}/invoke` | `{prompt, entity_types?, max_entities_per_type?}` — run with workspace context |

### Install ledger

`var/platform/skills.json` records `source` (`builtin` vs `installed`), `source_url`, `installed_at`, `last_invoked_at`. It's a single workspace-independent file because skills are global to a Theseus instance, not per-RFP.

---

## Authoring a new skill

1. **Pick a slug**: short, kebab-case, no spaces. Match the folder name to the frontmatter `name`.
2. **Create the folder**: `.github/skills/<slug>/`
3. **Write `SKILL.md`**:
   - Frontmatter with `name`, `description` (one tight sentence — Copilot uses this to decide when to invoke), `license`, optional `compatibility`, and `metadata` for repo-specific fields like `category`, `version`, `status`, and `upstream`
   - Body in **imperative voice**, ~100-200 lines max
   - Section: "When to use" / "When NOT to use"
   - Section: "Workflow" — numbered steps the agent should follow
   - Section: "Output Contract" — exact JSON envelope or Markdown structure
   - Section: "Workspace Context Injection" — what entity types to pull
4. **Add references on demand**: anything longer than ~30 lines goes in `references/<topic>.md` and is referenced via `see references/<topic>.md`. This is the **progressive disclosure** pattern from the agentskills.io spec.
5. **Add assets** if your skill produces structured output: `assets/<artifact>.md` or `.html`.
6. **Add scripts only if necessary**: prefer LLM-only skills. Scripts must be self-contained and read inputs from `build/context.json` if they need data.
7. **Validate**:
   - Open the repo in VS Code and ask Copilot a question that should trigger the skill — verify the skill description is specific enough
   - Visit Theseus → Tools → Agent Skills, click "Refresh", click your skill, and run it against a workspace
8. **Cross-cutting alignment** (if the skill references entities or relationships): follow the [Cross-Cutting Change Checklist](../.github/copilot-instructions.md) in the project copilot instructions.

---

## Installing a third-party skill

From the Theseus UI:

1. Navigate to **Tools → Agent Skills**
2. Click **Install from GitHub**
3. Paste the repo URL (must be `https://github.com/...`)
4. The repo must contain a `SKILL.md` at its root
5. Skill appears in the grid and is also picked up by Copilot/VS Code on the next reload

CLI equivalent:

```bash
git clone --depth=1 https://github.com/<org>/<repo>.git .github/skills/<slug>
rm -rf .github/skills/<slug>/.git
```

---

## Security considerations

- **Install URLs are restricted to `https://github.com/`** — no other hosts, no `git://`, no archives. This limits SSRF / supply-chain blast radius.
- **Cloned skills are shallow** (`--depth=1`) and the `.git` directory is removed after install.
- **The skill name is validated** against `^[a-z0-9][a-z0-9_-]{0,63}$` to prevent path traversal.
- **Skills cannot directly mutate the Neo4j RFP graph** — invocation only reads the entity store and dispatches to the LLM. Any output that should go back into the graph must flow through the normal `/insert` pipeline.
- **The install ledger lives in `var/platform/`** — outside the LightRAG workspace tree, so workspace deletion does not silently uninstall skills.

---

## Roadmap

- Per-skill eval harness reading from `theseus-skills/evals/<slug>/scenario-*.md`
- Skill marketplace browser pulling from a curated index repo
- Integration with `competitive-intel` external data sources (SAM.gov, USAspending)
- Auto-mirror of `theseus-skills/` to a junction on Windows (currently `theseus-skills/README.md` only)
