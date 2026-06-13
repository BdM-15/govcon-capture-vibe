---
name: readiness-frame-tea-leaves
description: Tea-leaves micro-skill — importance signals and implicit criteria with alternate reads. Emits tea_leaves_handoff.json. Chain upstream of mission-readiness-framer.
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
    deliverables: [tea_leaves_handoff.json]
    frame_artifact: tea_leaves_handoff.json
    min_kg_chunks_passes: 1
  max_turns: 10
---

# Readiness Frame — Tea Leaves

Micro-skill for **importance signals** and **implicit criteria**.

## Workflow

1. Run surface `tea_leaves`.
2. Emit `artifacts/tea_leaves_handoff.json` with `importance_signals[]` and `implicit_criteria[]` (include `alternate_read` unless `confidence: high`).
3. Tag `source_role` correctly (program office vs CO).