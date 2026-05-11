# Upstream Provenance

| Field          | Value                                                                                      |
| -------------- | ------------------------------------------------------------------------------------------ |
| Source repo    | https://github.com/mattpocock/skills                                                       |
| Source path    | `skills/productivity/grill-me/SKILL.md`                                                    |
| License        | Apache-2.0                                                                                 |
| Vendored on    | 2026-05-01                                                                                 |
| Vendored by    | GitHub Copilot (branch `154-phase1.2-json-prompt-conversion`)                              |
| Upstream rev   | `62f43a18177be6ec82da242e59ffbc490a4c22ea`                                                 |

## Adaptations

1. **Metadata block added** — `license: Apache-2.0` and a `metadata:` block with Theseus Phase 4j taxonomy keys (`personas_primary`, `capability`, `developer_only`, etc.) added to frontmatter. No upstream spec field is removed or changed.
2. **Description extended** — added a Theseus-local routing boundary so `grill-me` stays a developer-only stress-test skill while govcon-specific capture, proposal, pricing, compliance, and intel work routes to purpose-built domain skills.
3. **`evals/evals.json` added** — three Theseus-specific eval prompts targeting codebase design decisions. Upstream has no evals directory.

## Re-vendor instructions

To pull a fresh upstream copy:

```powershell
$raw = Invoke-WebRequest -Uri "https://raw.githubusercontent.com/mattpocock/skills/main/skills/productivity/grill-me/SKILL.md" | Select-Object -ExpandProperty Content
# Review diff against .github/skills/grill-me/SKILL.md — re-apply the three adaptations above.
```

Only the body and upstream description change on re-vendor. The `metadata:` block and description extension are Theseus-local and must be preserved.
