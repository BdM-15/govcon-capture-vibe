# Copilot Instructions for GovCon-Capture-Vibe

## ⚠️ CRITICAL RULE: Never Commit Without A Proper Commit Message

**MANDATORY**: Before running `git commit`, you MUST:

1. Prepare the commit message following Conventional Commits format

---

## Project Overview

**Ontology-based RAG system** for federal RFP analysis. Uses a **LightRAG-first native multimodal pipeline** (parser routing + MinerU + native KG/queries) with **xAI Grok** cloud processing. RAG-Anything remains a temporary compatibility dependency until issue #173 removes the legacy surface.

**Core Innovation**: 33 government contracting entity types + 35 canonical relationship types + 3 active relationship inference algorithms (L↔M linking, document structure, orphan resolution) enable Section L↔M mapping, requirement traceability, and Shipley methodology compliance.

### Supporting Documentation

- `README.md` - Repo overview, setup, and active backlog
- `docs/README.md` - Current documentation index
- `docs/STYLE_GUIDE.md` - UI styling rules and frontend constraints
- `docs/SKILLS.md` - Dual-use Agent Skills platform overview
- `docs/SKILL_SPEC_COMPLIANCE.md` - Skill spec audit and migration notes
- `docs/SKILL_TAXONOMY.md` - Closed-vocabulary skill taxonomy

### Root Folders

- `src/` - Python source code organized by domain
- `prompts/` - LLM prompt templates for extraction, multimodal analysis, query response, and inference
- `tools/` - Neo4j workspace management and validation utilities
- `docs/` - Architecture documentation and feature roadmaps
- `inputs/` - RFP document staging (uploaded/ and **enqueued**/ subdirs)
- `rag_storage/` - Per-workspace knowledge graph data (GraphML + embeddings)

---

## ⚠️ CRITICAL: Prompt Coherence & Cross-Cutting Change Rules

### The Three Prompt Systems

This project has **three independent prompt systems** that MUST stay aligned. Changes to the domain ontology, entity types, relationship types, or Shipley methodology MUST propagate across ALL three:

| System                         | Purpose                                         | Files                                                                                    | Registration                                                                |
| ------------------------------ | ----------------------------------------------- | ---------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| **1. LightRAG Extraction**     | Entity/relationship extraction from text chunks | `prompts/govcon_prompt.py` → `_build_v8_system_prompt()`                                 | `PROMPTS.update(GOVCON_PROMPTS)` in `src/server/initialization.py`          |
| **2. LightRAG Query/Response** | RAG query answering (Shipley mentor persona)    | `prompts/govcon_prompt.py` (`rag_response`, `naive_rag_response`, `keywords_extraction`) | Same `PROMPTS.update()` call                                                |
| **3. LightRAG Native Multimodal** | Table/image/equation VLM analysis             | `prompts/multimodal/govcon_multimodal_prompts.py`                                        | `MULTIMODAL_PROMPTS.update(...)` in `src/server/native_lightrag_runtime.py`  |

**Additionally**, post-processing inference prompts live in `prompts/relationship_inference/` (13 algorithm-specific markdown files used by `src/inference/` modules).

### Cross-Cutting Change Checklist

**When modifying entity types, relationship types, or domain vocabulary, you MUST audit ALL of the following:**

1. **Entity catalog YAML** (`prompts/extraction/govcon_entity_types.yaml`): single source of truth for the 33-type entity ontology. Updated by editing the YAML — schema's `VALID_ENTITY_TYPES` is derived from it at import time and the extraction prompt's Part D is rendered from it via `{entity_types_guidance}`. Run `pytest tests/ontology` to enforce parity.
2. **Schema** (`src/ontology/schema.py`): `VALID_RELATIONSHIP_TYPES`, Pydantic models. (`VALID_ENTITY_TYPES` is auto-derived from the YAML in #1 — do not hand-edit.)
3. **Extraction prompt** (`prompts/govcon_prompt.py` → `_build_v8_system_prompt()`): Part E relationship guidance (built from `render_relationship_types_guidance()`), Part F output contract. (Part D entity types are a `{entity_types_guidance}` placeholder rendered from the YAML — do not paste a static catalog back in.)
4. **Multimodal prompts** (`prompts/multimodal/govcon_multimodal_prompts.py`): System prompts, processing prompts, query prompts — must reference correct entity type names and canonical relationship types
5. **Query/response prompts** (`prompts/govcon_prompt.py`): `rag_response`, `naive_rag_response` — Shipley mentor framework must reference current entity vocabulary
6. **Inference prompts** (`prompts/relationship_inference/*.md`): Algorithm-specific prompts that reference entity/relationship types
7. **Test fixtures** (`tools/test_query_prompt.py`, `tests/`): Signal detection patterns, expected entity types, relationship type assertions
8. **VDB sync** (`src/inference/vdb_sync.py`): Normalization logic for relationship types
9. **Skill taxonomy** (`docs/SKILL_TAXONOMY.md` + every `.github/skills/*/SKILL.md`): When the persona vocabulary in the extraction prompt's `USER PERSONAS YOU SUPPORT` block changes (add / remove / rename a persona), update `docs/SKILL_TAXONOMY.md` § "Persona Vocabulary" AND audit `metadata.personas_primary` / `metadata.personas_secondary` across every SKILL.md frontmatter. The persona ID set, the Shipley-phase set, and the capability-verb set are all closed vocabularies — `tests/skills/test_skill_taxonomy.py` will fail any drift.

**Rule: No PR that changes entity types, relationship types, Shipley methodology, or skill personas should be committed without confirming all 9 areas above are aligned.**

### Domain Vocabulary Reference

- **Entity types (catalog-driven)**: Defined in `prompts/extraction/govcon_entity_types.yaml` — re-exported as `src/ontology/schema.py` → `VALID_ENTITY_TYPES` and rendered into the extraction prompt as `{entity_types_guidance}`
- **Relationship types (canonical)**: Defined in `src/ontology/schema.py` → `VALID_RELATIONSHIP_TYPES`
- **Shipley methodology**: Discriminators, win themes, hot buttons, proof points, FAB chains, ghost language, compliance matrix — defined in extraction prompt Part D (rendered from the entity catalog YAML) and query prompt `rag_response`

---

## Architecture & LightRAG Integration

This project extends **LightRAG** directly with government-contracting prompts, role routing, parser routing, and semantic post-processing. RAG-Anything-specific code is legacy compatibility only until the removal epic lands.

### Core Components (`src/`)

- `src/raganything_server.py` - **Main Entry Point**. Orchestrates the LightRAG-first Capture Workbench server and routes.
- `src/server/` - Server configuration and routing
  - `config.py` - LightRAG `global_args` setup (MUST load .env first)
  - `routes.py` - Custom endpoints with batch completion detection
  - `native_lightrag_runtime.py` - Direct LightRAG runtime, role registry, parser health, native multimodal prompt registration
  - `initialization.py` - Legacy compatibility helpers retained until issue #173
- `src/inference/` - Semantic post-processing (3 inference algorithms: L↔M links, document structure, orphan resolution)
- `src/ontology/` - Domain schema validation (Pydantic models for catalog-driven entity types and canonical relationship types)
- `src/extraction/` - Custom entity extraction logic

### Processing Pipeline

1. **Document Upload** → `/insert` or `/documents/upload` endpoints
2. **Native LightRAG Parser Routing** → `LIGHTRAG_PARSER` selects MinerU/native/fallback engines by suffix
3. **Multimodal Analysis** → Tables/images/equations analyzed by VLM using **System 3** prompts (entity-type-aware, Shipley-aligned)
4. **LightRAG Chunking** → Configurable tokens/chunk (set via CHUNK_SIZE in .env), 15% overlap
5. **Entity Extraction** → 33 govcon entity types via xAI Grok + Pydantic validation using **System 1** prompts
6. **Relationship Extraction** → 35 canonical relationship types with typed schema validation
7. **Semantic Post-Processing** → 6-phase pipeline (auto-triggered after batch) using inference prompts
   - Phase 1: Data Loading
   - Phase 2: Entity Normalization
   - Phase 3: Relationship Normalization (entity-pair retyping)
   - Phase 4: Relationship Inference (L↔M links, document structure, orphan resolution)
   - Phase 5: Workload Enrichment (optional)
   - Phase 6: VDB Synchronization
8. **Query Response** → Shipley mentor persona via **System 2** prompts

### Native LightRAG Multimodal & MinerU Integration

Theseus uses LightRAG's native parser pipeline and `lightrag.prompt_multimodal.MULTIMODAL_PROMPTS`, with MinerU as the primary OCR/layout parser for PDFs and OCR-heavy Office files. XLSX/XLSM workbooks are handled by Theseus's native workbook text adapter before LightRAG raw ingestion because MinerU local API does not support XLSX.

- **Multimodal Support**: Handles text, images, tables, and equations through LightRAG native multimodal prompts.
- **Parser Routing**: Controlled by `LIGHTRAG_PARSER` (for example `pdf:mineru-ite,docx:native-ite,xls*:native`). Options: `i` image VLM, `t` table VLM, `e` equation VLM.
- **MinerU Mode**: `MINERU_API_MODE=local` requires `MINERU_LOCAL_ENDPOINT`; `official` requires `MINERU_API_TOKEN`.
- **Vision Model**: Uses the LightRAG `vlm` role from `src/server/llm_routing.py`.
- **Multimodal Prompts**: `prompts/multimodal/govcon_multimodal_prompts.py` provides entity-type-aware, Shipley-aligned native prompts for table/image/equation analysis.

#### Context-Aware Processing

Native LightRAG parser output and surrounding page text provide context for tables/images. This enables:

- **Section Awareness**: Tables know they belong to "Appendix H - Workload Data"
- **CHILD_OF Relationships**: Algorithm 7 can infer parent section relationships
- **Better Embeddings**: VDB captures section semantics, not just isolated content

**Configuration (.env)**:

```bash
LIGHTRAG_PARSER=pdf:mineru-ite,doc:mineru-ite,docx:native-ite,ppt*:mineru-ite,xls*:native
VLM_PROCESS_ENABLE=true
MINERU_API_MODE=local
MINERU_LOCAL_ENDPOINT=http://localhost:8888
MINERU_LOCAL_BACKEND=pipeline
MINERU_LOCAL_PARSE_METHOD=auto
```

---

## ⚠️ Agent Skills — Open Spec Compliance

Theseus implements the open [Agent Skills specification](https://agentskills.io/specification) (originated by Anthropic, adopted by Claude Code, Cursor, Copilot, Junie, Roo Code, Goose, Amp). Skills live under `.github/skills/<name>/` and are discovered/invoked by `src/skills/manager.py`.

**Authoritative audit + migration plan:** [docs/SKILL_SPEC_COMPLIANCE.md](../docs/SKILL_SPEC_COMPLIANCE.md). Read it before modifying any skill or the runtime.

**Foundational meta-skill:** [.github/skills/skill-creator/](../.github/skills/skill-creator/) — vendored from `anthropics/skills` (Apache-2.0). Use it to author/refine/evaluate every other skill. See its [UPSTREAM.md](../.github/skills/skill-creator/UPSTREAM.md) for re-vendor instructions and the Claude.ai-specific runtime adaptation (Theseus is single-process; upstream assumes Claude Code parallel subagents).

### 🔒 MANDATE — `skill-creator` is required for every skill change

**There is no path to creating, rewriting, promoting, or materially improving a skill that bypasses `skill-creator`.** This is non-negotiable, applies to the agent and any subagent, and supersedes any "I'll just edit the file directly" instinct.

**You MUST load `skill-creator` (read its `SKILL.md`) and follow its workflow when:**

- Creating a new skill from scratch (any folder under `.github/skills/<new-name>/`)
- Promoting a placeholder/stub skill to a real implementation (e.g., wiring an MCP, adding tools-mode runtime)
- Rewriting a skill's frontmatter, body, references, assets, or evals
- Optimizing a skill's `description` for trigger accuracy
- Adding/removing `metadata.mcps`, `metadata.script_paths`, or `metadata.runtime`
- Running benchmarks/evals against a skill or comparing against a baseline

**Permitted without invoking `skill-creator` (small, surgical, no behavioral change):**

- Typo / mojibake / formatting-only fixes inside an existing SKILL.md or reference file
- Bumping `metadata.version` to match an already-completed change
- Renaming an internal artifact path that doesn't change the skill's contract
- Adding a contract test under `tests/skills/` (those live outside `.github/skills/`)

**The `skill-creator` workflow you MUST follow** (anchored in [Anthropic's authoring best-practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)):

1. **Snapshot first.** Copy the existing skill (if any) to `tools/_skill_snapshots/<skill-name>-pre-<phase>/` (gitignored) so you can diff and roll back.
2. **Build evals BEFORE prose.** Write/refresh `evals/evals.json` with ≥3 realistic prompts that capture the gaps you intend to close. Evals are the source of truth — not your intuition.
3. **Establish the baseline.** Note how the current skill (or no skill) performs against those prompts.
4. **Draft minimally.** Write only enough SKILL.md to close the gap. Honor the spec: 6-field frontmatter, body <500 lines, workflow-as-numbered-checklist, references one level deep, `assets/` not `templates/`, gerund naming, third-person "pushy" description with both WHAT + WHEN, no time-sensitive language, consistent terminology, no Windows backslashes in paths inside the skill.
5. **Match degrees of freedom to fragility.** High-freedom prose for judgment-heavy steps; low-freedom "run exactly this script" for fragile ones. Avoid offering multiple options where one default + escape hatch will do.
6. **Iterate observe→refine→test.** Run the evals (or at minimum a live smoke-test invocation through `SkillManager.invoke(...)`), watch what the model actually does, bring observations back, refine. Do not declare "done" without at least one real run.
7. **Honor progressive disclosure.** Push large reference material into `references/*.md` so it loads on demand, not into the SKILL.md body.
8. **Cite Anthropic best-practices** in your commit/PR description when you make a non-trivial authoring decision (e.g., "moved tool reference table to `references/data_sources.md` per progressive-disclosure pattern").

**Enforcement at commit time:** Before proposing any commit that touches `.github/skills/<skill>/SKILL.md`, `evals/evals.json`, `references/`, or `assets/`, you must affirm in the commit message body (or the chat turn proposing it) that `skill-creator` was loaded and its workflow was followed. If it wasn't, stop, load `skill-creator`, redo the work, then commit.

**Rule:** No PR that creates or materially changes a skill should be committed without (a) `skill-creator` having been loaded for that turn, (b) an updated `evals/evals.json`, and (c) at least one observed run (smoke test or full eval pass).

### Spec rules (the only ones that matter)

1. **Frontmatter — six allowed fields only:** `name` (required, max 64 chars, lowercase + hyphens, no `anthropic`/`claude`), `description` (required, max 1024 chars, third-person, "pushy" with both **what** + **when**), `license`, `compatibility`, `metadata` (escape hatch for custom keys), `allowed-tools` (experimental). **Anything else at the top level is non-conformant — move it under `metadata:`.**
2. **Directory layout:** `SKILL.md` (required, body <500 lines), `scripts/` (executed via `run_script` tool, NOT loaded into context), `references/` (loaded on demand, one level deep), `assets/` (templates/icons/fonts used in output — **NOT `templates/`**), `evals/evals.json` (test prompts).
3. **Workflow lives in the SKILL.md body** as a numbered Markdown checklist invoking tools — **never** as a custom YAML field. The runtime gives the model tools and lets the body drive.
4. **Naming:** gerund preferred (`processing-pdfs`), noun phrases acceptable. Avoid `helper`, `utils`, `tools`, `documents`.
5. **Progressive disclosure:** metadata (~100 tokens, always loaded) → SKILL.md body (loaded on activation) → bundled resources (loaded only when the body references them).

### Theseus runtime architecture (Option B — tools-fetch model)

Skills run as **multi-turn tool-calling agents**, not single-shot prompt dumps. The `SkillManager` exposes a small tool registry to the LLM:

| Tool                                | Purpose                                                       | Backed by                            |
| ----------------------------------- | ------------------------------------------------------------- | ------------------------------------ |
| `read_file(path)`                   | Read `references/`, `assets/`, `scripts/` as text (read-only) | filesystem                           |
| `run_script(path, stdin?, timeout)` | Execute `scripts/*.py`/`*.sh` in subprocess sandbox           | subprocess (cwd locked to skill dir) |
| `write_file(path, content)`         | Persist artifacts (confined to `<run_dir>/artifacts/`)        | filesystem (sandboxed)               |
| `kg_query(cypher)`                  | Deterministic structural queries against active workspace KG  | Neo4j client                         |
| `kg_entities(types[], limit)`       | Typed entity slicing                                          | existing `_slice_entities` logic     |
| `kg_chunks(query, top_k, mode)`     | Chat-grade hybrid retrieval (Phase 1.6)                       | `aquery_data(...)` pipeline          |

Every tool call is captured in `<run_dir>/transcript.json` for grounding audit. **The skill body is the contract; the transcript is the proof.** This mirrors how a human analyst works: read the assignment → query the KG → fetch supporting chunks → run scripts → write the draft → cite sources.

### Skill Chain Contracts — Required Review

Theseus also maintains machine-readable skill handoff contracts for dynamic skill chaining in `src/skills/chain_contracts.py`. A skill contract is the planner-facing interface promise for a skill: accepted upstream semantic products, produced semantic products, artifact extensions, downstream-compatible skills, planner keywords, phase rank, role, and quality gate.

**Any time a skill is added, imported from GitHub / skills.sh, removed, renamed, split, decomposed, merged, or materially changed, you MUST review the chain contract surface:**

1. Update or add the skill's `SkillChainContract` in `src/skills/chain_contracts.py` if it can participate in chains.
2. Keep `accepts`, `produces`, `artifact_extensions`, `downstream_skills`, `role`, and `quality_gate` aligned with the actual SKILL.md workflow and emitted artifacts.
3. Avoid broad planner keywords like `win`, `data`, or `analysis` unless the skill truly owns that intent; ambiguous terms cause noisy chains.
4. Update planner tests in `tests/skills/test_skill_chain_planner.py` for new handoff edges, decomposition changes, or expected chain shape changes.
5. If the skill should not chain, confirm no contract is needed and that the planner still handles it only as a direct fallback when appropriate.

**Rule:** No PR or commit that creates, imports, decomposes, or materially changes a skill should be proposed without explicitly stating whether the chain contract was added, updated, or intentionally left absent.

### Cross-cutting rules for ANY skill change

When modifying a skill or the runtime, you MUST:

1. **`skill-creator` loaded:** For any non-trivial skill change (see MANDATE above), affirm `skill-creator/SKILL.md` was read this turn and its workflow followed. Trivial fixes (typos, mojibake, version bumps) are exempt.
2. **Frontmatter audit:** Verify only the 6 spec fields at top level. Move `version`, `category`, `status`, `authoritative_source`, `upstream`, etc. under `metadata:`.
3. **Directory naming:** If the skill has a `templates/` folder, it must be renamed to `assets/` (and `Skill.has_templates` references in `manager.py` updated to `has_assets`).
4. **Body length:** Stay under 500 lines. Move long content into `references/*.md`.
5. **Workflow as checklist:** Body must contain an explicit numbered checklist invoking the tools above. No implicit "use the briefing book" assumptions.
6. **`evals/evals.json` present:** Every skill needs at least 3 test prompts using the schema in `.github/skills/skill-creator/references/schemas.md`.
7. **UTF-8 only:** Save SKILL.md as UTF-8 (no BOM round-trip through Windows-1252). PowerShell: `Out-File -Encoding utf8`. Watch for mojibake (`â€"`, `â†'`, `â†"`) in existing files.
8. **Spec portability:** The same SKILL.md must run unmodified in Claude Code, Cursor, Copilot. Theseus-specific behavior goes under `metadata:` — never as new top-level YAML keys.
9. **Audit doc updated:** If you discover a new gap or close one, update `docs/SKILL_SPEC_COMPLIANCE.md` in the same commit.

**Rule:** No PR that touches `.github/skills/` or `src/skills/` should be committed without confirming all 9 areas above.

### Sub-phase migration state (current)

| Sub-phase | Scope                                                        | State      |
| --------- | ------------------------------------------------------------ | ---------- |
| 2.0       | Vendor skill-creator + audit doc                             | ✅ Done    |
| 2.1       | Tool-calling runtime in `src/skills/manager.py`              | ⏳ Pending |
| 2.2       | Migrate `proposal-generator` end-to-end (proves the pattern) | ⏳ Pending |
| 2.3       | Migrate remaining 4 skills + UI transcript drawer            | ⏳ Pending |

---

## Architecture Philosophy — Improve Codebase Architecture

Follow Matt Pocock's `improve-codebase-architecture` philosophy in all build, bugfix, refactor, and review work. Always prefer simple, deep structures over shallow wrappers, pass-through modules, or feature-shaped bloat.

### Exact vocabulary

- **Module** — anything with an interface and an implementation (function, class, file, folder, or vertical slice)
- **Interface** — everything a caller must know to use a module correctly (types, rules, error cases, ordering, config)
- **Depth** — how much useful behavior sits behind a small, simple interface
- **Deep module** — high leverage + high locality behind a small interface
- **Shallow module** — interface almost as complicated as the code inside it
- **Seam** — the place where behavior can be swapped without editing the calling code
- **Adapter** — a concrete thing that fills a seam
- **Leverage** — what callers gain from depth
- **Locality** — what maintainers gain from depth

### Daily mindset

- Hunt shallow modules, duplicated logic, and places where understanding one concept requires hopping between many small files.
- Favor deep modules: small interface, deep implementation, high leverage, high locality.
- Prefer deletion, consolidation, or deepening over new wrappers, helper layers, or adapter soup.
- Always seek opportunities to uncomplicate the codebase when found.
- Use the project's ubiquitous language when naming code or explaining changes: the govcon ontology, canonical relationship types, and Shipley terms are the default vocabulary.

### Presenting structural changes

When surfacing a non-trivial structural change:

1. State the problem plainly.
2. Describe the solution in plain English.
3. Explain benefits in terms of leverage, locality, and testability.
4. Ask which candidate the user wants to explore next before proposing full interfaces.

---

## Development Guidelines

### Coding Style & Conventions

- **Python**: Follow PEP 8. Use 4-space indentation.
- **Logging**: Use `logging.getLogger(__name__)` or `lightrag.utils.logger`. **Avoid `print`**.
- **State Modeling**: Use `dataclasses` or Pydantic models.
- **Type Hinting**: Annotate functions and variables.
- **Imports**:
  - **CRITICAL**: Load `.env` (`load_dotenv()`) **BEFORE** importing any LightRAG modules. LightRAG evaluates defaults (like `CHUNK_SIZE`) at import time.
  - **Pattern**:

    ```python
    from dotenv import load_dotenv
    load_dotenv()  # MUST BE FIRST

    from lightrag import LightRAG
    from lightrag.api.config import global_args
    ```

### Agent Workflow & Best Practices

- **Search**: Use `rg` (grep_search) for fast text search. Use `file_search` for file names.
- **Paths**: Use repo-relative paths for all commands.
- **Modifications**: Honor existing local modifications. Never revert user changes without explicit instruction.
- **Planning**: For non-trivial work, create a multi-step plan.
- **Validation**: Always validate changes by running relevant tests (`pytest` or specific scripts).
- **Simplification**: Prefer deleting or deepening code over adding abstractions. If you find a way to uncomplicate the codebase without widening scope, take it.
- **Cross-cutting awareness**: Before completing any feature branch, review the Cross-Cutting Change Checklist above if the change touches ontology, prompts, or domain vocabulary.

### Frontend / UI (Alpine + Tailwind CDN, external CSS)

**Read [docs/STYLE_GUIDE.md](../docs/STYLE_GUIDE.md) before making any UI changes.**

- **Two files**: `src/ui/static/index.html` (markup + Alpine `theseus()` component + inline `tailwind.config`) and `src/ui/static/styles/theseus.css` (all custom CSS — `:root` token block + components). **No build step**, no inline `<style>` block.
- **CRITICAL — Tailwind Play CDN does NOT process `@apply` in `theseus.css`.** `@apply` only resolves inside an inline `<style>` block in HTML, which we no longer have. Writing `@apply` in `theseus.css` produces silent style failures. Always use raw CSS with the `var(--*)` token references defined in `:root`.
- **Token system**: All colors live as CSS custom properties in `theseus.css` (`--neon-cyan`, `--ink-900`, `--edge-strong`, `--text-300`, etc.). For transparency, use the matching `--*-rgb` triplet inside `rgba()`: `rgba(var(--neon-cyan-rgb), 0.4)`. Do NOT add new hex literals for color variants — use the triplet + alpha.
- **Tailwind config is duplicated**: the runtime config lives inline as `tailwind.config = {…}` in a `<script>` tag at the top of `index.html` (read by the CDN in the browser); the IDE-only mirror lives at `tailwind.config.js` (read by the VS Code Tailwind IntelliSense extension). **If you change one, mirror the other** — custom tokens (`neon-*`, `ink-*`, `edge-*`, `shadow-glow`, `shadow-magenta`) must match in both files. New CSS tokens added to `:root` should also be mirrored here if they need a Tailwind utility.
- **No server restart for UI changes** — hard-reload the browser (Ctrl+Shift+R) since `index.html` and `theseus.css` are served via `StaticFiles`.
- **Alpine state lives on `theseus()`**: workspace name is `this.stats.workspace` (NOT `activeWorkspace`); chat messages are `this.currentChat.messages[]`; toasts via `this.toast(msg, kind)`; scroll target is `this.$refs.msgs`.
- **Re-render Lucide icons after dynamic markup**: existing `$watch` hooks on `currentChat`, `palette.open`, `wsModal.open`, etc. call `lucide.createIcons()` — add a watcher when introducing a new modal/overlay.
- **UTF-8 only**: Save files as UTF-8 (no BOM round-trip through Windows-1252). If you see `Â·`, `â†'`, `â€"` etc. in the rendered UI, that's mojibake — repair targeted patterns before committing. PowerShell: always use `Out-File -Encoding utf8`.

---

## Testing & Validation

**MANDATORY**: Always run tests from the project `.venv` (managed by `uv`).

### Dependency Management (uv, not pip)

- This project uses **uv** to manage `.venv`. The venv intentionally has **no `pip`** — all installs go through `uv` so they're reflected in `pyproject.toml` + `uv.lock`.
- **NEVER** run `pip install <pkg>` (it will fail or leak into another Python). If a tool is missing from `.venv`, declare it in `pyproject.toml` and run `uv sync`.
  - Runtime dep: `uv add <pkg>`
  - Dev/test dep: `uv add --dev <pkg>` (lands in `[dependency-groups] dev`, installed by `uv sync` by default)
- After any `uv sync`, verify CUDA torch survived: `python -c "import torch; print(torch.cuda.is_available())"`. The `[tool.uv.sources]` block pins torch/torchvision to the `pytorch-cu124` index so resyncs should preserve GPU builds, but a CPU downgrade has happened historically.

### Running Tests

1.  **Quick Validation Scripts**:
    - Refer to `tests/TEST_SCRIPTS_README.md` for specific scenarios.
    - Example: `.\.venv\Scripts\python.exe tests/test_neo4j_quick.py`
2.  **Full Suite**:
    - `.\.venv\Scripts\python.exe -m pytest tests` (pytest is declared in `[dependency-groups] dev`).
    - Use markers if available (check `tests/pytest.ini` if present).
3.  **Prompt Signal Tests**:
    - `.\.venv\Scripts\python.exe tools/test_query_prompt.py --workspace <name> --query-id M2` — Tests mentor persona signal detection
    - Signal categories: `shipley_terms`, `mentoring_language`, `risk_flags`, `reasoning_chain`
    - Note: Tests query against cached LLM responses. Re-process workspace under new prompts for fresh results.
4.  **Native Ingestion Regression Gate**:
  - `.\.venv\Scripts\python.exe tools/native_ingestion_regression_gate.py --fixture --json` — no-GPU/no-MinerU smoke for native pipeline capabilities, parser routing, multimodal prompt contracts, fixture entity/relationship counts, multimodal evidence, and known-answer checks.
  - Full local check: `.\.venv\Scripts\python.exe tools/native_ingestion_regression_gate.py --workspace rag_storage/<workspace> --known-answer-file tools/native_known_answers.example.json --require-multimodal --output run-dir/artifacts/native-ingestion-gate.json` after reprocessing a representative workspace.
  - Run the fixture gate before touching native ingestion, parser routing, multimodal prompts, strict-schema boundaries, or LightRAG pins. See `docs/NATIVE_INGESTION_REGRESSION_GATE.md`.

### Environment Setup

- Monitor terminal prompt for `(.venv)` indicator, or invoke `.\.venv\Scripts\python.exe` directly.
- Ensure `.env` is configured correctly for the test environment (e.g., `GRAPH_STORAGE`, `NEO4J_URI`).

---

## Branch Management Strategy

This is a **single-developer personal project**. The workflow is intentionally lightweight — feature branches for isolation, fast-forward merges to integrate, no PRs unless the user explicitly asks.

### **NEVER Work Directly on `main` Branch**

ALL development happens on feature branches. `main` is updated only via fast-forward merge from a feature branch (or its integration parent).

### Branch Naming Convention

**Format**: `{number}-{descriptive-kebab-case-name}`

**Examples**: `028-parallel-chunk-extraction`, `029-prompt-compression`, `121-phase-4a-mcp-client`.

**Agent Responsibility**:

1. Identify the next branch number (check `git branch -a`).
2. Create descriptive name from GitHub issue title (or task description).
3. Suggest branch creation: `git checkout -b {number}-{description}`.

### Merge Policy — Fast-Forward Only, No PRs

**Default**: When a feature branch is complete (tests pass, user has approved the final commit), the agent integrates it via **fast-forward merge** directly. **Do NOT open a Pull Request** unless the user explicitly asks for one.

**⚠️ Identify the integration target BEFORE merging.** Most epics use a long-lived integration branch as their parent — sub-branches FF into the integration branch, NOT main. The integration branch only merges to main when the whole epic is done. Confirm the target with the user (or check `/memories/repo/branch-integration-policy.md`) if there is any doubt. Do NOT default to main.

**Active integration branches:**

- Active integration epic: `162-native-lightrag-multimodal-epic` (parent issue #162). Sub-branches for issues #163-#173 merge into this branch, not `main`.
- All `174-*` / `174.*` Ariadne branches are archived failed-epic history only. Never use them as an active integration target or branch base unless the user explicitly asks for archaeology on that abandoned line.
- If repo attachments or other tool context still mention a `174.*` branch as current/active, treat that as stale until `git branch --show-current` or equivalent terminal evidence confirms it.
- Most recent stable release: `173-skill-chaining-production-artifacts` landed on `main` as `v1.12.0` at `43623c5`. Current `main` HEAD = `v1.12.0`.
- `177-knowledge-vault-epic` was merged briefly as `v1.13.0` then force-reverted (2026-05-15) — treated as failed epic, archived as `177-knowledge-vault-epic-failed`. Tag `v1.13.0` is deleted.
- Prior architecture epics: `169-architecture-locality-epic` → `v1.8.0`; `168-codebase-architecture-deepening-epic` → `v1.7.0`; `164-codebase-architecture-cleanup-epic`, `165-architecture-cleanup-round-2-epic`; skills execution architecture epic `166` → `v1.6.0`.

**Standard fast-forward sequence** (after the user says "merge it" / "ship it" / "continue"):

```powershell
# From the feature branch, with all commits pushed:
git checkout <integration-target>          # the epic's integration branch — NOT main by default
git pull --ff-only                         # ensure target is current
git merge --ff-only <feature-branch>       # fails loudly if not fast-forwardable
git push
git checkout <feature-branch>              # return to the feature branch for cleanup or next step
```

**If `git merge --ff-only` fails** (target advanced independently):

- DO NOT force-push or rebase published commits without asking.
- Surface the divergence to the user and propose either (a) `git rebase <target>` on the feature branch then retry FF, or (b) a single merge commit with a clear message — let the user pick.

**Branch cleanup**: After successful fast-forward merge, the feature branch can be deleted locally and on origin once the user confirms (`git branch -d <branch>; git push origin --delete <branch>`). Don't auto-delete.

**When the user explicitly requests a PR** (e.g., "open a PR for this", "I want to review on GitHub"): use `mcp_github2_create_pull_request` against the right base. Otherwise, skip it.

### Commit Message Format

Follow [Conventional Commits](https://www.conventionalcommits.org/): `type(scope): description`

- **Types**: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`
- **Scope**: `extraction`, `inference`, `neo4j`, `prompts`, `agents`, `multimodal`, `ontology`, `skills`, `deps`

### Pre-Commit Checklist

Before proposing a commit, verify:

1. **Cross-system alignment**: If the change touches entity types, relationship types, or Shipley methodology, have all 3 prompt systems been audited? (See Cross-Cutting Change Checklist)
2. **Schema consistency**: Do `VALID_ENTITY_TYPES` and `VALID_RELATIONSHIP_TYPES` in `schema.py` match what the prompts reference?
3. **Test fixtures updated**: Do test signal patterns and assertions reflect the current vocabulary?
4. **Version bumped**: If extraction prompt changed, is the version number in the prompt header updated?
5. **Tests pass from `.venv`**: `.\.venv\Scripts\python.exe -m pytest <relevant tests>` succeeds.

---

## Configuration (.env)

```bash
# LLM - xAI Grok (OpenAI-compatible API)
LLM_BINDING_HOST=https://api.x.ai/v1
LLM_MODEL=grok-4.20-0309-reasoning
LLM_BINDING_API_KEY=xai-xxx

# Embeddings - OpenAI (MUST use OpenAI endpoint, not xAI)
EMBEDDING_BINDING_HOST=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-large
EMBEDDING_BINDING_API_KEY=sk-proj-xxx

# Storage
GRAPH_STORAGE=Neo4JStorage  # or NetworkXStorage
WORKING_DIR=./rag_storage/workspace_name

# Batch processing
BATCH_TIMEOUT_SECONDS=30

# Native LightRAG parser routing
LIGHTRAG_PARSER=pdf:mineru-ite,doc:mineru-ite,docx:native-ite,ppt*:mineru-ite,xls*:native
VLM_PROCESS_ENABLE=true
MINERU_API_MODE=local
MINERU_LOCAL_ENDPOINT=http://localhost:8888
```

---

## Common Patterns

### Batch Document Upload

The `DocumentQueueTracker` in `src/server/routes.py` auto-detects batch completion. Uploads register via `register_request_start()`.

### Custom Endpoint Override

Routes override LightRAG defaults in `src/raganything_server.py`.

### File Operations

Use workspace tools (`read_file`, `create_file`, `replace_string_in_file`), NOT PowerShell for file I/O.

### GPU Warning

After `uv sync`, PyTorch might downgrade to CPU-only. Reinstall CUDA versions manually if needed (see `README.md` or previous instructions).

## graphify

Use Graphify as the first-pass map for repo-scale work so chats spend fewer tokens rediscovering the codebase.

- Before answering architecture, dependency, debugging, refactor, feature-planning, or "where does X live?" questions, read `graphify-out/GRAPH_REPORT.md` if it exists.
- For broad questions, run `graphify query "<question>" --budget 1500` before wide workspace searches, then open only the files or wiki pages that the graph points to.
- For known symbols or systems, prefer `graphify explain "<node>"` to get the node neighborhood before reading source files.
- For integration questions between two concepts, prefer `graphify path "A" "B"` before manual grep/semantic search.
- If `graphify-out/wiki/index.md` exists, navigate the wiki for deeper architecture context and community pages.
- Do not use Graphify for tiny known-file edits, simple terminal requests, or cases where the relevant file is already open and obvious.
- Type `/graphify . --wiki` in Copilot Chat to rebuild the full graph. Use `graphify update .` after code-only changes when semantic re-extraction is not needed.
