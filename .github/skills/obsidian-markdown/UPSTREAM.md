# Upstream provenance — `obsidian-markdown`

This skill is **vendored** from an external upstream. Do not hand-edit without recording the change in the "Theseus adaptation log" below — re-vendoring will overwrite local edits otherwise.

## Source

| Field         | Value                                                                  |
| ------------- | ---------------------------------------------------------------------- |
| Upstream repo | https://github.com/kepano/obsidian-skills                              |
| Upstream path | `skills/obsidian-markdown/`                                            |
| Pinned commit | `ac9398734fe719565809f7a6048b05c36b1ca38f`                             |
| Vendored at   | 2026-05-08                                                             |
| License       | MIT (Copyright (c) 2026 Steph Ango / @kepano) — see [LICENSE](LICENSE) |
| Vendored by   | epic 174 (`174.1-vendor-pipeline`, merged)                             |

## Files vendored verbatim

- `SKILL.md` (5,367 bytes)
- `references/CALLOUTS.md` (1,238 bytes)
- `references/EMBEDS.md` (780 bytes)
- `references/PROPERTIES.md` (1,149 bytes)
- `LICENSE` (1,077 bytes)

These match the upstream blob SHAs at the pinned commit. No bytes have been modified yet.

## Theseus adaptation log

| Date       | Change                                                                                                                                                                                                 | Rationale                                                                                                              |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------- |
| 2026-05-08 | Initial vendor — verbatim copy.                                                                                                                                                                        | Phase 174.1 baseline. Adaptations land in follow-up commits so the diff is auditable.                                  |
| 2026-05-08 | Added Theseus `metadata:` block to SKILL.md frontmatter (`developer_only: true`, `personas_primary: none`, `personas_secondary: []`, `shipley_phases: []`, `capability: render`, `upstream:` pointer). | Required by `tests/skills/test_skill_taxonomy.py`. Spec-compliant — agentskills.io permits arbitrary `metadata:` keys. |
| 2026-05-08 | Promoted skill to dual-purpose tier (`developer_only: false`, `personas_secondary: [proposal_writer, capture_manager]`).                                                                             | User direction: vendored `obsidian-markdown` should appear as both Theseus platform skill and developer utility.      |

### Planned adaptations (not yet applied)

These are tracked but **not** applied yet, so the initial diff against upstream is empty:

- Path remap: when the skill writes notes, default target = `global/notes/` (or `rag_storage/<workspace>/evergreen/` when invoked inside a workspace context).
- Tool registry: declare in SKILL.md frontmatter `metadata:` block which Theseus tools the skill is allowed to call (`filesystem.write_global`, `filesystem.write_workspace`).
- Frontmatter schema: align skill-emitted note frontmatter with Theseus note model (add `theseus_layer: global|workspace`, `source_skill: <name>`, `created_at`).

When applied, each adaptation gets a row in the table above.

## Re-vendoring procedure

1. Pick a new upstream commit; record the SHA below in a new "Pinned commit" row.
2. `cd .github/skills/obsidian-markdown`
3. Re-run the four `Invoke-WebRequest` calls used in the initial vendor (record the exact URLs here when the pinned SHA changes).
4. Re-apply each adaptation in the table above (or note that an adaptation was upstreamed and removed).
5. Re-run any evals introduced under `evals/` (none yet — added when this skill is wired into the runtime).
6. Update the Source table above (`Pinned commit`, `Vendored at`) and add an adaptation-log row if behavior changed.
