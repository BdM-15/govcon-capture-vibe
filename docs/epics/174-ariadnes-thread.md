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
- [ ] Vendored skills (`obsidian-markdown`, `idea-capturer`) live under `.github/skills/<name>/` with per-skill `UPSTREAM.md` (commit SHA, license, adaptation log). `theseus-skills/README.md` mapping table is the single index.
- [ ] `obsidian-markdown` (kepano) and `idea-capturer` (eddiebe147) are vendored, license-attributed, and Theseus-adapted (paths, tool registry, govcon prompts).
- [ ] `global-idea-capturer` skill exists, defaults to `global/inbox/`, supports local-LLM polish, and exposes a "promote to workspace" handoff.
- [ ] `global/{inbox,notes,llm-wiki,intel}/` directory layout exists; `GlobalStore` service in `src/core/`; `/api/global/*` routes registered.
- [ ] Ariadne's Thread dashboard is the new top-level UI (`/`); current Workbench is reachable at `/workspace/<name>`.
- [ ] Command-center IA is live: Morning Brief, Action Queue, Opportunity Cards, Stage Board; inventory metrics demoted to System view.
- [ ] `phase-promoter` skill chain handles source → processed → evergreen promotion using v1.12 chain features (HITL, semantic labels, handoffs) and supports LLM Wiki / intel synthesis flow.
- [ ] Canonical `pursuits/<slug>/00_pursuit.yaml` + Shipley folder scaffold exist per workspace and feed dashboard cards/stage board.
- [ ] 174.7 ships seven vault-driven views: Today, Pipeline, Decision Queue, Intel Desk, Opp 360, Knowledge, Agent Ops.
- [ ] 174.8 delivers vault <-> `rag_storage` / LightRAG round-trip, including explicit refresh/delete-by-doc flow.
- [ ] 174.9 adds Shipley/FAR seeds, color-team templates, and cross-opportunity pattern feed.
- [ ] All new Markdown is Obsidian-flavored (yaml frontmatter, `[[wikilinks]]`, callouts).
- [ ] Repo memory updated; `.github/copilot-instructions.md` "Active integration branches" updated; `branch-integration-policy.md` updated.
- [ ] Tag `v1.13.0`; merge to `main` with regular merge commit.

## Phased Plan

### 174.0 — Epic scaffold (this commit)

- Create branch `174-ariadnes-thread-epic`.
- Create `docs/epics/174-ariadnes-thread.md` (this file).
- Create `global/{inbox,notes,llm-wiki,intel}/.gitkeep` skeleton.
- Update repo memory: `/memories/repo/branch-integration-policy.md` + new `ariadnes-thread-epic.md`.
- **Out of scope here:** any code changes; any vendored content; any UI changes.

### 174.1 — Vendor pipeline (single-root)

- Sub-branch `174.1-vendor-pipeline`.
- Vendor `obsidian-markdown` (kepano) into `.github/skills/obsidian-markdown/` with `UPSTREAM.md` (commit SHA + MIT attribution + adaptation log) + verbatim `LICENSE`.
- Vendor `idea-capturer` (eddiebe147 / skills.sh) into `.github/skills/idea-capturer/` with `UPSTREAM.md` (license caveat documented).
- Update `theseus-skills/README.md` mapping table to list both new vendored skills.
- **Decision (post-kickoff):** original plan called for a separate `theseus-skills/vendor/` root + dual-root discovery in `SkillCatalog`. Reverted — single-dev repo, no need for the extra surface area. Provenance lives in per-skill `UPSTREAM.md` + the README mapping (same pattern as existing vendored skills like `caveman`, `tdd`, `huashu-design`).
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

### 174.4b — Command-center IA rewrite

- Replace generic dashboard panels with Morning Brief, Action Queue, Opportunity Cards, and Stage Board.
- Back these views with `00_pursuit.yaml`-driven metadata rather than placeholder inventory summaries.
- Demote raw inventory metrics to System view so Ariadne stays operator-facing.
- Acceptance: dashboard reads like command center, not admin console.

### 174.5 — `phase-promoter` chain + wiki/intel synthesis

- Sub-branch `174.5-phase-promoter`.
- New skill at `.github/skills/phase-promoter/` with chain contract in `src/skills/chain_contracts.py`.
- Workflow: select source files in `sources/` → analyze with LLM → synthesize into `processed/` → human-in-the-loop confirm → write to `evergreen/` → re-ingest selectively into LightRAG → optionally export to `global/llm-wiki/`.
- Reuses v1.12 HITL + semantic labels.
- Includes Karpathy-style LLM Wiki / intel synthesis pattern and local Qwen 7-9B note-polish path.
- Tests: chain executor integration test + planner test.

### 174.6 — Pursuit schema + dashboard cards

- Sub-branch `174.6-pursuit-dashboard`.
- Add a canonical `pursuits/<slug>/00_pursuit.yaml` per workspace with editable pursuit metadata: agency, Shipley stage, upcoming gate, proposal due date, weighted PWin drivers, and 7-axis readiness bars.
- Seed a Shipley folder template alongside that file so every workspace has a standard pursuit structure without manual setup.
- Populate Ariadne opportunity cards and the stage board from this pursuit metadata instead of placeholders.

### 174.7 — Vault-driven views

- Ship seven core Ariadne views as Alpine routes: Today, Pipeline, Decision Queue, Intel Desk, Opp 360, Knowledge, Agent Ops.
- Keep Ariadne global-first; workspace routes remain deep-dive mode.
- Reuse existing dashboard data paths where possible instead of building parallel stores.

### 174.8 — Ontology overlay + LightRAG round-trip

- Add `ontology_promoter` flow bridging vault artifacts and workspace `rag_storage`.
- Make promotion to workspace KG explicit and reversible.
- Support LightRAG refresh path using delete-by-doc / re-ingest mechanics instead of ad hoc storage surgery.

### 174.9 — Seeds + cross-opportunity patterns

- Seed Shipley/FAR starter content and color-team templates.
- Add cross-opportunity pattern feed for reusable capture, intel, and proposal signals.
- Focus on population layer: make Ariadne useful on day one, not only after long manual curation.

### 174.10 — Integration & release

- Run full test suite from `.venv`.
- Bump version to `v1.13.0`.
- Update `README.md` with new dashboard screenshot.
- Update `docs/ARCHITECTURE.md` global vs workspace model.
- Update `.github/copilot-instructions.md` "Active integration branches" + cross-cutting checklist if entity/relationship vocab changed (it shouldn't here).
- Update `/memories/repo/branch-integration-policy.md`.
- Merge to `main` with regular merge commit (NOT `--ff-only`).
- Tag `v1.13.0`. Push tag.

## Architecture Decisions

### AD-1: Single skill root

All skills — first-party, dual-purpose, and vendored — live under `.github/skills/<name>/`. Provenance for vendored copies is recorded in per-skill `UPSTREAM.md` and indexed in `theseus-skills/README.md`. Single-dev repo doesn't justify the extra surface area of a second discovery root. (Original plan called for `theseus-skills/vendor/` as a separate root; reverted in 174.1.)

### AD-2: Global layer is Markdown-on-disk

Not a LightRAG instance. Cheaper, matches Obsidian mental model, no embedding cost on capture. Promotion to a workspace = explicit re-ingest into that workspace's LightRAG. Search across global = lightweight (ripgrep + frontmatter index).

### AD-3: Dashboard is incremental, not rewrite

Adds new top-level Alpine component + route. Existing `index.html` Workbench becomes `/workspace/<name>`. No framework change. No build step.

### AD-4: Per-skill UPSTREAM.md, not git submodule

Each vendored skill carries its own `UPSTREAM.md` with upstream URL + commit SHA + license + adaptation log + re-vendor procedure. Re-vendor is a deliberate documented command. Submodules introduce CI friction we don't need for a single-dev repo.

### AD-5: `phase-promoter` is a skill chain, not new infrastructure

Reuses v1.12 chain executor (HITL, semantic labels, handoffs). Validates that the chain infrastructure is general enough — if it isn't, that's a v1.12 bug to fix, not a reason to fork.

## Out of Scope (Explicit)

- No new build step, framework, or database.
- No live Obsidian sync (we emit Obsidian-flavored MD; opening in Obsidian is a user-side choice).
- No multi-user / auth.
- No replacement of Capture Workbench.
- No vendoring of additional skills beyond `obsidian-markdown` and `idea-capturer` in this epic.

## Tracking

Each phase = one sub-branch. Sub-branches FF into `174-ariadnes-thread-epic`. Epic merges to `main` only after 174.9 / release work with full test green + user approval.

Per project mandate: every skill creation/modification in 174.2, 174.5, 174.6 **must load `skill-creator`** and follow its workflow (snapshot → evals → baseline → draft → iterate). No shortcuts.
