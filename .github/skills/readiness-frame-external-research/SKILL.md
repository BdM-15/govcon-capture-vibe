---
name: readiness-frame-external-research
description: Conditional external-research micro-skill when the user names vendors, platforms, or URLs. Runs mandatory independent web_search plus seed URL fetch; emits capability_overlay_handoff.json. Chain upstream of mission-readiness-framer when overlay intent is detected.
license: MIT
metadata:
  personas_primary: capture_manager
  personas_secondary: [proposal_manager]
  shipley_phases: [capture, strategy]
  capability: research
  skill_role: slice
  skill_family: readiness-frame
  skill_family_label: Mission Readiness Frame
  runtime: tools
  category: capture_intelligence
  version: 1.0.0
  status: active
  research_harness:
    deliverables: [capability_overlay_handoff.json]
    frame_artifact: capability_overlay_handoff.json
    min_kg_chunks_passes: 0
    min_scratchpad_chars: 500
  max_turns: 10
---

# Readiness Frame — External Research (conditional)

Run **only** when the user prompt implies capability overlay (vendor, platform, URL, or "can we use").

## Workflow

1. User URLs are **seeds** — always run independent `web_search` for vendor + product; do not limit research to provided links.
2. Use `web_fetch` / `web_research` on seed URLs when present.
3. Emit `artifacts/capability_overlay_handoff.json` with `capability_overlay` (vendor, sources, platform_capabilities, pain_point_mappings, innovation_links).
4. Cite web sources; map to solicitation scope honestly in `fit_to_scope`.