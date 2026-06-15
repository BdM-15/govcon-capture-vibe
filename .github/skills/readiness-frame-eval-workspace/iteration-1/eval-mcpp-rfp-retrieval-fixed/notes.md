# Eval iteration-1 — retrieval path (partial)

Run `20260615_141630` (cancelled before handoff draft completed).

## Retrieval result (good)

- `plan_complete: true` after 4 `kg_chunks` + 1 `kg_entities`
- All four batch surfaces advanced (batch 4 saturated — zero new chunks)
- `phase: draft` — harness unlocked write
- Prior queries are the short plan-surface queries only (no manifest long-query poison)

## Why earlier runs failed / felt slow

1. Manifest `suggested_kg_chunks_query` overlapped → duplicate plan guard on batches 2–4
2. Generic plan surface keywords → `match_surface_id` credited every pass to `eval_batch_1`
3. Model retried `write_file` while still in retrieve phase → burned turns until cap
4. Skill `max_turns: 14` is ignored when below env default (`skill_tools_max_turns`); eval solo allows up to 24 turns

## Still open

- Full solo gate green + `eval_handoff.json` not verified this iteration
- Next smoke should complete in ~8–10 turns if draft writes once after `plan_complete`