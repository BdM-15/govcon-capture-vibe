---
name: improve-codebase-architecture
description: "**Developer tool — for Theseus contributors only. Not a govcon platform skill; does not query the KG or RFP workspace.**\nSurfaces architectural friction in the Theseus codebase and proposes deepening opportunities — refactors that turn shallow pass-through modules into deep, high-leverage ones. USE WHEN the user asks to \"improve the architecture,\" \"find refactoring opportunities,\" \"identify shallow modules,\" \"make this easier to test,\" \"consolidate tightly-coupled files,\" or asks what to clean up or how to improve the codebase structure. Also triggers on \"this is too hard to navigate,\" \"too many small files,\" \"where should I start refactoring,\" \"this is getting messy,\" or any variant of code quality, coupling, or design within the Theseus repo itself. Uses domain vocabulary from CONTEXT.md, and records rejected candidates as ADRs so the same ground is never re-litigated. DO NOT USE FOR govcon analysis, RFP review, proposal drafting, or any workspace-query task."
license: Apache-2.0
metadata:
  version: 1.0.0
  category: developer-tool
  status: active
  runtime: tools-fetch
  developer_only: true # Not surfaced in the Theseus govcon UI
  upstream: https://github.com/mattpocock/skills/tree/main/skills/engineering/improve-codebase-architecture
  personas_primary: none
  personas_secondary: []
  shipley_phases: []
  capability: meta
---

# Improve Codebase Architecture

Surface architectural friction and propose **deepening opportunities** — refactors that turn shallow modules into deep ones. The aim is testability and AI-navigability.

## Glossary

Use these terms exactly in every suggestion. Consistent language is the point — don't drift into "component," "service," "API," or "boundary." Full definitions in [references/LANGUAGE.md](references/LANGUAGE.md).

- **Module** — anything with an interface and an implementation (function, class, package, slice).
- **Interface** — everything a caller must know to use the module: types, invariants, error modes, ordering, config. Not just the type signature.
- **Implementation** — the code inside.
- **Depth** — leverage at the interface: a lot of behaviour behind a small interface. **Deep** = high leverage. **Shallow** = interface nearly as complex as the implementation.
- **Seam** — where an interface lives; a place behaviour can be altered without editing in place. (Use this, not "boundary.")
- **Adapter** — a concrete thing satisfying an interface at a seam.
- **Leverage** — what callers get from depth.
- **Locality** — what maintainers get from depth: change, bugs, knowledge concentrated in one place.

Key principles (see [references/LANGUAGE.md](references/LANGUAGE.md) for the full list):

- **Deletion test**: imagine deleting the module. If complexity vanishes, it was a pass-through. If complexity reappears across N callers, it was earning its keep.
- **The interface is the test surface.**
- **One adapter = hypothetical seam. Two adapters = real seam.**

This skill is _informed_ by the project's domain model. The domain language gives names to good seams; ADRs record decisions the skill should not re-litigate.

## Process

### 1. Explore

Read the project's domain glossary (`CONTEXT.md` at repo root if it exists) and any ADRs in `docs/adr/` relevant to the area you're touching first. Explore organically with `read_file`, `grep_search`, and `semantic_search`. Don't follow rigid heuristics — note where you experience friction:

- Where does understanding one concept require bouncing between many small modules?
- Where are modules **shallow** — interface nearly as complex as the implementation?
- Where have pure functions been extracted just for testability, but the real bugs hide in how they're called (no **locality**)?
- Where do tightly-coupled modules leak across their seams?
- Which parts of the codebase are untested, or hard to test through their current interface?

Apply the **deletion test** to anything you suspect is shallow: would deleting it concentrate complexity, or just move it? A "yes, concentrates" is the signal you want.

### 2. Present candidates

Present a numbered list of deepening opportunities. For each candidate:

- **Files** — which files/modules are involved
- **Problem** — why the current architecture is causing friction
- **Solution** — plain English description of what would change
- **Benefits** — explained in terms of locality and leverage, and also in how tests would improve

**Use CONTEXT.md vocabulary for the domain, and [references/LANGUAGE.md](references/LANGUAGE.md) vocabulary for the architecture.** If `CONTEXT.md` defines a term, use it — not an ad-hoc synonym.

**ADR conflicts**: if a candidate contradicts an existing ADR in `docs/adr/`, only surface it when the friction is real enough to warrant revisiting the decision. Mark it clearly (e.g. _"contradicts ADR-0007 — but worth reopening because…"_). Don't list every theoretical refactor an ADR forbids.

Do NOT propose interfaces yet. Ask the user: "Which of these would you like to explore?"

### 3. Grilling loop

Once the user picks a candidate, drop into a grilling conversation. Walk the design tree with them — constraints, dependencies, the shape of the deepened module, what sits behind the seam, what tests survive.

Side effects happen inline as decisions crystallize:

- **Naming a deepened module after a concept not in `CONTEXT.md`?** Add the term to `CONTEXT.md` — see [references/CONTEXT-FORMAT.md](references/CONTEXT-FORMAT.md) for structure. Create the file lazily if it doesn't exist.
- **Sharpening a fuzzy term during the conversation?** Update `CONTEXT.md` right there.
- **User rejects the candidate with a load-bearing reason?** Offer an ADR, framed as: _"Want me to record this as an ADR so future architecture reviews don't re-suggest it?"_ Only offer when the reason would actually be needed by a future explorer — skip ephemeral reasons ("not worth it right now") and self-evident ones. See [references/ADR-FORMAT.md](references/ADR-FORMAT.md).
- **Want to explore alternative interfaces for the deepened module?** See [references/INTERFACE-DESIGN.md](references/INTERFACE-DESIGN.md).
