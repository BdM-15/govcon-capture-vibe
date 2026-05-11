---
name: grill-me
description: >
  Interviews the user relentlessly about a plan or design until reaching shared
  understanding, resolving each branch of the decision tree one question at a time.
  Use when user wants to stress-test a plan, get grilled on their design, or
  mentions "grill me". Developer-only utility — does not query the Theseus KG.
  For govcon-specific capture, proposal, pricing, compliance, or intel work, use
  the corresponding domain skills instead.
license: Apache-2.0
metadata:
  version: 1.0.1
  category: developer-tool
  status: active
  runtime: legacy
  upstream: https://github.com/mattpocock/skills/tree/main/skills/productivity/grill-me
  personas_primary: none
  personas_secondary: []
  shipley_phases: []
  capability: meta
  developer_only: true
---

Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.

Ask the questions one at a time.

If a question can be answered by exploring the codebase, explore the codebase instead.
