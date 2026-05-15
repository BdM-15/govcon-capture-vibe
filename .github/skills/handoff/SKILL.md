---
name: handoff
description: Compact the current conversation into a handoff document for another agent to pick up.
metadata:
  personas_primary: none
  personas_secondary: []
  shipley_phases: []
  capability: meta
  category: continuity
  version: 1.0.0
  status: active
  runtime: legacy
  argument-hint: "What will the next session be used for?"
  upstream: https://github.com/mattpocock/agent-skills
---

Write a handoff document summarising the current conversation so a fresh agent can continue the work. Save it to a path produced by `mktemp -t handoff-XXXXXX.md` (read the file before you write to it).

Suggest the skills to be used, if any, by the next session.

Do not duplicate content already captured in other artifacts (PRDs, plans, ADRs, issues, commits, diffs). Reference them by path or URL instead.

If the user passed arguments, treat them as a description of what the next session will focus on and tailor the doc accordingly.
