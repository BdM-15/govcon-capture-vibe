---
name: obsidian-cli
description: "Reference skill for obsidian-cli — a command-line tool for creating, searching, and managing Obsidian vaults from the terminal. Vendored from kepano/obsidian-skills for reference use by knowledge-vault. USE WHEN the user asks about batch-importing notes into Obsidian, exporting vault content, or running CLI operations on a local Obsidian vault. DO NOT USE for production Theseus vault operations — use knowledge-vault instead."
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

# Obsidian CLI — Reference

This skill is a **read-only reference** vendored from `kepano/obsidian-skills`. It documents obsidian-cli usage patterns useful for vault import/export workflows.

## Common commands

```bash
# Create a note
obsidian new "Note Title" --vault ~/vault

# Search notes
obsidian search "evaluation factor" --vault ~/vault

# Open a note
obsidian open "Note Title" --vault ~/vault

# List notes by tag
obsidian list --tag rfp --vault ~/vault
```

## Batch import from Theseus vault

To export evergreen notes from Theseus into Obsidian format:

```bash
# 1. Export via Theseus API
curl http://localhost:9621/api/ui/vault/notes?status=evergreen > notes.json

# 2. Convert to Markdown files (custom script)
python tools/export_vault_to_obsidian.py notes.json --out ~/vault/theseus/

# 3. Open vault
obsidian open --vault ~/vault
```

---

*Reference only. For Theseus vault operations, use the `knowledge-vault` skill.*
