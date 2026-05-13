---
name: idea-capturer
description: "Reference skill for rapid idea capture using a structured fleeting-note template — adapted from eddiebe147/claude-settings idea-capturer pattern. USE WHEN the user wants a template for capturing raw govcon intelligence observations quickly during RFP analysis, site visits, or capture conversations. Produces a structured fleeting note ready for the knowledge-vault polish workflow. DO NOT USE for the full knowledge-vault lifecycle — use knowledge-vault instead."
license: MIT
metadata:
  personas_primary: capture_manager
  personas_secondary: [proposal_manager]
  shipley_phases: [capture]
  capability: draft
  runtime: legacy
  category: knowledge
  version: 1.0.0
  status: reference
  upstream: https://github.com/eddiebe147/claude-settings
  note: Vendored as read-only reference for knowledge-vault fleeting-note intake pattern.
---

# Idea Capturer — Reference

This skill is a **read-only reference** adapted from `eddiebe147/claude-settings` idea-capturer pattern. It provides a structured fleeting-note template for rapid govcon intelligence capture.

## When to Use

- You heard something important on a customer call and need to capture it now
- You noticed a pattern across multiple RFP sections while reading
- A colleague shared competitive intelligence you want to preserve
- You had an insight about a win theme while away from your desk

## Fleeting Note Template

```markdown
---
status: raw
captured_at: {{date}}
source: {{source}}  # e.g., "Section L.7", "customer call 2026-05-13", "colleague note"
topic: {{topic}}    # e.g., "evaluation criteria", "technical requirements", "past performance"
---

## Raw Capture

{{paste your raw observation here — no editing needed}}

## Initial Signal

<!-- Optional: flag what type this might be -->
- [ ] Requirement (shall language)
- [ ] Customer priority / hot button
- [ ] Evaluation factor signal
- [ ] Competitive intelligence
- [ ] Win theme candidate
- [ ] Other: ___________
```

## Quick Capture Rules

1. **Speed > polish.** Capture now, polish later via `knowledge-vault`.
2. **Quote verbatim when possible.** Exact language enables precise entity proposals.
3. **Note the source.** Even "Section L, somewhere around page 12" is better than nothing.
4. **One observation per note.** Don't combine unrelated observations.

## After Capture

Pass the completed template to `knowledge-vault` with:
> "Polish this fleeting note and identify entity proposals."

The `knowledge-vault` skill will handle the rest: rewrite for clarity, apply Shipley vocabulary, propose entity types, and recommend KG cross-links.

---

*Reference only. Full lifecycle management via `knowledge-vault`.*
