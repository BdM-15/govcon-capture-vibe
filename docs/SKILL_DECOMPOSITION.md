# Mission Readiness Framer — Skill Decomposition

## Problem

Monolithic `mission-readiness-framer` (40 turns, 12 retrieval surfaces) produced shallow, chat-like outputs because skills kept only entity names + chunk IDs from `aquery_data`, then rebuilt thin briefing books under low `SKILL_MAX_*` caps.

## Architecture

```
Platform retrieval plumbing (Phase 0)
  ├── full aquery_data passthrough (researcher_retrieval.py)
  ├── bootstrap seed → research_scratchpad.md
  ├── generic research_harness (plan_surfaces from skill metadata)
  ├── evidence gates + independent auditor
  └── Settings UI query recommendations

readiness-frame-* micro-skills (Phase 1)
  ├── readiness-frame-eval
  ├── readiness-frame-workload
  ├── readiness-frame-pains
  ├── readiness-frame-modernization
  ├── readiness-frame-tea-leaves
  ├── readiness-frame-win-themes
  └── readiness-frame-external-research (conditional)

mission-readiness-framer (Phase 2)
  └── chain orchestrator / compiler → mission_readiness_frame.json + brief.md
```

## Micro-skill contract

Each `readiness-frame-*` skill:

- Sets `research_harness: true` with `plan_surfaces_path` pointing at a **narrow** surface list
- Declares `deliverables` and `frame_artifact` for one JSON handoff
- Optionally declares `coverage_contract` for deterministic audit (e.g. eval rows)
- Uses platform bootstrap + tool-loop retrieval; does **not** expand surfaces in platform Python

## Chain invocation

Invoke via existing `/api/ui/skill-chains/invoke` with `context_artifacts` carrying upstream JSON handoffs. `mission-readiness-framer` merges handoffs before synthesis.

Recommended chain (parallel where possible):

1. `readiness-frame-workload` + `readiness-frame-eval` (parallel)
2. `readiness-frame-pains` + `readiness-frame-modernization` + `readiness-frame-tea-leaves` (parallel)
3. `readiness-frame-win-themes`
4. `readiness-frame-external-research` (only when `detect_external_research_intent()` fires)
5. `mission-readiness-framer` (compile + platform synthesis → `brief.md`)

## Tuning

Adjust retrieval breadth via **Settings → Query Tuning** (`ui_query_settings.json`). Use **Apply recommendations** when the workspace-size banner appears — do not edit `.env` manually for per-workspace tuning.