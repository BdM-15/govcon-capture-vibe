# theseus-skills/vendor/

External agent skills vendored into Theseus as **force multipliers**. Discovered by `SkillCatalog` alongside `.github/skills/` once Phase 174.1 of the Ariadne's Thread epic lands.

## Why a separate root

`.github/skills/` holds Theseus-authored + classic-vendored skills (huashu-design, govcon-ontology, grill-me-*, etc.). Mixing third-party force-multiplier skills there muddies provenance. Keeping them in `theseus-skills/vendor/`:

- Makes upstream-license tracking explicit (one `MANIFEST.yaml`).
- Lets us re-vendor cleanly without diff noise in the primary skills dir.
- Keeps the single-root assumption out of `agentskills.io`-spec consumers (they read `.github/skills/` only; the vendor root is Theseus-specific).

## Conflict policy

If a skill name collides between roots, `.github/skills/` wins and `SkillCatalog` logs a loud warning. Don't shadow on purpose — rename the vendored copy.

## Adding a vendored skill

1. Add an entry to [`MANIFEST.yaml`](MANIFEST.yaml) (start `status: planned`, pin upstream URL).
2. Confirm upstream license is permissive (Apache-2.0, MIT, BSD).
3. Copy the skill directory into `theseus-skills/vendor/<name>/`.
4. Add `UPSTREAM.md` documenting commit SHA, license, and Theseus adaptations.
5. Apply adaptations (paths, tool registry, prompt language).
6. Flip `status: vendored` and fill `vendored_at`.
7. Run `tests/test_skill_dual_roots.py` (added in Phase 174.1).

## Re-vendoring

When upstream changes:

1. Bump `commit:` SHA in `MANIFEST.yaml`.
2. Re-copy upstream files; re-apply Theseus adaptations.
3. Update `UPSTREAM.md` adaptation log.
4. Re-run skill evals (`evals/evals.json`).
