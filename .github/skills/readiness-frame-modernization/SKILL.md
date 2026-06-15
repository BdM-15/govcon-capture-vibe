---
name: readiness-frame-modernization
description: Modernization and innovation inquiry micro-skill — current methods, systems, tooling, and quality/cost improvement openings. Emits modernization_handoff.json. Chain upstream of mission-readiness-framer.
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
    deliverables: [modernization_handoff.json]
    frame_artifact: modernization_handoff.json
    min_kg_chunks_passes: 2
  max_turns: 12
  depth_extension_turns: 0
---

# Readiness Frame — Modernization / Innovation

Micro-skill for **current methods** and **innovation opportunities**.

## Workflow

1. Run surfaces `methods_modernization` and `innovation_inquiry` in order.
2. Emit `artifacts/modernization_handoff.json` with `current_methods[]` and `innovation_opportunities[]` (honest `fit_to_scope`).
3. Cite PWS/QASP/attachment chunks; no vendor invention without web evidence.