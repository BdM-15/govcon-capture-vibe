# Upstream provenance — `idea-capturer`

This skill is **vendored** from an external upstream. The original is hosted on `skills.sh` (Claude-skill marketplace), not GitHub, and ships as a downloadable `SKILL.md` with no separate license file. Treat this entry as the lower-confidence vendor record under `.github/skills/`.

## Source

| Field        | Value                                                                                                                                                                                                                                                             |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Upstream URL | https://skills.sh/eddiebe147/claude-settings/idea-capturer                                                                                                                                                                                                        |
| Author       | Eddie Be (`@eddiebe147` on skills.sh)                                                                                                                                                                                                                             |
| Retrieved as | `idea-capturer.zip` (single-file SKILL.md, 14,469 bytes) attached to the epic-174 conversation on 2026-05-08                                                                                                                                                      |
| License      | **Not stated upstream.** skills.sh sharing convention implies permissive use; we treat it as MIT-equivalent for vendoring purposes pending author confirmation. **Action item:** contact author or check if a LICENSE is later published; record the answer here. |
| Vendored at  | 2026-05-08                                                                                                                                                                                                                                                        |

## Files vendored verbatim

- `SKILL.md` (14,469 bytes) — copied byte-for-byte from the attached zip; no other files exist in the upstream package (no `references/`, `scripts/`, `assets/`, or `evals/`).

## Why we vendored without a clear license

The user explicitly approved vendoring this skill in the epic-174 kickoff. The skill is the **source pattern** for the Theseus-platform-tier `global-idea-capturer` (which lives at `.github/skills/global-idea-capturer/` once 174.2 lands) — the vendored copy serves primarily as a reference for that derivative. If license clarification later forbids redistribution we will:

1. Remove `.github/skills/idea-capturer/SKILL.md`.
2. Update this `UPSTREAM.md` + `theseus-skills/README.md` to record the unvendoring and document why.
3. Keep the derivative `.github/skills/global-idea-capturer/` (which is a Theseus-original work informed by — but not copied from — the upstream pattern).

## Theseus adaptation log

| Date       | Change                                                                                                                                                                                               | Rationale                                                                                                              |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| 2026-05-08 | Initial vendor — verbatim copy.                                                                                                                                                                      | Phase 174.1 baseline. Derivative `global-idea-capturer` lands in 174.2; that's where adaptations live, not here.     |
| 2026-05-08 | Added Theseus `metadata:` block to SKILL.md frontmatter (`developer_only: true`, `personas_primary: none`, `personas_secondary: []`, `shipley_phases: []`, `capability: meta`, `upstream:` pointer). | Required by `tests/skills/test_skill_taxonomy.py`. Spec-compliant — agentskills.io permits arbitrary `metadata:` keys. |
| 2026-05-08 | Promoted skill to dual-purpose tier (`developer_only: false`, `personas_secondary: [capture_manager, proposal_manager]`).                                                                          | User direction: vendored `idea-capturer` should appear as both Theseus platform skill and developer utility.          |

### Planned adaptations (not applied to the vendored copy)

By design, **no adaptations are applied to the vendored file**. The vendored copy stays verbatim as a reference. Adaptations all land in the derivative `.github/skills/global-idea-capturer/`:

- Default capture dir → `global/inbox/`.
- Optional local-LLM polish step via `src/skills/llm_chat.py`.
- Promote-to-workspace handoff calling `/api/global/promote`.
- Theseus tool-registry declaration.
- Govcon-aware tagging vocabulary.

This split keeps the upstream auditable while letting the Theseus version evolve.

## Re-vendoring procedure

skills.sh does not expose a stable raw URL or commit SHA. To re-vendor:

1. Visit https://skills.sh/eddiebe147/claude-settings/idea-capturer.
2. Download the latest `idea-capturer.zip`.
3. Extract `idea-capturer/SKILL.md` and replace the vendored file.
4. Note the retrieval date in the Source table above and add a row to the adaptation log above.
5. Diff against the previous vendored copy; if upstream changed substantively, consider whether the derivative `global-idea-capturer` skill needs updating.
