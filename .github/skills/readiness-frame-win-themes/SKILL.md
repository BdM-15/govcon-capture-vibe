---
name: readiness-frame-win-themes
description: Shipley win-theme seed micro-skill — needs/wants, priorities, and win-theme candidates with rationale chains. Emits win_themes_handoff.json. Chain upstream of mission-readiness-framer.
license: MIT
metadata:
  personas_primary: capture_manager
  personas_secondary: [proposal_manager]
  shipley_phases: [capture, strategy]
  capability: analyze
  skill_role: slice
  skill_family: readiness-frame
  skill_family_label: Mission Readiness Frame
  runtime: tools
  category: capture_intelligence
  version: 1.0.0
  status: active
  research_harness:
    plan_surfaces_path: references/plan_surfaces.json
    deliverables: [win_themes_handoff.json]
    frame_artifact: win_themes_handoff.json
    min_kg_chunks_passes: 2
  max_turns: 12
---

# Readiness Frame — Win Themes

Micro-skill for **customer needs/wants** and **win-theme candidate seeds**.

## Workflow

1. Run surfaces `shipley_needs_wants` then `shipley_win_themes`.
2. Emit `artifacts/win_themes_handoff.json` with priority-ranked `win_theme_candidates[]` (full `rationale_chain`, `proof_required[]`, `evaluation_factor_links[]`).
3. Seeds only — no proposal prose.