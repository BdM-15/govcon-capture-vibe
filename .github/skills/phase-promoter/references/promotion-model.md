# Promotion Model

`phase-promoter` maps raw Ariadne captures onto the current repo layout.

## Tier Mapping

| Tier             | Intended repo location                          | Required frontmatter state                                             | Use when                                                                                 |
| ---------------- | ----------------------------------------------- | ---------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Source / inbox   | `global/inbox/<date>-<slug>.md`                 | `status: inbox`                                                        | Raw capture, brain dump, fleeting idea                                                   |
| Processed        | `global/notes/<date>-<slug>.md`                 | `status: processed`, `source: synth`, `derives_from: <source>`         | Clearer structure helps, but the note is still provisional                               |
| Evergreen        | `global/notes/<date>-<slug>.md`                 | `status: evergreen`, `source: synth`, `derives_from: <source>`         | Durable, reusable, cross-session knowledge                                               |
| LLM Wiki seed    | `global/llm-wiki/<topic>.md`                    | Usually `status: evergreen`, `source: synth`, `derives_from: <source>` | Topic-dense, cross-opportunity material that should become a single-source-of-truth page |
| Workspace source | `rag_storage/<workspace>/sources/<filename>.md` | Preserve the synthesized or source note exactly                        | The note should feed a specific workspace's LightRAG ingest path                         |

## Frontmatter Rules

- Preserve `workspace` when it still applies.
- Preserve or narrow `tags`; do not add speculative tags.
- Carry forward `wikilinks` when they still help retrieval.
- Add `derives_from: <relative-source-path>` on every synthesized note.
- Switch `source:` to `synth` for any note the skill rewrites or splits.

## Write Rule

`phase-promoter` now writes promoted notes directly into repo-local `global/` via `write_global_note`, and uses `promote_global_note` to copy selected notes into `rag_storage/<workspace>/sources/`. Use `write_file` only for scratch artifacts that should remain inside the run folder.

## Decision Heuristics

- Prefer `processed` over `evergreen` when the note depends on pending verification, a single customer conversation, or stale intel.
- Prefer `evergreen` over `llm-wiki` when the idea is durable but still narrow.
- Emit an `llm-wiki` seed only when a reader would plausibly want one dense page for the topic.
- Emit a `workspace_source` copy only when a concrete workspace is named or the user explicitly chooses one.
