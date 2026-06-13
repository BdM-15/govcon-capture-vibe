---
name: readiness-frame-workload
description: Retrieves package-mechanics evidence — background, PWS/SOW, QASP, transition — and emits workload_handoff.json with readiness enablers and workload clusters. Chain upstream of mission-readiness-framer.
license: MIT
metadata:
  personas_primary: capture_manager
  personas_secondary: [proposal_manager, program_manager]
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
    deliverables: [workload_handoff.json]
    frame_artifact: workload_handoff.json
    min_kg_chunks_passes: 4
  max_turns: 16
---

# Readiness Frame — Workload / Package Mechanics

Micro-skill for **PWS/SOW, background, QASP, transition** surfaces.

## Workflow

1. Execute the injected retrieval plan (package-mechanics surfaces only).
2. Emit `artifacts/workload_handoff.json` with `workload_enablers[]`, `readiness_outcome`, `failure_modes_feared[]`, and cited scope clusters.
3. Defer thin surfaces honestly in `claim_gaps[]`.