# UPSTREAM — global-idea-capturer

This is a **Theseus-tier derivative** of the vendored [`idea-capturer`](../idea-capturer/) skill. Not a vendored copy — it does not track an external upstream.

## Lineage

- **Inspired by:** [`idea-capturer`](../idea-capturer/) (eddiebe147 via skills.sh, license unstated; vendored under epic 174.1).
- **Why a derivative instead of extending the vendored skill?** The vendored skill is a generic Zettelkasten ideation framework with no save target. Theseus needs a capture skill that:
  1. Writes to a specific path layout (`global/inbox/<YYYY-MM-DD>-<slug>.md`).
  2. Emits a specific Obsidian frontmatter contract that `GlobalStore` (174.3) and `phase-promoter` (174.5) can parse.
  3. Knows about the active workspace and routes `workspace:` field accordingly.
  4. Refuses to develop/explore — that's the vendored skill's job.
- Keeping the vendored copy unmodified means we can `git pull` upstream without losing Theseus adaptations.

## Diff vs vendored `idea-capturer`

| Concern              | Vendored `idea-capturer`                          | This derivative                                  |
|----------------------|---------------------------------------------------|--------------------------------------------------|
| Save target          | Unspecified                                       | `global/inbox/<YYYY-MM-DD>-<slug>.md`            |
| Frontmatter contract | Free-form                                         | Strict — see `references/frontmatter.md`         |
| Workflows            | 5 (capture, develop, organize, brainstorm, synth) | 1 (capture) — develop/synth handled by `phase-promoter` |
| Tag vocabulary       | Free-form                                         | Closed families (skill names, opportunity codes, domains, tier hints) |
| Workspace awareness  | None                                              | Records active workspace in frontmatter          |
| Promotion            | Implicit ("permanent notes")                      | Explicit handoff to `phase-promoter` (174.5)     |

## When the vendored skill triggers instead

The planner should pick the vendored `idea-capturer` when the user wants to **explore**, **develop**, or **brainstorm without saving**. The descriptions are tuned to make this differentiation:

- vendored: "develop a concept", "brainstorm [topic]", "synthesize insights"
- derivative: "capture this", "save this for Theseus", "remember this"

If both trigger, prefer the derivative — capture is the safer default (the user can always invoke vendored later for development).
