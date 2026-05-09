---
name: phase-promoter
description: Promotes Ariadne inbox captures into processed notes, evergreen knowledge, workspace-ready source files, and optional LLM Wiki seeds. USE WHEN the user says "promote this note", "graduate this inbox item", "turn this capture into evergreen", "split this brain dump", "move this into the workspace", "prepare this for the LLM wiki", or any variant of curating saved global notes rather than capturing new ones. Accepts upstream handoffs from `global-idea-capturer` or explicit note paths, and emits staged Obsidian-flavored Markdown artifacts plus intended target paths. DO NOT USE FOR raw capture (use `global-idea-capturer`), proposal drafting, or KG extraction.
metadata:
  developer_only: false
  personas_primary: capture_manager
  personas_secondary: [proposal_manager]
  shipley_phases: []
  capability: meta
  runtime: legacy
  global_store_targets: [global/notes/, global/llm-wiki/]
---

# Phase Promoter

Turns rough captures into durable knowledge. It preserves provenance, advances a note only as far as the source supports, and keeps workspace promotion explicit.

## Workflow

1. **Locate the source note(s).** Prefer upstream `input_artifacts` from the Theseus Chain Handoff. If none exist, ask the user for one or more note paths under `global/inbox/` or `global/notes/`.
2. **Read the promotion model** in [references/promotion-model.md](references/promotion-model.md). Preserve the source note's `workspace`, `tags`, `wikilinks`, `priority`, and provenance.
3. **Decide the highest justified tier for each source.**
   - `processed`: clearer structure or splitting is useful, but the note is still provisional.
   - `evergreen`: durable and reusable enough to live in `global/notes/`.
   - `llm-wiki`: cross-opportunity, topic-dense knowledge worth exporting to `global/llm-wiki/`.
   - `workspace_source`: the note should also be copied into `rag_storage/<workspace>/sources/` for a specific opportunity.
4. **Synthesize the promoted note(s).** Use Obsidian-flavored Markdown. Every synthesized note must set `source: synth`, add `derives_from: <source-path>`, keep justified tags, and update `status:` to `processed` or `evergreen`.
5. **Split only when the source clearly contains distinct durable ideas.** A single brain dump may yield multiple processed notes, but every child note must cite the same `derives_from` source.
6. **Stage artifacts under `<run_dir>/artifacts/phase-promoter/`.** Mirror the intended target filenames. Current runtime limitation: do not claim you wrote directly to repo `global/` or `rag_storage/` unless a tool actually did that.
7. **Use a human gate when routing is ambiguous.** If tier choice, wiki export, or workspace routing is unclear, stop and ask one tight question. Exact missing inputs matter more than polished prose.
8. **Report the result in three sections:** `Staged artifacts`, `Intended target paths`, and `Exact gaps` (only when needed).

## Rules

- Preserve user wording where it carries signal; compress only redundancy.
- Never drop provenance. Every synthesized note cites `derives_from`.
- Never mutate the KG directly. Workspace promotion means a markdown copy into `rag_storage/<workspace>/sources/`.
- Do not export to `global/llm-wiki/` just because the user mentioned "wiki". The content must be dense, reusable, and cross-opportunity.
- Do not mark a note `evergreen` if it depends on a one-off tactical decision or stale intel.

## Output Contract

Always make the deliverable easy to apply manually or by a later automation pass.

- `Staged artifacts`: bullet list of files actually written under `<run_dir>/artifacts/phase-promoter/`.
- `Intended target paths`: bullet list mapping each staged artifact to its target under `global/notes/`, `global/llm-wiki/`, or `rag_storage/<workspace>/sources/`.
- `Exact gaps`: only include when promotion cannot safely proceed without another user decision.

## Example

Source note: `global/inbox/2026-05-09-afcap6-wrap-rate.md`

Promotion outcome:

- `phase-promoter/2026-05-09-afcap6-wrap-rate-evergreen.md` -> intended target `global/notes/2026-05-09-afcap6-wrap-rate-evergreen.md`
- `phase-promoter/2026-05-09-afcap6-wrap-rate-source.md` -> intended target `rag_storage/afcap6_drfp_171/sources/2026-05-09-afcap6-wrap-rate-source.md`

Both synthesized notes keep the relevant tags, set `source: synth`, and add `derives_from: inbox/2026-05-09-afcap6-wrap-rate.md`.