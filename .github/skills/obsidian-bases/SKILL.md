---
name: obsidian-bases
description: "Reference skill for Obsidian Bases — a structured data layer inside Obsidian vaults that enables database-style views over Markdown notes. Vendored from kepano/obsidian-skills for reference use by knowledge-vault. USE WHEN the user asks about Obsidian Bases syntax, table views, filter expressions, or structured queries over vault notes. DO NOT USE for production Theseus vault operations — use knowledge-vault instead."
license: MIT
metadata:
  personas_primary: none
  personas_secondary: []
  shipley_phases: []
  capability: meta
  runtime: legacy
  category: reference
  version: 1.0.0
  status: reference
  upstream: https://github.com/kepano/obsidian-skills
  note: Vendored as read-only reference. Not executed in production.
---

# Obsidian Bases — Reference

This skill is a **read-only reference** vendored from `kepano/obsidian-skills`. It documents Obsidian Bases conventions useful for building database-style views over vault notes — analogous to the Theseus intel-feed swimlane grouping.

## Base file format

A `.base` file defines structured views:

```yaml
schema:
  fields:
    - name: status
      type: text
    - name: updated_at
      type: date
views:
  - type: table
    name: All Notes
    filter: "status != ''"
  - type: board
    name: Swimlanes
    groupBy: status
```

## Filtering

```
status = "polished"
updated_at > "2026-01-01"
tags includes "rfp"
```

## Theseus mapping

| Obsidian Bases concept | Theseus vault equivalent |
|------------------------|--------------------------|
| `status` field | `VaultNote.status` (raw/polished/evergreen) |
| Board view | Intel Feed swimlane kanban |
| Table view | Notes list pane |
| Filter | `GET /api/ui/vault/notes?status=raw` |

---

*Reference only. For Theseus vault operations, use the `knowledge-vault` skill.*
