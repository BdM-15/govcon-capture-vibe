---
name: obsidian-markdown
description: "Reference skill for Obsidian-flavored Markdown conventions: wikilinks, callouts, frontmatter tags, embeds, and folder structure patterns. Vendored from kepano/obsidian-skills for reference use by knowledge-vault. USE WHEN the user asks about Obsidian wikilink syntax, how to structure Markdown notes for vault import, or how to format callouts and embeds. DO NOT USE for production Theseus vault operations — use knowledge-vault instead."
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
  note: Vendored as read-only reference for knowledge-vault polish workflow. Not executed in production.
---

# Obsidian Markdown — Reference

This skill is a **read-only reference** vendored from `kepano/obsidian-skills`. It provides Obsidian Markdown conventions used by the `knowledge-vault` skill when structuring polished notes for potential Obsidian-compatible export.

## Wikilinks

Internal links use double-bracket syntax:

```markdown
[[Note Title]]
[[Note Title|Display Text]]
[[Folder/Note Title#Heading]]
```

## Frontmatter

YAML frontmatter at the top of a note:

```markdown
---
tags: [govcon, rfp, technical-approach]
status: polished
aliases: [TA Section]
---
```

## Callouts

```markdown
> [!NOTE] Title
> Content here

> [!WARNING]
> Important caution

> [!TIP] Shipley Hot Button
> This is a customer priority — see evaluation factor 3.2
```

## Embeds

```markdown
![[Note Title]]         — embed full note
![[Note Title#Section]] — embed section only
```

## Folder conventions

```
vault/
├── fleeting/     — raw notes (status: raw)
├── developing/   — polished notes (status: polished)
└── connected/    — evergreen notes (status: evergreen)
```

---

*Reference only. For Theseus vault operations, use the `knowledge-vault` skill.*
