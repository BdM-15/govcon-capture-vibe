# global/ — Ariadne's Thread evergreen layer

This is the **default working area** for Theseus. Most daily capture lands here, not in a workspace.

| Subdir      | Purpose                                                                   | Promotion target                                   |
| ----------- | ------------------------------------------------------------------------- | -------------------------------------------------- |
| `inbox/`    | Raw quick captures from `global-idea-capturer`                            | → `notes/` after triage, or → workspace `sources/` |
| `notes/`    | Triaged, developed personal notes (Obsidian-flavored MD)                  | → `llm-wiki/` via compaction chain                 |
| `llm-wiki/` | Karpathy-style synthesized wiki pages — one MD per topic, dense + current | Read-only-ish; updated by compaction chain         |
| `intel/`    | Cross-opportunity intel (vendor watch, agency notes, market signals)      | → workspace `intel/` when an opportunity goes deep |

All files are **Obsidian-flavored Markdown**: YAML frontmatter, `[[wikilinks]]`, `> [!note]` callouts. Open in Obsidian if desired — Theseus does not require it.

Starter corpus seeded in 174.9:

- `llm-wiki/shipley/` — capture-gate starter notes
- `llm-wiki/regulations/` — proposal-facing FAR quick sheets
- `llm-wiki/templates/` — reusable color-team templates
- `intel/patterns/` — cross-opportunity capture, intel, and proposal signals

See [docs/epics/174-ariadnes-thread.md](../docs/epics/174-ariadnes-thread.md) for design.
