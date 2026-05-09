---
name: global-idea-capturer
description: Captures fleeting govcon thoughts, cross-opportunity insights, brain dumps, and "things I should remember" into the Theseus global inbox as Obsidian-flavored Markdown — the default capture surface for the Ariadne's Thread dashboard. USE WHEN the user says "capture this", "save this for Theseus", "brain dump", "I just realized", "remember this", "for the LLM wiki", "cross-opportunity note", or any variant of recording a thought that is NOT scoped to a single active RFP workspace. Writes directly to `global/inbox/<YYYY-MM-DD>-<slug>.md` with frontmatter, never mutates a workspace KG, and leaves promotion to a workspace as an explicit separate step (handled by `phase-promoter` in 174.5). DO NOT USE FOR drafting proposal prose (use `proposal-generator`), structured idea exploration without a save target (use the vendored `idea-capturer`), or anything that requires KG writes.
metadata:
  developer_only: false
  personas_primary: capture_manager
  personas_secondary: [proposal_manager]
  shipley_phases: []
  capability: meta
  runtime: tools
  derives_from: idea-capturer
  global_store_target: global/inbox/
---

# Global Idea Capturer

Default capture surface for Ariadne's Thread. Friction-free writes to `global/inbox/`. One note per capture. Obsidian-flavored Markdown so the user can open `global/` in Obsidian directly.

> [!note] Relationship to vendored `idea-capturer`
> The vendored `idea-capturer` (eddiebe147 via skills.sh) is a generic Zettelkasten-style ideation framework with no save target. This derivative is Theseus-specific: it knows about the global store layout, the Obsidian frontmatter contract, the active workspace, and the `phase-promoter` handoff. Use the vendored skill for unstructured exploration; use this one when the goal is to capture and save.

## Workflow

1. **Read the user's text verbatim.** Do not rephrase, summarize, or expand. The capture moment is sacred — your job is to add structure around the user's words, not edit them.
2. **Detect the active workspace** (if any). Check the conversation context for an active workspace name (e.g., `afcap6_drfp_171`). If present, record it in frontmatter `workspace:` so `phase-promoter` can route promotion later. If absent, leave the field empty.
3. **Generate the slug.** Derive a 3–6-word kebab-case slug from the first sentence or the dominant noun phrase. Examples: `afcap6-incumbent-wrap-rate`, `llm-wiki-structure-ideas`, `oci-sweeper-prior-contracts`.
4. **Generate frontmatter** following the contract in [references/frontmatter.md](references/frontmatter.md). Required fields: `date`, `source`, `status`, `tags`. Optional: `workspace`, `wikilinks`, `priority`.
5. **Compose the note body.** User's text first, verbatim. Then a `## Context` section if the conversation made the trigger obvious (e.g., "captured during pricing review of AFCAP6"). Then `## Wikilinks` listing any `[[skill-name]]` or `[[workspace-name]]` references the user mentioned or you inferred. Do NOT add commentary, "good idea!" framing, or recommendations.
6. **Write the file.** Path: `global/inbox/<YYYY-MM-DD>-<slug>.md`. Use `write_global_note` so the note lands at the real inbox path.
7. **Report.** Single line: `Captured → <path>`. No celebration. No follow-up questions unless the user's text was ambiguous in a way that affects the slug or tags.

## Anti-patterns (do not do)

- Don't promote the note into a workspace LightRAG. Promotion is `phase-promoter`'s job (174.5).
- Don't ask the user "do you want to develop this further?" — that's the vendored `idea-capturer`'s workflow, not this one. Capture is a one-shot save.
- Don't split a single brain dump into multiple notes even if it contains 3 ideas. The inbox is the rough tier; splitting happens at the `processed/` tier in `phase-promoter`.
- Don't infer a `priority:` value the user didn't state. Leave it absent.
- Don't add tags the user's text doesn't justify. Tags should be verifiable from the body, not aspirational.

## Tag vocabulary

Pick from existing tag families to keep the inbox searchable:

- **Skill names** (when the capture is about extending a skill): `oci-sweeper`, `workload-analyzer`, `proposal-generator`, etc.
- **Opportunity codes** (when the capture is about a specific RFP, even if not the active workspace): `afcap6`, `afcap5`, etc.
- **Domains**: `pricing`, `compliance`, `competitive-intel`, `ontology`, `ui`, `meta`.
- **Tier hints**: `llm-wiki` (graduates to `global/llm-wiki/` later), `evergreen` (durable knowledge), `ephemeral` (delete after action).

Two to four tags is right. One tag is too few; six is too many.

## Example

User input:

> Capture this for Theseus: AFCAP6 incumbent likely fielding lower wrap rate than us; need to verify via USAspending obligation trend before pricing.

File written to `global/inbox/2026-05-08-afcap6-incumbent-wrap-rate.md`:

```markdown
---
date: 2026-05-08
source: capture
status: inbox
workspace: afcap6_drfp_171
tags: [afcap6, pricing, competitive-intel]
wikilinks: [[competitive-intel]] [[price-to-win]]
---

AFCAP6 incumbent likely fielding lower wrap rate than us; need to verify via USAspending obligation trend before pricing.

## Context

Captured during AFCAP6 pricing review. Active workspace: `afcap6_drfp_171`.

## Wikilinks

- [[competitive-intel]] — to pull obligation history
- [[price-to-win]] — to back into incumbent wrap rate
```

Response:

```
Captured → global/inbox/2026-05-08-afcap6-incumbent-wrap-rate.md
```
