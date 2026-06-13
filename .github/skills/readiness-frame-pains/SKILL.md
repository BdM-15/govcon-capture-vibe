---
name: readiness-frame-pains
description: Shipley capture micro-skill — customer pain points (explicit, latent, structural) from the solicitation package. Emits pains_handoff.json. Chain upstream of mission-readiness-framer.
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
    deliverables: [pains_handoff.json]
    frame_artifact: pains_handoff.json
    min_kg_chunks_passes: 1
  max_turns: 10
---

# Readiness Frame — Customer Pains

Micro-skill for **Shipley customer pain** extraction.

## Workflow

1. Run retrieval plan surface `shipley_pains`.
2. Emit `artifacts/pains_handoff.json` with `customer_pain_points[]` — each with `visibility`, `challenge_type`, `rationale`, `readiness_link`, `source_chunk_ids[]` (platform enriches `source_citations[]` with document/section/quote for briefs).
3. Cover every **material** pain the package supports; defer gaps in `claim_gaps[]`.