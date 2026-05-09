# Global Inbox Frontmatter Contract

Every note in `global/inbox/` MUST have YAML frontmatter with these fields. The `GlobalStore` (174.3) and `phase-promoter` (174.5) parse this — drift breaks the chain.

## Required

| Field    | Type     | Values                                        | Notes                                                                                                                          |
| -------- | -------- | --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `date`   | ISO date | `YYYY-MM-DD`                                  | Capture date, not the date the underlying event happened.                                                                      |
| `source` | enum     | `capture`, `chat`, `import`, `synth`          | `capture` = quick-capture box; `chat` = mid-conversation; `import` = pasted from outside; `synth` = produced by another skill. |
| `status` | enum     | `inbox`, `processed`, `evergreen`, `archived` | New captures are always `inbox`. `phase-promoter` advances.                                                                    |
| `tags`   | list     | 2–4 lowercase kebab-case strings              | See SKILL.md "Tag vocabulary" section.                                                                                         |

## Optional

| Field          | Type   | Values                                          | When to use                                                                            |
| -------------- | ------ | ----------------------------------------------- | -------------------------------------------------------------------------------------- |
| `workspace`    | string | Active workspace name (e.g., `afcap6_drfp_171`) | When the capture relates to a specific opportunity. Enables `phase-promoter` to route. |
| `wikilinks`    | string | `[[name1]] [[name2]]` space-separated           | Mirrors the body's wikilinks for the index to find without parsing prose.              |
| `priority`     | enum   | `low`, `med`, `high`                            | ONLY when the user explicitly stated urgency. Don't infer.                             |
| `derives_from` | string | Path to source note (relative to `global/`)     | Used by `phase-promoter` synthesis output, not by raw captures.                        |

## Anti-patterns

- No `title:` field — the slug in the filename IS the title.
- No `author:` field — single-user repo.
- No `version:` field — git history is the version log.
- No nested frontmatter (no `meta: { ... }`). Flat keys only.
- No `[[wikilinks]]` inside YAML strings outside the dedicated `wikilinks:` field — Obsidian renders them in the body, not the frontmatter.

## Example

```yaml
---
date: 2026-05-08
source: capture
status: inbox
workspace: afcap6_drfp_171
tags: [afcap6, pricing, competitive-intel]
wikilinks: [[competitive-intel]] [[price-to-win]]
---
```
