# Epic 174 — Ariadne's Thread

> **Branch:** `174-ariadnes-thread-epic` · **Target version:** `v1.13.0` · **Integration:** merge commit to `main`
>
> This file is also the GitHub Issue body. Copy/paste verbatim when filing the issue, or use it as the source of truth and let the issue link back here.

## Vision

Turn Theseus into a **personal capture operating system** where **Ariadne's Thread** is the central command center the user lives in daily. **Global capture is the default**; per-opportunity workspaces become **secondary focused-view "deep dive" modes** the user enters only when an opportunity warrants full Theseus processing.

The current Capture Workbench (single-workspace UI) stays — it becomes the deep view. The new dashboard layer wraps it.

## Core Philosophy (Non-Negotiable)

1. Global is the default. Most daily work is global.
2. Workspaces are focused views, not the home.
3. Ariadne's Thread is the management framework — global intel, cross-opportunity synthesis, pipeline status, LLM Wiki, and quick capture all in one place.
4. Minimal bloat. Reuse the v1.10–v1.12 skill chain infrastructure heavily.
5. One LightRAG per workspace. Global layer is Markdown-on-disk + lightweight index, not a KG.
6. All new Markdown is Obsidian-flavored.

## Acceptance Criteria

- [ ] Epic branch `174-ariadnes-thread-epic` exists and is the integration target for sub-branches.
- [ ] `theseus-skills/vendor/` exists with `MANIFEST.yaml` pinning upstream URL + commit + license per vendored skill.
- [ ] `SkillCatalog` discovers skills from **both** `.github/skills/` and `theseus-skills/vendor/` (single-root assumption removed).
- [ ] `obsidian-markdown` (kepano) and `idea-capturer` (eddiebe147) are vendored, license-attributed, and Theseus-adapted (paths, tool registry, govcon prompts).
- [ ] `global-idea-capturer` skill exists, defaults to `global/inbox/`, supports local-LLM polish, and exposes a "promote to workspace" handoff.
- [ ] `global/{inbox,notes,llm-wiki,intel}/` directory layout exists; `GlobalStore` service in `src/core/`; `/api/global/*` routes registered.
- [ ] Ariadne's Thread dashboard is the new top-level UI (`/`); current Workbench is reachable at `/workspace/<name>`.
- [ ] Dashboard panels: global inbox, opportunity pipeline (lightweight status across all workspaces), LLM wiki tree, cross-opportunity intel feed, quick-capture box.
- [ ] `phase-promoter` skill chain handles `sources → processed → evergreen → active` promotion using v1.12 chain features (HITL, semantic labels, handoffs).
- [ ] Cross-opportunity synthesis chain compacts `global/notes/` into `global/llm-wiki/<topic>.md` (Karpathy-style LLM Wiki).
- [ ] All new Markdown is Obsidian-flavored (yaml frontmatter, `[[wikilinks]]`, callouts).
- [ ] `tests/` cover: skill discovery from two roots, GlobalStore CRUD, dashboard route, `global-idea-capturer` end-to-end, `phase-promoter` chain.
- [ ] Repo memory updated; `docs/copilot-instructions.md` "Active integration branches" updated; `branch-integration-policy.md` updated.
- [ ] Tag `v1.13.0`; merge to `main` with regular merge commit.

## Phased Plan

### 174.0 — Epic scaffold (this commit)
- Create branch `174-ariadnes-thread-epic`.
- Create `docs/epics/174-ariadnes-thread.md` (this file).
- Create `global/{inbox,notes,llm-wiki,intel}/.gitkeep` skeleton.
- Create `theseus-skills/vendor/MANIFEST.yaml` with placeholder entries.
- Update repo memory: `/memories/repo/branch-integration-policy.md` + new `ariadnes-thread-epic.md`.
- **Out of scope here:** any code changes; any vendored content; any UI changes.

### 174.1 — Vendor pipeline + dual skill roots
- Sub-branch `174.1-vendor-pipeline`.
- Modify `src/skills/skill_catalog.py`: replace `_SKILLS_DIR` with `_SKILL_ROOTS = [...]`; iterate both in `discover()`. Conflict policy: `.github/skills/` wins over `theseus-skills/vendor/` if both define same name (loud warning).
- Add `tests/test_skill_dual_roots.py`.
- Vendor `obsidian-markdown` (kepano) into `theseus-skills/vendor/obsidian-markdown/`. Include `UPSTREAM.md` with commit SHA + Apache-2.0 (or actual) attribution + Theseus adaptation notes.
- Vendor `idea-capturer` (eddiebe147 / claude-settings) into `theseus-skills/vendor/idea-capturer/`. Same UPSTREAM.md treatment.
- Update `MANIFEST.yaml` with real SHAs and licenses.
- **Acceptance:** `manager.list_skills()` returns vendored skills; existing skill tests still pass.

### 174.2 — `global-idea-capturer` skill
- Sub-branch `174.2-global-idea-capturer`.
- New skill at `.github/skills/global-idea-capturer/` (Theseus platform tier, not vendor — adapts the vendored idea-capturer specifically for Theseus global flow).
- Tools: `filesystem.write_global(path, content)`, `llm.polish(text)` (uses `llm_chat.py`), `workspace.promote(note_id, target_workspace)`.
- Default landing: `global/inbox/<YYYY-MM-DD>-<slug>.md` with Obsidian frontmatter.
- `evals/evals.json` with ≥3 test prompts (per skill-creator workflow).
- **MUST load `skill-creator` per project mandate.**

### 174.3 — Global storage backend
- Sub-branch `174.3-global-store`.
- `src/core/global_store.py`: thin facade — `read(path)`, `write(path, content)`, `list(prefix)`, `search(query)` over `global/`.
- `src/server/global_routes.py`: `/api/global/inbox`, `/api/global/notes`, `/api/global/llm-wiki`, `/api/global/intel`, `/api/global/capture`, `/api/global/promote`.
- Tests: `tests/test_global_store.py`, `tests/test_global_routes.py`.

### 174.4 — Ariadne's Thread dashboard UI
- Sub-branch `174.4-ariadne-dashboard`.
- New `src/ui/static/dashboard.html` (Alpine component `ariadne()`).
- Move current `index.html` mount to `/workspace/<name>`; new `/` serves dashboard.
- Dashboard panels (in order of build):
  1. Global Quick Capture box (top, always visible) — wires to `global-idea-capturer`.
  2. Opportunity Pipeline strip — pulls workspace stats via existing `/workspaces` endpoint; click → focused view.
  3. Global Inbox feed (latest 20 notes from `global/inbox/`).
  4. LLM Wiki tree (lazy-loaded from `global/llm-wiki/`).
  5. Cross-Opportunity Intel feed (entries from `global/intel/`).
- Markdown rendering uses vendored `obsidian-markdown` skill's renderer logic (or its referenced library).
- Style budget: stay within existing `theseus.css` token system. No new CSS framework.
- Tests: `tests/test_dashboard_routes.py`, smoke test for Alpine state.

### 174.5 — `phase-promoter` chain
- Sub-branch `174.5-phase-promoter`.
- New skill at `.github/skills/phase-promoter/` with chain contract in `src/skills/chain_contracts.py`.
- Workflow: select source files in `sources/` → analyze with LLM → synthesize into `processed/` → human-in-the-loop confirm → write to `evergreen/` → re-ingest selectively into LightRAG → optionally export to `global/llm-wiki/`.
- Reuses v1.12 HITL + semantic labels.
- Tests: chain executor integration test + planner test.

### 174.6 — LLM Wiki compaction chain
- Sub-branch `174.6-llm-wiki-compaction`.
- New skill `llm-wiki-compactor` (or extend `phase-promoter`) — periodic synthesis of `global/notes/` into topical `global/llm-wiki/<topic>.md` files.
- Karpathy-style: each wiki page is dense, current, single-source-of-truth on a topic; old notes archived not deleted.

### 174.7 — Integration & release
- Run full test suite from `.venv`.
- Bump version to `v1.13.0`.
- Update `README.md` with new dashboard screenshot.
- Update `docs/ARCHITECTURE.md` global vs workspace model.
- Update `.github/copilot-instructions.md` "Active integration branches" + cross-cutting checklist if entity/relationship vocab changed (it shouldn't here).
- Update `/memories/repo/branch-integration-policy.md`.
- Merge to `main` with regular merge commit (NOT `--ff-only`).
- Tag `v1.13.0`. Push tag.

## Architecture Decisions

### AD-1: Two skill roots
`SkillCatalog` walks both `.github/skills/` (Theseus-authored + classic vendored) and `theseus-skills/vendor/` (force-multiplier external skills). Avoids copy/symlink. Conflict resolution: `.github/skills/` wins, loud warning logged. ~10 LOC change.

### AD-2: Global layer is Markdown-on-disk
Not a LightRAG instance. Cheaper, matches Obsidian mental model, no embedding cost on capture. Promotion to a workspace = explicit re-ingest into that workspace's LightRAG. Search across global = lightweight (ripgrep + frontmatter index).

### AD-3: Dashboard is incremental, not rewrite
Adds new top-level Alpine component + route. Existing `index.html` Workbench becomes `/workspace/<name>`. No framework change. No build step.

### AD-4: Vendor manifest, not git submodule
`theseus-skills/vendor/MANIFEST.yaml` pins upstream URL + commit SHA + license + adaptation notes. Re-vendor is a deliberate documented command. Submodules introduce CI friction we don't need for a single-dev repo.

### AD-5: `phase-promoter` is a skill chain, not new infrastructure
Reuses v1.12 chain executor (HITL, semantic labels, handoffs). Validates that the chain infrastructure is general enough — if it isn't, that's a v1.12 bug to fix, not a reason to fork.

## Out of Scope (Explicit)

- No new build step, framework, or database.
- No live Obsidian sync (we emit Obsidian-flavored MD; opening in Obsidian is a user-side choice).
- No multi-user / auth.
- No replacement of Capture Workbench.
- No vendoring of additional skills beyond `obsidian-markdown` and `idea-capturer` in this epic.

## Tracking

Each phase = one sub-branch. Sub-branches FF into `174-ariadnes-thread-epic`. Epic merges to `main` only at 174.7 with full test green + user approval.

Per project mandate: every skill creation/modification in 174.2, 174.5, 174.6 **must load `skill-creator`** and follow its workflow (snapshot → evals → baseline → draft → iterate). No shortcuts.
