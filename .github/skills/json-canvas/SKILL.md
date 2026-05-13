---
name: json-canvas
description: "Reference skill for the JSON Canvas open format — an infinite-canvas file format for node-based visual note layouts, used by Obsidian Canvas. Vendored from kepano/obsidian-skills for reference use by knowledge-vault. USE WHEN the user asks about JSON Canvas file format, creating visual node maps, or exporting vault note relationships as a canvas. DO NOT USE for production Theseus vault operations — use knowledge-vault instead."
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

# JSON Canvas — Reference

This skill is a **read-only reference** vendored from `kepano/obsidian-skills`. It documents the JSON Canvas open format for building visual note maps — useful when visualizing knowledge-vault note relationships.

## File format overview

A `.canvas` file:

```json
{
  "nodes": [
    {
      "id": "node1",
      "type": "text",
      "text": "Evaluation Factor: Past Performance",
      "x": 0, "y": 0, "width": 200, "height": 80,
      "color": "1"
    },
    {
      "id": "node2",
      "type": "file",
      "file": "vault/connected/PP-Scale-Evergreen.md",
      "x": 250, "y": 0, "width": 200, "height": 80
    }
  ],
  "edges": [
    {
      "id": "edge1",
      "fromNode": "node1", "fromSide": "right",
      "toNode": "node2", "toSide": "left",
      "label": "SUPPORTS"
    }
  ]
}
```

## Node types

| Type | Description |
|------|-------------|
| `text` | Inline Markdown text |
| `file` | Link to a vault file |
| `link` | External URL |
| `group` | Container for grouping nodes |

## Theseus mapping

Knowledge-vault evergreen notes and their KG relationships can be exported as a JSON Canvas to visualize the note → proposal section linkage map.

---

*Reference only. For Theseus vault operations, use the `knowledge-vault` skill.*
