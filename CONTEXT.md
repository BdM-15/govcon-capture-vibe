# Theseus

Ontology-backed RAG system that ingests federal RFPs into a knowledge graph and answers govcon capture questions through a Shipley-methodology mentor persona.

## Language

### Core system concepts

**Workspace**:
An isolated knowledge graph + vector database for exactly one RFP. Lives at `rag_storage/<name>/`. All entities, relationships, and embeddings are workspace-scoped. Created manually: user names the workspace, switches to it via the UI, then uploads documents through the Documents page. Not auto-created on first upload.

`rag_storage/<name>/` layout (traced from live workspace):

- `graph_chunk_entity_relation.graphml` — GraphML snapshot; legacy file, KG lives in Neo4j
- `vdb_entities.json`, `vdb_relationships.json`, `vdb_chunks.json` — LightRAG VDB embedding stores
- `kv_store_doc_status.json` — primary doc lifecycle store. Keys = `doc-<hash>`. Each record: `status` (PENDING → PROCESSING → PREPROCESSED → PROCESSED | FAILED), `chunks_count`, `chunks_list`, `content_summary`, `content_length`, `created_at`, `updated_at`, `file_path`, `track_id`, `metadata` (timing, engine). First file to check for "doc processed but missing from KG". RAG-Anything writes extra fields (`multimodal_processed`, `multimodal_content`, `scheme_name`) and non-standard status strings ("handling" → PROCESSING, "parsing" → PROCESSING, "ready" → PENDING) — stripped/remapped by `apply_doc_status_compatibility_shim()` in `src/server/doc_status_compat.py` before any LightRAG KV write. Timestamps stored as local ISO strings (converted from UTC by `to_local_iso()`). `DocStatus.PREPROCESSED` = MinerU parse done, extraction not yet started (LightRAG internal state — rarely visible in UI).
- `kv_store_text_chunks.json`, `kv_store_full_docs.json`, `kv_store_entity_chunks.json`, `kv_store_full_entities.json`, `kv_store_full_relations.json`, `kv_store_relation_chunks.json` — LightRAG chunk/entity/relation KV stores
- `kv_store_llm_response_cache.json`, `kv_store_parse_cache.json` — LLM + parse caches (safe to delete to force reprocessing)
- `.ontology_bootstrap` — bootstrap marker; present = skip bootstrap on next startup
- `<name>_errors.log`, `<name>_processing.log` — per-workspace ingest logs
- `chats/` — persisted chat history for this workspace
- `pursuits/` — capture pursuit artifacts (skill outputs)
- `mineru/` — MinerU parse cache (intermediate PDF extraction results)
- `skill_runs/<skill>/<timestamp>/` — per-invocation skill run directories

_Avoid_: project, environment, instance.

**Knowledge graph (KG)**:
The graph database holding all entities and relationships for a workspace. Backed by Neo4j when `GRAPH_STORAGE=Neo4JStorage` (production default). Accessed via `src/core/neo4j_io.py`. The semantic post-processor reads from and writes to this graph. Skills query it via the `kg_query(cypher)` and `kg_entities(types[])` tools.
_Avoid_: "the graph" alone (ambiguous between the KG and GraphML files on disk).

**VDB (vector database)**:
LightRAG's internal embedding stores: `entity_vdb` + `relationships_vdb`. Managed entirely by LightRAG via `ainsert_custom_kg()`. Workspace-scoped — lives under `rag_storage/<name>/` alongside the KG. Powers hybrid retrieval (`kg_chunks` tool). Phase 5 of the semantic post-processor (VDB sync) pushes inference-discovered relationships into it so queries can find them.
_Avoid_: treating VDB and KG as interchangeable — KG = Neo4j graph (structure); VDB = embeddings (retrieval).

**Graph storage** (`GRAPH_STORAGE` env var):
Selects the KG backend. Two options: `Neo4JStorage` (production; requires `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`) and `NetworkXStorage` (config default; in-memory, no Neo4j required; used for local tests / CI where Neo4j is unavailable). When `GRAPH_STORAGE=NetworkXStorage` the inference algorithms and `Neo4jGraphIO` skip Neo4j reads/writes and emit a warning — skills that issue Cypher (`kg_query` tool) will get empty results. Connection details wrapped in `Neo4jConnectionConfig` (`src/core/neo4j_config.py`). `Neo4jConnectionConfig.enabled` property returns `True` only for `Neo4JStorage` — guard used everywhere before issuing Cypher.
_Avoid_: assuming Neo4j is always active; scripts that hard-code `bolt://localhost:7687` without checking `enabled`.

**Neo4jGraphIO** (`src/inference/neo4j_graph_io.py`):
The write/read bridge between the inference algorithms and Neo4j. Instantiated per semantic post-processor run (`SemanticPostProcessingRun._io()`). Opens a direct Neo4j `GraphDatabase.driver` connection from `Settings` at `__init__`; must be closed after the run. Key methods used by the post-processor:

- `get_all_entities()` — `MATCH (n:<workspace>)` → entity dicts (`id`, `entity_name`, `entity_type`, `description`, `source_id`)
- `get_all_relationships()` — `MATCH (a)<-[r]->(b)` → relationship dicts (`source`, `target`, `rel_type`, `keywords`, `weight`, `description`)
- `update_entity_types(updates)` — batch `SET n.entity_type =` for Phase 2 entity normalization
- `update_entity_names(updates)` — batch `SET n.entity_id =` for Phase 2 name canonicalization
- `add_relationships(rels)` — `MERGE`-based upsert for algorithm-discovered edges (Phase 4 output)

Workspace scoping: all Neo4j nodes belonging to a workspace carry a label equal to the workspace name (LightRAG convention). `Neo4jGraphIO` queries always filter by `(n:<workspace_label>)`. Distinct from `Neo4jConnectionConfig` (connection settings only) and `src/core/neo4j_io.py` (lower-level helpers used by workspace management routes).
_Avoid_: calling it "the Neo4j client" (ambiguous — `neo4j_config.py` also has a config class); confusing it with the LightRAG-internal KV stores (separate path, separate format).

**Ingest pipeline**:
The sequence that turns a raw RFP document into graph data: MinerU parse -> content filter/rebalance -> `insert_content_list` (multimodal analysis + LightRAG chunking + entity/relationship extraction) -> batch completion -> semantic post-processing trigger. Entry point: `process_document_with_semantic_inference()` in `src/server/document_processing.py`. This function is passed as `process_document_func` to both upload and scan routes — identical pipeline regardless of trigger.

Steps inside `process_document_with_semantic_inference`: (1) `rag_instance.parse_document()` via MinerU, (2) `filter_discarded_content_blocks()` — drops structural chrome (`discarded`, `header`, `footer`, `page_number`, `aside_text`, `page_footnote`) defined in `DISCARDED_CONTENT_TYPES`; these carry no extractable govcon content, (3) `rebalance_modal_content_blocks()`, (4) `rag_instance.insert_content_list()` — RAG-Anything native end-to-end (multimodal VLM + LightRAG chunking + extraction), (5) callback dispatches `on_document_complete` -> batch timer reset.

**Modal rebalancing** (`rebalance_modal_content_blocks`): Pre-`insert_content_list` normalization step. RAG-Anything sends non-text blocks through a VLM multimodal path. If MinerU already extracted text from a table or list, re-typing it as `text` routes it through the cheaper LightRAG text path instead — avoids double-extraction and over-amplification. Rules: `table` with non-empty body → convert to `[TABLE]...[/TABLE]` text block; `list` → `[LIST]...[/LIST]` text block; `seal` → discard; images/equations → pass through as multimodal. Logged as "Rebalanced modal artifacts" with per-type counts.
_Avoid_: "the pipeline" (ambiguous -- see Flagged ambiguities).

**Semantic post-processor**:
The 5-phase inference pass that runs exactly once after a batch completes. Phases: (1) data loading, (2) entity normalization, (3) relationship normalization, (4) relationship inference, (5) VDB sync. Lives in `src/inference/`. _Note_: a "workload enrichment" phase existed previously but was removed when the ontology gained native `workload_metric` entities — extraction handles that coverage now.

**Trigger mechanism**: `GovConProcessingCallback` (`src/server/processing_callback.py`) tracks in-flight documents. Each `on_document_complete` / `on_document_error` schedules a `asyncio.call_later` timer (`BATCH_TIMEOUT_SECONDS`). Timer fires `_check_batch_complete()`: if `pending_uploads == 0` and `processing_docs == 0` and `enhancement_pending`, it calls `enhance_knowledge_graph()`. New document arriving cancels and resets the timer. Gate: `ENABLE_POST_PROCESSING` env var (default true). No background thread — runs in the server's asyncio event loop.

Two tracking levels: HTTP-layer (`pending_uploads` set, managed by `register_request_start(filename)` / `register_request_end(filename)`) and parse-layer (`processing_docs` set, added on `on_parse_complete`, removed on `on_document_complete`/`on_document_error`). Batch completion requires *both* sets empty. `enhancement_running` flag prevents duplicate concurrent runs. Singleton pattern: `get_processing_callback()` returns `_callback` module-level instance.

Phase 4 runs 3 **inference algorithms** in parallel (`src/inference/algorithms/`): `infer_lm_links` (L↔M cross-document linking), `infer_document_structure` (heuristic regex, zero LLM cost), `resolve_orphans` (reconnect unlinked entities). Algorithms are the mechanisms inside Phase 4; phases are the overarching structure of the whole pass.
_Avoid_: "post-processing pipeline" (pipeline is overloaded -- see Flagged ambiguities). Never conflate phases with algorithms.

**Entity normalization** (Phase 2, `src/inference/semantic_post_process_support.py`):
Four sequential sub-operations applied to Neo4j entities before relationship work:

1. **Type cleanup** (`plan_entity_type_updates()`): Deterministic scan of all entities grouped by `entity_type`. Three patterns caught:
   - `table` type → `heuristic_table_type_mapping()`: keyword match on entity name + description → maps to `proposal_instruction`, `deliverable`, `evaluation_factor`, `performance_standard`, `requirement`, `clause`, etc. (RAG-Anything VLM outputs these as `table` before downstream context is available)
   - `#evaluation_factor` / `|requirement` prefix artifacts → strip `#`/`|` prefix → valid entity type (LightRAG occasionally emits these prefix-polluted strings)
   - `unknown` type → collected for LLM batch retyping (step 2)
2. **UNKNOWN retyping** (`_retype_unknown_entities()`): LLM call via `retype_entities_batch()`, batches of 20. Entities whose description can't map to a valid govcon type stay `unknown`.

3. **Name canonicalization** (`plan_entity_name_updates()`): Targets `evaluation_factor` entities with punctuation-drift duplicates (e.g. `Factor 1 Technical Approach` vs `Factor 1: Technical Approach`). `canonicalize_factor_like_name()` normalises to `Factor <ordinal>: <label>` form. Returns `(name_updates, canonical_mapping)`. Neo4j updated via `Neo4jGraphIO.update_entity_names()`; VDB updated via `apply_entity_name_updates_to_vdb()` — rewrites `entity_name` in `vdb_entities.json` and `src_id`/`tgt_id` in `vdb_relationships.json`.

4. **VDB metadata sync** (`sync_entity_metadata_to_vdb()`): After type cleanup commits, patches `vdb_entities.json` with updated `entity_type`, `source_id`, and `description` from Neo4j without touching embedding vectors. Prevents query-time drift between Neo4j entity types and VDB metadata.

_Avoid_: calling Phase 2 "type fixing" (it also handles name dedup and VDB sync); conflating `apply_entity_name_updates_to_vdb` (name remap) with `sync_entity_metadata_to_vdb` (type/metadata patch).

**Relationship normalization** (Phase 3, `src/inference/semantic_post_process_support.py`):
Retype of generic edges using entity-pair context. `resolve_generic_relationship()` checks if a relationship's `rel_type` is in `GENERIC_REL_TYPES` (currently `{"RELATED_TO"}`); if so, looks up `(source_entity_type, target_entity_type)` in `ENTITY_PAIR_REL_MAP` (50+ pairs) → returns canonical relationship type or keeps original if no match. Examples: `(requirement, deliverable)` → `SATISFIED_BY`; `(evaluation_factor, evaluation_factor)` → `CHILD_OF`; `(requirement, clause)` → `GOVERNED_BY`. Applied in `_normalize_relationships()` — re-writes Neo4j relationship types in-place. Does NOT fire LLM.
_Avoid_: calling this "Phase 4" (Phase 3 is heuristic normalization; Phase 4 is LLM inference algorithms).

**Inference algorithms** (`src/inference/algorithms/`, Phase 4 of the semantic post-processor):
Three algorithms run in parallel via `asyncio.gather` under a shared concurrency semaphore (`MAX_CONCURRENT_LLM_CALLS`):

| Algorithm                  | Function                      | LLM    | Relationship types produced | When it fires                                                                                                                                                                                                                                                  |
| -------------------------- | ----------------------------- | ------ | --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `infer_lm_links`           | `infer_lm_links.py`           | ✅ yes | `GUIDES`                    | Instructions × eval factors: gathers `proposal_instruction`, `proposal_volume`, instruction-flavoured `deliverable`/`requirement` entities; sends instruction–eval factor pairs to LLM via `instruction_evaluation_linking.md` prompt; extracts `GUIDES` edges |
| `infer_document_structure` | `infer_document_structure.py` | ❌ no  | `REFERENCES`, `CHILD_OF`    | Pure regex: detects CDRL/DID/DD-Form-1423 cross-refs, doc-section refs, attachment refs; builds numbered-hierarchy `CHILD_OF` edges from dot-notation prefixes (e.g. `F.1.5.7` → `F.1.5`) — deterministic, zero API cost                                       |
| `resolve_orphans`          | `resolve_orphans.py`          | ✅ yes | any canonical type          | Queries Neo4j for entities with zero edges; batches them 30 orphans × 100 targets; sends each batch to LLM via `orphan_resolution.md` prompt; prioritises high-value target types (`requirement`, `document_section`, `deliverable`…)                          |

Reduced from 8 → 3 algorithms in Issue #85: algorithms 2–6 became redundant once the extraction prompt + specialized entity types handled that coverage natively.
_Avoid_: calling them "phases" (phases = the 5-phase wrapper; algorithms = parallel workers inside Phase 4).

**VDB sync** (Phase 5, `src/inference/vdb_sync.py`):
`sync_discoveries_to_vdb()` — syncs Neo4j-resident inferred relationships back to LightRAG's VDB stores after Phase 4 completes. Without this step, algorithm-discovered edges exist in Neo4j but are invisible to `/query` results (KG retrieval reads the VDB, not Neo4j directly). Mechanism: calls `lightrag.ainsert_custom_kg()` on relationships tagged `source='semantic_post_processor'`. Dedupe: normalises source/target to a pair key (sorted tuple) — VDB is pair-keyed, not direction-keyed, so duplicate pair writes are harmless but tracked in `_build_sync_audit()` stats. `sync_all_relationships_to_vdb` (full resync) was removed in commit `5f4c5b8`; only `sync_discoveries_to_vdb` is active.
_Avoid_: "update VDB" (too generic); "Phase 6" (there is no Phase 6 — VDB sync is Phase 5).

**Batch**:
A user-defined group of documents uploaded together for which exactly one semantic post-processor run is guaranteed. Auto-detected by an idle-timeout window (`BATCH_TIMEOUT_SECONDS`): when no new document completes for that duration, the batch is declared complete and post-processing fires once. Without batching, uploading N documents would trigger N post-processor runs -- each exponentially more expensive as the graph grows.
_Avoid_: job, run, upload session.

**Track ID**:
Correlation token for one ingest operation. Format: `{prefix}_{YYYYMMDD_HHMMSS}_{8hex}`. Prefix is `insert` for upload-path calls (LightRAG's `generate_track_id("insert")`) and `scan-{8hex}` for `/scan-rfp` (our code). Stored in `kv_store_doc_status.json` per document. Emitted in server log lines as `[scan <track_id>]`. Use to grep server log for all events from one ingest session.
_Avoid_: request ID, job ID (neither is a first-class concept here).

**LLM response cache** (`kv_store_llm_response_cache.json`, workspace root):
LightRAG's content-addressed cache of LLM API responses. Cache key = hash of `(model, prompt, system_prompt, response_format, history_messages)`. On a repeated ingest of the same document against the same model+config, identical prompts hit the cache and skip the API call entirely — safe for dev iteration but must be invalidated when switching modes. **Cache identity rule**: when `ENTITY_EXTRACTION_STRICT_SCHEMA=true`, `llm_routing.py` appends `#strict-jsonschema` to the `host` field in the `extract` role metadata. This changes the cache namespace — cached responses from the non-strict path will not be served for strict-mode runs and vice versa. Safe to delete the entire file to force full re-extraction; LightRAG rebuilds it on the next ingest. Do not delete mid-batch (partial cache leaves some chunks re-extracted, some served from cache — mismatched entity sets).
_Avoid_: "clearing the cache" without qualifying which cache (`kv_store_parse_cache.json` = MinerU parse cache; `kv_store_llm_response_cache.json` = LLM API response cache — deleting one does not affect the other).

**SkillManager** (`src/skills/manager.py`):
Singleton that discovers, installs, and invokes agent skills. Discovery: walks `.github/skills/` at startup, parses YAML frontmatter from each `SKILL.md`; install ledger at `var/platform/skills.json` (global to instance, not per-workspace). Invocation: `SkillManager.invoke(name, workspace, user_prompt, entity_payload, llm, ...)` → `SkillExecutor.invoke()` → runtime branch:

- **legacy mode** (`run_legacy_skill`): single-shot — compose full prompt (SKILL.md body + `entity_payload` JSON briefing book) → one `llm()` call → persist run. Simpler, cheaper, no tool calls.
- **tools mode** (`run_tools_skill`): multi-turn agentic loop — LLM calls tools (`kg_query`, `kg_entities`, `kg_chunks`, `read_file`, `run_script`, `write_file`) up to `SKILL_TOOLS_MAX_TURNS` (default 20) per run. Skills declare `metadata.runtime: tools` in frontmatter to opt in. `run_tools_skill()` in `src/skills/skill_tools_runner.py`: (1) creates `run_dir` via `run_store.create_run_dir()`; (2) resolves script roots — `_DEFAULT_SCRIPT_ROOTS` (renderers + huashu-design) always added, plus `metadata.script_paths` entries validated as directories; (3) starts MCP sessions for `required_mcps` from frontmatter; (4) calls `run_tool_loop()` up to `max_turns`; (5) persists run via `run_store.persist_tools_run()`; (6) calls `auto_emit_artifacts()` unless `metadata.auto_emit_artifacts: false`; (7) calls `touch_invocation(skill.name)` for LRU tracking.

Runtime mode resolution order: `runtime_mode_override` arg → `SKILL_RUNTIME_MODE` env var → skill frontmatter `metadata.runtime` → default `legacy`.

Skill chaining: tools-mode skills can call `invoke_skill(child_name, child_prompt)` as a tool. Max depth = 1 (one child per parent, no recursion). Cycle detection prevents `A→B→A`. `SkillManager.invoke_chain()` runs deterministic multi-skill sequences via `SkillChainExecutor` (LangGraph).
_Avoid_: "skill runner" (ambiguous — both runners exist); "skill pipeline" (see Flagged ambiguities).

**Artifact auto-emission** (`src/skills/skill_emitters.py`):
`auto_emit_artifacts(skill, run_dir)` — called at the end of every tools-mode run unless `metadata.auto_emit_artifacts: false`. Detects JSON + Markdown artifacts written by the skill in `run_dir/artifacts/`, then calls the `renderers` and `huashu-design` render scripts to produce `.docx` (from `.md` via Pandoc) and `.xlsx` (from `.json` via openpyxl).

`_PRODUCT_PROFILES` maps 10 known skills (competitive-intel, compliance-auditor, proposal-generator, price-to-win, oci-sweeper, ot-prototype-strategist, rfp-reverse-engineer, subcontractor-sow-builder, workload-analyzer, data-analyzer) to `{base, label, xlsx_sources}` — controls base filename stem and which JSON files to render into workbook sheets. Unknown skills get defaults derived from `skill.name`.

Format control: `metadata.auto_emit_formats` (comma-separated or list) → set of `{"html", "md", "json", "docx", "xlsx"}`; default `{"md", "json", "docx", "xlsx"}`. XLSX source priority: `metadata.auto_emit_xlsx_source` → profile `xlsx_sources` → discovered `*.json` (alpha-sorted, excluding `report.json`). Render outcome written back to artifact manifest: `render_status: failed` with `render_message` / `render_log_excerpt` if subprocess fails.
_Avoid_: "auto-save" (these are render conversions, not simple copies); assuming all skills emit — skills can opt out per `metadata.auto_emit_artifacts: false`.

**SkillSettingsStore** (`src/skills/settings.py`):
Per-workspace settings file (`rag_storage/<workspace>/ui_skill_settings.json`). Two independent settings surfaces:

1. **Briefing-book params** (stored in file, per-workspace): `max_entities_per_type` (default 40), `max_chunks_per_entity` (default 3), `max_relationships_per_entity` (default 8), `retrieval_mode` (default from `SKILL_RETRIEVAL_MODE` env, fallback `"mix"`), `retrieval_top_k` (default 60). `read()` merges stored keys over defaults; `write()` atomic tmp-replace.
2. **Tools-mode runtime limits** (stored in `.env`, global to process, not per-workspace): 13 env vars — `SKILL_TOOLS_MAX_TURNS` (20), `SKILL_TOOLS_LLM_TIMEOUT` (180 s), `MCP_HANDSHAKE_TIMEOUT` (15 s), `MCP_TOOL_CALL_TIMEOUT` (60 s), `MCP_SHUTDOWN_TIMEOUT` (3 s), `SKILL_TOOLS_MAX_TOOL_RESULT_CHARS` (12 000), `SKILL_TOOLS_MAX_READ_BYTES` (200 000), `SKILL_TOOLS_MAX_WRITE_BYTES` (1 000 000), `SKILL_TOOLS_MAX_SCRIPT_SECONDS` (120), `SKILL_TOOLS_MAX_KG_ENTITIES_PER_TYPE` (50), `SKILL_TOOLS_MAX_KG_CHUNKS` (30), `SKILL_TOOLS_MAX_CHUNKS_PER_ENTITY` (5), `SKILL_TOOLS_MAX_RELATIONSHIPS_PER_ENTITY` (20). Written via `set_env_var` (triggers `reset_settings()` — see Workspace management). Read at call-time via `skill_tools_runtime_limits()` → `SkillToolsRuntimeLimits` frozen dataclass.

`VALID_SKILL_RETRIEVAL_MODES = {"hybrid", "local", "global", "naive", "mix", "off"}`. `"off"` disables retrieval entirely — briefing book falls back to bulk entity slice. `VALID_SKILL_RUNTIME_MODES = {"tools", "legacy"}`.
_Avoid_: "skill settings" without specifying which surface (briefing-book params vs tools-mode runtime limits — different backing stores, different scope).

**Briefing book** (`entity_payload`):
The source-grounded context package assembled by the route layer and passed to `SkillManager.invoke()` as `entity_payload`. Built in two steps:

1. **Retrieval** (`_retrieve_relevant_entities_for_skill()`): runs a hybrid KG+VDB query against the user prompt + skill description; returns a lowercased entity-name whitelist (`names`) and matched chunk IDs.
2. **Slice** (`build_skill_briefing_book()` in `src/skills/context.py` → `SkillWorkspaceEvidenceStore.build_briefing_book()`): reads workspace KV stores and graph, filters to whitelisted entity names (or bulk-slices if retrieval is off), returns a dict with three keys:
   - `entities`: `{entity_type: [{name, description, source_chunks}]}`
   - `source_chunks`: verbatim RFP text blocks (model must quote from these, not fabricate)
   - `relationships`: typed KG edges connected to sliced entities

In the prompt the briefing book is framed under the header `"## Workspace Briefing Book (JSON)"` and declared the "authoritative source of truth" (`src/skills/skill_prompting.py`). Size cap: `SKILL_MAX_PAYLOAD_CHARS` env var. Retrieval mode and `top_k` are per-request; `mode="off"` disables retrieval and falls back to bulk entity slice.
_Avoid_: "entity context", "workspace context" (both too generic); "KG dump" (loses the retrieval-grounding step).

**SkillCatalog** (`src/skills/skill_catalog.py`):
Deep module for skill discovery, install, and ledger persistence. Owns the in-memory `dict[str, Skill]` registry plus a JSON ledger file (`rag_storage/<workspace>/skills_ledger.json`). Key behaviors:

- `discover()` — walks `skills_dir/` for subfolders containing `SKILL.md`; parses frontmatter via `parse_frontmatter()`; merges ledger metadata (installed_at, last_invoked_at, source); rebuilds `_skills` dict. Called at server startup and after every install/uninstall. Silently skips folders that fail to parse.
- `get_skill(name)` / `get_skill_detail(name)` — `get_skill_detail` adds `body_md`, `references`, `assets`, `templates`, `scripts` file lists.
- `install_from_github(url)` — shallow `git clone --depth=1` into `skills_dir/`, validates `SKILL.md` exists, strips `.git/`, records ledger entry, re-calls `discover()`. Validates URL must begin with `https://github.com/` — only GitHub sources accepted.
- `uninstall(name)` — refuses to delete `source == "builtin"` skills; calls `shutil.rmtree` on skill folder.
- `touch_invocation(name)` — updates `last_invoked_at` in ledger on every `SkillManager.invoke()` call.
- Skill `source` values: `"builtin"` (shipped with repo, never deletable), `"installed"` (installed via GitHub URL).
- Name validation: `_SAFE_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")`.
- `has_assets` / `has_templates` / `has_scripts` / `has_references` / `has_evals` — boolean flags from subdirectory presence, set at discovery time.
_Avoid_: "skill registry" (that's `SkillManager`'s job); "skill store" (the JSON ledger is just the ledger, not the full catalog).

**Skill routes** (`src/server/skill_routes.py`):
HTTP API surface for skill invocation, runs management, and settings. Three registration functions:

- `register_skill_catalog_ui_routes`: `GET /api/ui/skills`, `GET /api/ui/skills/{name}`, `POST /api/ui/skills/refresh`, `POST /api/ui/skills/install`, `DELETE /api/ui/skills/{name}`.
- `register_skill_settings_ui_routes`: `GET/PUT/POST /api/ui/settings/skills` (briefing-book params: `max_entities_per_type`, `max_chunks_per_entity`, `max_relationships_per_entity`, `retrieval_mode`, `retrieval_top_k`) and `GET/PUT/POST /api/ui/settings/skills/runtime` (tools-mode ceiling params persisted to `.env` via `set_env_var`).
- `register_skill_invoke_ui_routes`: `POST /api/ui/skills/{name}/invoke` + `POST /api/ui/skills/{name}/runs/{run_id}/resume` + chain invoke/plan endpoints + `GET/POST` runs management + Studio artifact endpoints.

**Invoke flow** (`POST /api/ui/skills/{name}/invoke`): determine `effective_mode` via `resolve_skill_runtime_mode(frontmatter_mode)` → if `"tools"` mode, pass empty `entity_payload={}` and bound `slice_fn`/`retrieve_fn` closures (capped to payload limits) — the tool loop fetches KG data lazily. If `"legacy"` mode, eagerly build the briefing book (retrieval → slice → attach to `entity_payload`) before calling `mgr.invoke()`. Response shape: `{skill, workspace, response, entities_used, warnings, elapsed_ms, prompt_tokens_estimate, run_id, run_dir, finish_reason, runtime_mode, retrieval}`.

**Resume flow** (`POST /api/ui/skills/{name}/runs/{run_id}/resume`): loads existing run, checks `can_resume` flag (HTTP 409 if not), merges `user_addendum` + `answers` dict, re-invokes with `user_supplied_context.resume_notes` in the entity payload.

**Skill runs** (`rag_storage/<workspace>/skill_runs/<skill_name>/<run_id>/`): each invocation writes a run directory containing `metadata.json`, `response.md`, `transcript.json`, and any produced artifacts. Route: `GET /api/ui/skills/{name}/runs?limit=<n>` (list), `GET /api/ui/skills/{name}/runs/{run_id}` (detail), `/reasoning` (reasoning view extracted from transcript). Trash/restore: `list_trashed_runs`, restore + bulk delete endpoints under Studio (`GET/POST /api/ui/studio/*`).
_Avoid_: "skill API" (three separate registration functions exist — be specific); "runtime_mode" (means legacy vs tools); "run" without qualifying it's a `SkillRunMetadata` record under `skill_runs/`.

**SkillChainExecutor** (`src/skills/chain_executor.py`):
LangGraph-backed executor for deterministic multi-skill chains. Called by `SkillManager.invoke_chain()` when the planner (or explicit API call) needs a fixed sequence of skills rather than a single-skill invocation. Uses a `StateGraph` with one node per chain step; steps share a `ChainRunState` carried through `ChainExecutionState`. Key contract:

- `invoke(spec, ...)` → runs a new `ChainSpec` (list of `ChainStepSpec`s) from scratch
- `resume(chain, from_step_id=...)` → re-executes from a specific step after user supplies missing inputs
- `blocked` flag set when any step reports `needs_input`; planner surfaces the `input_request` to the user
- Artifacts produced by step N are promoted (via `_promoted_artifacts()`) and available as inputs to step N+1 — this is the cross-skill handoff mechanism
- `mode` field: `"original"` (production) or `"dry_run"` (validation without LLM calls)

**ChainSpec** (plan, `src/skills/chain_models.py`): user/system-authored chain request. Fields: `name`, `prompt`, `context`, `steps: list[ChainStepSpec]` (max 20), `stop_on_error`. Validated as a DAG at construction time: no duplicate step IDs, no forward `depends_on` references, no forward `from_steps` in artifact requirements. `ChainStepSpec` fields: `id` (lowercase kebab/snake, unique), `skill`, `prompt`, `context`, `depends_on`, `input_artifacts` (pre-resolved `ChainArtifactRef`s), `artifact_requirements` (`ChainArtifactRequirement` contracts specifying expected files from prior steps by extension, mime, product label).

**ChainRunState** (execution ledger, `src/skills/chain_models.py`): wraps the plan with runtime state. Fields: `chain_id`, `workspace`, `status` (pending/running/completed/partial/failed), `mode` (original/rerun/resume), `source_chain_id` (for reruns), `spec: ChainSpec`, `steps: dict[str, ChainStepRun]`, `promoted_artifacts` (cross-step `ChainArtifactRef`s resolved from finished steps), `input_request` (non-empty when blocked), `resume_notes`. `ChainStepRun` status cycle: pending → running → completed | partial | failed | skipped. `missing_inputs`/`missing_outputs` on both `ChainStepRun` and `ChainRunState` capture quality-gate failures without failing the run.

`chain_contracts.py` declares which skills can chain and what they accept/produce — planner uses this to validate a proposed sequence before constructing a `ChainSpec`.
_Avoid_: calling chains "pipelines" (see Flagged ambiguities); confusing `ChainSpec` (plan) with `ChainRunState` (execution state); using `ChainRunState.steps` as a list (it is keyed by step id).

**SkillChainPlanner** (`src/skills/chain_planner.py`):
Deterministic, scoring-based planner that converts a goal string (`prompt` + optional `outcome`) into a `ChainPlan`. No LLM call — pure keyword/contract matching.

Scoring: for each eligible skill, `_score()` awards `4 × |goal_tokens ∩ contract.keywords|` + `2 × name tokens` + `1 × capability tokens`. Skills not in `CONTRACT_REGISTRY` fall back to description text (capped at 3 pts). Minimum threshold: **score ≥ 4** to become a target skill.

Selection: `_target_skills()` → `_select_skills()` → for each target skill, upstream skills in `CONTRACT_REGISTRY.downstream_skills(target)` are prepended in phase-rank order. Renderer skills (`renderers`, `huashu-design`) appended if `include_rendering=True` and goal contains output terms (`docx`, `xlsx`, `pdf`, etc.) and the upstream skill's contract marks it as `renderable_upstream`. Disconnected skills (no valid handoff path to any other selected skill) are pruned by `_prune_disconnected()`.

`_EXCLUDED_BY_DEFAULT = {"caveman", "grill-me", "govcon-ontology", "improve-codebase-architecture", "skill-creator", "tdd", "to-issues", "to-prd"}` — meta/analysis skills excluded from planning unless explicitly named in the goal tokens.

Output: `ChainPlan` → `spec: ChainSpec` (step IDs are slugified skill names, `artifact_requirements` wired from contract `produces`/`accepts`), `selected_skills` (with scores + roles), `rejected_skills` (top 10 scored but not selected), `warnings`, `rationale`, `iteration_policy: {mode: "outcome-gated-linear"}`. If no skills match: raises `ValueError`.
_Avoid_: "AI planner" (no LLM); "automatic chain" (user must invoke `/api/ui/skill-chains/plan` explicitly); confusing plan threshold (score ≥ 4) with runtime quality gates.

**Skill run directory**:
Per-invocation working directory for one skill execution. Path: `rag_storage/<workspace>/skill_runs/<skill>/<YYYYMMDD_HHMMSS_slug>/`. Contains:
- `run.md` — run envelope (YAML-ish frontmatter); parsed by `parse_run_envelope()` to produce `metadata` dict with `run_id`, `skill`, `workspace`, `created_at`, `user_prompt`, `elapsed_ms`, etc.
- `response.md` — raw LLM response text
- `prompt.md` — full prompt sent to LLM (briefing book + skill body)
- `artifacts/` — skill output files (`.docx`, `.xlsx`, `.md`, etc.); discoverable via `list_run_artifacts()` using `artifact_manifest.json` for metadata + MIME
- `tool_outputs/` — raw tool call results per turn (tools-mode only)
- `transcript.json` — array of tool call events; fed to `build_reasoning_view()` for the UI reasoning panel

`SkillRunIndex.list_runs()`: walks `skill_runs/`, reads `run.md` envelopes, projects via `_project_run_summary_payload()` → adds `input_request`, `missing_inputs`, `status` (`"completed"` | `"interrupted"`), `can_resume` bool. `_extract_missing_inputs(response)` scans response text for bullet lists under "exact gaps"/"missing inputs" headers. `_extract_follow_up_question(response)` detects question-format lines.

`SkillRunIndex.read_run()`: full detail — adds `artifacts`, `transcript`, `tool_outputs`. Run ID must pass `_SAFE_RUN_ID = re.compile(r"^[0-9]{8}_[0-9]{6}_[a-z0-9_-]+$")`.

Trash: `rag_storage/<workspace>/.trash/studio_artifacts/<trash_id>/`. `trash_id` format: `YYYYMMDD_HHMMSS_microseconds_original.ext`. Restore: moves back to original path. Bulk trash/restore endpoints under Studio (`GET/POST /api/ui/studio/trash`, `/restore`, `/delete`).
_Avoid_: run-dir, output dir, workspace; "run.md is JSON" (it's an envelope parsed by `parse_run_envelope`, not raw JSON).

**MCP skill integration** (`src/skills/mcp_client.py`, `src/skills/mcp_session.py`):
Skills declare `metadata.mcps: [usaspending, sam_gov]` in `SKILL.md` frontmatter to access vendored MCP servers under `tools/mcps/<name>/`. Architecture:

- **`MCPRegistry`** (one per server process, owned by `SkillManager`): maps `run_id → {name → MCPSession}`. `start_for_run(run_id, skill_mcps, ...)` spawns subprocesses + handshakes. `shutdown_run(run_id)` tears down all sessions for a run in the `finally` block of `run_tool_loop`.
- **`MCPSession`** (one subprocess per MCP per skill run, no cross-run pooling): stdio transport + newline-delimited JSON-RPC (per MCP spec — one message per line). Performs `initialize` handshake, calls `tools/list`, registers each server tool as a `ToolSpec` named `mcp__<server>__<tool>`. Async futures map pending `id → Future`; `_reader_task` dispatches responses.
- **`MCPManifest`** (`tools/mcps/<name>/theseus_manifest.json`): spawn command, `env_required`/`env_optional`, `vendored_from` URL + commit for re-vendor audit. Separate from upstream `package.json`/`mcp.json` — Theseus-side glue only.
- **From the model's view**: MCP tools look identical to in-process tools (`read_file`, `kg_query`, etc.) — all flow through the same tool dispatch loop and transcript.
- **Allowlist**: registry spawns only servers whose names appear in the calling skill's `metadata.mcps`. Empty = no MCP tools (closed by default).

Missing env vars → `MCPError` at session start, logged as `missing` in `MCPStartupResult.missing[]` — skill run continues without that server's tools and warns in transcript.
_Avoid_: "MCP server" without qualifying "vendored MCP server under `tools/mcps/`" (the VS Code MCP servers the user installs are a different concept; Theseus's vendored MCPs are skill-scoped subprocesses).

**Inputs directory** (`inputs/<workspace>/`):
Filesystem staging area for batch ingest. Drop PDFs/DOCX here, then call `POST /scan-rfp` to process all unprocessed files in the folder sequentially. Already-processed files are skipped. The server also copies uploaded files here when using the Documents UI (`/documents/upload`). `inputs/__enqueued__/` is a reserved name (never written to by any code — skip it).
_Avoid_: upload folder, queue (there is no queue; scan is synchronous per-file in a background task).

**Upload** (`POST /documents/upload`):
Interactive single-file ingest via the UI. Saves the file to `inputs/<workspace>/` then immediately processes it through the ingest pipeline. Supports `stage_only=true` to save without processing (defers to scan). Primary/preferred path for day-to-day use. Upload staging (`src/server/upload_staging.py`):

- `sanitize_upload_filename(name)`: strips `/`, `\`, and leading `.` from the filename — prevents path traversal before saving.
- SHA-256 content dedup: if a file with the same name already exists in `inputs/<workspace>/`, the two files are hashed. Identical content → existing file reused (no overwrite, no re-ingest). Different content → new file saved with `_YYYYMMDD_HHMMSS` timestamp suffix.
- Write: atomic temp file in the same folder → `tmp.replace(target)` — avoids torn writes.
- `list_scannable_files(folder)`: non-recursive glob for `DEFAULT_SCAN_EXTENSIONS` — used by scan to find pending files; deduplicates case variants.
_Avoid_: "file upload" without noting the SHA-256 dedup (identical re-upload silently reuses the existing file).

**Scan** (`POST /scan-rfp`):
Filesystem batch ingest. Reads all unprocessed files from `inputs/<workspace>/`, processes each sequentially in a background task, skips already-processed files (`doc_status.get_doc_by_file_path(name)` with `status == "processed"`). Returns a `track_id` immediately (`scan-<8hex>`); progress visible in server logs by filtering on `[scan <track_id>]`. Response `status` values: `"scanning_started"` (files found + background task launched) | `"empty"` (no supported files in folder). Same `process_document_func` as upload — identical pipeline, different trigger. Intended for bulk/automated ingestion when comfortable with that workflow.
_Avoid_: confusing scan with upload — they share the pipeline but differ in trigger, batching, and background execution.

**Bootstrap**:
One-time pre-seeding of a workspace's knowledge graph with curated govcon domain knowledge (Shipley methodology, FAR patterns, evaluation frameworks) before any RFP documents are uploaded. Triggered automatically at server startup via `maybe_bootstrap_ontology()` in `src/server/rag_post_init.py`. Gate: `AUTO_BOOTSTRAP_ONTOLOGY` env var (default `true`). Fresh workspace (no marker) + env enabled -> ontology entities/relationships become the initial KG foundation. `.ontology_bootstrap` marker written after success; present -> skip on subsequent startups. `ONTOLOGY_BOOTSTRAP_FORCE=true` re-seeds even if marker exists.
_Avoid_: initialization (overloaded with server startup), seed.

**Workspace management** (`src/server/workspace_routes.py`):
Routes for creating, switching, inspecting, and deleting workspaces. `WorkspaceMaintenance` (deep module) implements discovery and deletion; `discover_workspaces(working_dir)` finds folders under `rag_storage/` that contain any of `kv_store_doc_status.json`, `vdb_entities.json`, `vdb_chunks.json`.

| Route | Effect |
|---|---|
| `GET /api/ui/workspaces` | Lists discovered workspaces + active name |
| `POST /api/ui/workspaces/switch` | Writes `WORKSPACE=<name>` to `.env`, resets settings, schedules `self_restart()` (0.75 s delay) — **process re-execs itself** |
| `GET /api/ui/workspaces/inventory` | Cross-view table: Neo4j node counts + rag_storage MB + inputs file counts for every workspace |
| `POST /api/ui/workspaces/{name}/delete` | Deletes selected buckets (`neo4j`, `rag_storage`, `inputs`); refuses to delete active workspace |
| `POST /api/ui/workspaces/wipe-all` | Deletes all workspaces across selected buckets; requires `confirm="DELETE ALL"`; re-creates active workspace dir; schedules restart |
| `POST /api/ui/restart` | Schedules `self_restart()` with 0.75 s delay |

`set_env_var(key, value)` writes directly to `.env` file (atomic tmp-rename), then calls `os.environ[key] = value` and `reset_settings()`. Switching workspace = `set_env_var("WORKSPACE", name)` + restart. Workspace name validation: `_SAFE_WS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")`. Cannot delete active workspace — must switch first.
_Avoid_: "workspace selector" (generic); "hot-swap" (switch requires a full process restart, not a live reconfigure).

**Chat** (chat session, `rag_storage/<workspace>/chats/<id>.json`):
Persisted UI conversation stored as one JSON file per chat. `ChatStore` (`src/server/chat_store.py`) manages the lifecycle — one `ChatStore` instance per server, scoped to the active workspace dir. Chat schema: `id` (16-hex UUID), `title`, `mode` (query mode: `local`/`global`/`hybrid`/`mix`/`naive`/`bypass`), `rfp_context` (optional free-text context prepended to queries), `messages[]` (`{role, content, timestamp}`), `created_at`, `updated_at`. Key behaviors:

- Atomic write: writes to `<id>.json.tmp` then renames — no partial-write corruption on server kill
- `build_history()`: extracts `(role, content)` pairs from `messages[]`; caps to `CHAT_HISTORY_PAIRS` most-recent pairs to bound context window sent to LightRAG
- `maybe_autotitle()`: if title is still "New chat", sets it to the first 60 chars of the first user message
- `mode` is stored per-chat; override accepted on each `POST /chats/{id}/messages` call

`kv_store_chats.json` does **not** exist — chats are stored as individual files, not a single KV store. The UI calls `GET /chats` to list summaries (title, mode, message count, timestamps) without loading full message history.
_Avoid_: "chat session" (not a server-side session object); "chat history" (ambiguous with LightRAG conversation_history — qualify which).

**Entity catalog**:
The YAML-driven registry of 33 govcon entity types at `prompts/extraction/govcon_entity_types.yaml`. Single source of truth — `VALID_ENTITY_TYPES` in `src/ontology/schema.py` is derived from it at import time (no regeneration step). The extraction prompt's Part D (`{entity_types_guidance}`) is also rendered from this YAML at runtime. To add a new entity type: edit the YAML only, then run `pytest tests/ontology/test_entity_catalog_coherence.py` to confirm parity. No other files need hand-editing.
_Avoid_: entity types list, entity schema.

**Canonical relationship types**:
The 35 fixed relationship type strings defined in `src/ontology/schema.py -> VALID_RELATIONSHIP_TYPES`. Every relationship in the knowledge graph must use one of these as its `keywords` first token. `normalize_relationship_type(rel_type, fallback="RELATED_TO")` (`src/ontology/schema.py`) converts any extracted or inferred string to the nearest valid canonical type; unknown types silently become `RELATED_TO` (WARNING logged). `_INFERENCE_ONLY_REL_TYPES` frozenset in `src/ontology/extraction_schema.py` lists types produced only by inference algorithms (e.g. `GUIDES`) — excluded from the strict schema's relationship type enum so extraction never emits them directly.
_Avoid_: edge types, link types, relationship schema.

**Strict schema extraction** (`ENTITY_EXTRACTION_STRICT_SCHEMA`, `src/ontology/extraction_schema.py`):
Optional mode that passes `response_format={"type": "json_schema", "json_schema": {..., "strict": True}}` to xAI's OpenAI-compatible API for the `extract` role, constraining the model to emit exactly the field names LightRAG's parser expects. Enabled via `ENTITY_EXTRACTION_STRICT_SCHEMA=true` in `.env`. Schema name: `GovConExtractionResult`. Enforces:

- `entities[].type` constrained to the entity catalog enum (no invented types at extraction time)
- Required fields `name`, `type`, `description` always present on each entity object
- Required fields `source`, `target`, `keywords`, `description` always present on each relationship object

**Why `keywords` has no `pattern` constraint**: xAI strict mode rejects JSON-Schema `pattern` (returns HTTP 400). First-token relationship type enforcement is handled by (a) the extraction prompt and (b) downstream `normalize_relationship_type()` in `src/ontology/schema.py`. **Cache identity note**: switching `ENTITY_EXTRACTION_STRICT_SCHEMA` on or off changes the `response_format` argument, which changes the cache key in `kv_store_llm_response_cache.json` — existing cached responses from the opposite mode will not be reused. Baseline data (mcpp_drfp): strict mode `GovConExtractionResult` yielded 4994 entities / 8603 relationships vs 2614 / 4245 for JSON without schema (−48% / −51%).

**Chunking**:
LightRAG splits each document into token-bounded chunks before extraction. Two required `.env` knobs — `CHUNK_SIZE` (tokens per chunk) and `CHUNK_OVERLAP_SIZE` (overlap tokens) — both mandatory, no safe default, startup fails without them. The custom chunker (`src/extraction/govcon_chunking.py`, registered via `global_args.chunking_func`) wraps LightRAG's native `chunking_by_token_size` and prepends a `[GOVCON_DOC: type=...; note=...]` banner to every chunk so the extraction prompt and query prompt know the doc type. No other chunking parameters exist.

**Per-role LLM models** (`src/server/llm_routing.py`):
LightRAG 1.5.0 allows a separate model per processing role. `build_role_llm_routing()` constructs all role wrappers from two config fields (`extraction_llm_name`, `reasoning_llm_name`); the other roles reuse `extraction_llm_name` by default.

| Role           | `.env` var               | Default model                 | What it does                                                                                                                                                  |
| -------------- | ------------------------ | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `extract`      | `EXTRACT_LLM_MODEL`      | `grok-4-1-fast-non-reasoning` | Entity + relationship extraction (LightRAG `extract` role). Optionally enforces strict JSON schema (`ENTITY_EXTRACTION_STRICT_SCHEMA=true`). Max 32 k tokens. |
| `query`        | `QUERY_LLM_MODEL`        | `grok-4.20-0309-reasoning`    | RAG query answering via Shipley mentor persona (LightRAG `query` role). Max `llm_max_output_tokens`.                                                          |
| `keyword`      | `KEYWORD_LLM_MODEL`      | reuses `EXTRACT_LLM_MODEL`    | Query-time keyword extraction (LightRAG `keyword` role). Max 4 k tokens.                                                                                      |
| `vlm`          | `VLM_LLM_MODEL`          | reuses `EXTRACT_LLM_MODEL`    | VLM table/image/equation analysis (LightRAG `vlm` role). Max 8 k tokens.                                                                                      |
| `post_process` | `POST_PROCESS_LLM_MODEL` | `grok-4-1-fast-reasoning`     | Inference algorithms in `src/inference/`. **Not** a LightRAG role — called directly by `SemanticPostProcessor`.                                               |

`keyword` and `vlm` reuse `extraction_llm_name` at the function level; their `.env` vars exist in config but are not wired in `llm_routing.py`. `modal_llm_func` (RAGAnything multimodal processor) also reuses `extraction_llm_name` and strips any strict JSON schema `response_format` if accidentally passed.
_Avoid_: "the LLM" (five model slots exist); "reasoning model" without specifying which role.

**mineru/ cache** (`rag_storage/<workspace>/mineru/`):
MinerU parse artifacts written once per document. Layout: `<doc_filename>_<hash8>/<doc_filename>/auto/` containing:

- `<doc>.md` — reconstructed markdown of the full document
- `<doc>_content_list.json` / `_content_list_v2.json` — structured content blocks (text, table, image, equation items) passed to RAGAnything for modal processing
- `<doc>_middle.json` / `_model.json` — intermediate layout analysis from MinerU
- `<doc>_layout.pdf` / `_span.pdf` / `_origin.pdf` — layout visualisation and original copy
- `images/` — extracted image files referenced by content blocks

`kv_store_parse_cache.json` (workspace root, namespace `parse_cache`): LightRAG KV store mapping doc hash → content list. Prevents re-running MinerU when the same file is re-uploaded. Safe to delete to force a fresh parse; rebuilds on next ingest.
_Avoid_: "MinerU output" (ambiguous with `output_dir`); "parser cache" (both the `mineru/` folder and `kv_store_parse_cache.json` exist — qualify which).

**Processing log** (`rag_storage/<workspace>/<workspace>_processing.log`):
Workspace-scoped log file written by the ingest and semantic post-processing pipelines. Distinct from `logs/server.log.*` (global server log). Path resolved at runtime via `_log_path()` using `global_args.working_dir + WORKSPACE` — not a static path. Routes in `src/server/document_routes.py`:

- `GET /api/ui/processing-log?limit=<n>` — `read_snapshot()` reads the tail of the log file (up to `limit`, hard cap 2000); returns `{path, exists, events[]}`. `events[]` items: `{id, ts, level, logger, message, category, kind, phase?}`.
- `GET /api/ui/processing-log/stream` — SSE stream via `stream_events()`: yields a `snapshot` frame first (last `limit` events), then `event` frames as new lines are appended (1.5 s poll), with `ping` keep-alives every 15 s.

Event classification (`classify_workspace_log_event`): each parsed log line is tagged with `category` (`"processing"` / `"query"` / `"lightrag-processing"` / `"lightrag-query"` / other) based on logger name and message prefix markers. `_PHASE_RE` regex extracts phase number/label from `"Phase N: ..."` lines (semantic post-processor banners).

`parse_workspace_log_lines(lines)` is the text-format parser: expects `YYYY-MM-DD HH:MM:SS | LEVEL | logger | message` format; silently discards malformed lines. `_read_tail_lines(path, max_lines)` does backwards block-read (64 KB blocks, `seek(0, 2)`) — never reads more than needed.
_Avoid_: "server log" (that's the global `logs/server.log.*`); "processing log" without specifying workspace (each workspace has its own file).

### Prompt systems

**Extraction prompt** (System 1):
The LightRAG prompt that extracts entities and relationships from text chunks during the ingest pipeline. Lives at `prompts/govcon/extraction.py -> build_v8_system_prompt()`.
_Avoid_: "the prompt" (three prompt systems exist -- always qualify which one).

**Query prompt** (System 2):
The RAG response prompt that answers user queries through the Shipley mentor persona. Lives at `prompts/govcon/query.py`.

**Multimodal prompt** (System 3):
The VLM prompt for analyzing tables, images, and equations extracted by MinerU. Lives at `prompts/multimodal/govcon_multimodal_prompts.py`.

**Reasoning filter** (`src/server/reasoning_filter.py`):
`strip_think(text)` removes `<think>...</think>` reasoning blocks that xAI Grok reasoning models emit before the visible response. Applied to every assistant message before it is persisted to the chat JSON. `ThinkStripper` is the stateful streaming variant — buffers input and emits only text outside `<think>` blocks, used in the SSE streaming path. Neither class modifies the query LLM output seen by skills (skills receive post-reasoning text via `aquery()`). If `<think>` tags appear in the KG (e.g. extraction chunked through a reasoning model), they are not cleaned — that is an extraction config problem, not a filter gap.
_Avoid_: calling it "chain-of-thought stripping" (specific to Grok's `<think>` tag convention, not a general CoT mechanism).

**Entity name normalization** (`normalize_entity_name`, `src/inference/relationship_inference_support.py`):
Pure text normalization for duplicate detection comparison only — removes `section`, `sec`, `.`, `-`, `:`, and spaces from a name string, then lowercases. Used by `plan_entity_name_updates()` to compare two entity names ignoring punctuation drift. **Not** used for canonical storage or display — normalized form is never written to Neo4j or VDB. Do not use for any other purpose.
_Avoid_: calling it "entity deduplication" (dedup uses this as one comparison step; the output is never the canonical form).

### Query modes

**Query mode** (`mode` param on `QueryParam`, default `mix`):
How LightRAG retrieves context before generating an answer. Passed per-chat; stored in the chat JSON file (see **Chat**); code default = `"mix"` in `chat_routes.py` and `settings.py`. Valid set: `{"local", "global", "hybrid", "mix", "naive", "bypass"}` — enforced in `VALID_QUERY_MODES`.

| Mode     | What it fetches                                           | When to use                                                                                            |
| -------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `local`  | Entity VDB lookup on `ll_keywords` + graph node traversal | Narrow entity facts ("what is the CLIN structure?")                                                    |
| `global` | Relationship VDB lookup on `hl_keywords` + edge traversal | Broad cross-doc themes ("what are the evaluation priorities?")                                         |
| `hybrid` | Both entity and relationship paths, round-robin merged    | General — balanced entity+relationship coverage                                                        |
| `mix`    | hybrid **+** `chunks_vdb` vector chunk retrieval appended | **Default / primary use.** Most comprehensive; adds raw text chunks to the entity+relationship context |
| `naive`  | Pure `chunks_vdb` vector search only — no KG              | Baseline semantic similarity; use to compare against KG-backed modes                                   |
| `bypass` | No retrieval — direct LLM call                            | Prompt-only queries that need no document context                                                      |

Implementation: `local`/`global`/`hybrid`/`mix` all dispatch to `kg_query()` in LightRAG's `operate.py`; `mix` additionally calls `_get_vector_context()`. `naive` calls `naive_query()`. All except `bypass` are valid for `kg_chunks` skill tool.

### UCF and solicitation structure

**UCF** (Uniform Contract Format):
Standard DoD/civilian RFP structure. Key sections: C (statement of work), H (special requirements), J (attachments), L (proposal instructions), M (evaluation factors). Not all solicitations use UCF -- the system handles non-UCF formats too.

**L-to-M mapping**:
The core use case: tracing which proposal instruction (Section L) is addressed by which evaluation factor (Section M), expressed as `MAPS_TO` relationships in the knowledge graph. Works for UCF and non-UCF equivalents.

**Proposal instruction**:
A direction in the RFP telling offerors how to structure or submit their proposal. UCF: lives in Section L. Non-UCF: equivalent instructions in any section.
_Avoid_: "Section L item" (implies UCF only).

**Evaluation factor**:
A criterion the government uses to score proposals. UCF: lives in Section M. Non-UCF: equivalent scoring criteria wherever they appear.
_Avoid_: "Section M factor" (implies UCF only).

**Requirement**:
A stated or implied obligation the contractor must fulfill after award. Distinct from proposal instructions (which govern the bid) and evaluation factors (which govern scoring).
_Avoid_: "shall statement" (too narrow -- requirements can be implied).

### Shipley methodology

**Win theme**:
A discriminator backed by proof points, explicitly tied to a customer hot button. A win theme is not a feature claim -- it requires a benefit linkage.
_Avoid_: selling point, highlight, strength.

**Hot button**:
A customer priority signal extracted from the RFP text -- a pain, goal, or emphasis that the win strategy should address.

**Ghost language**:
Language in the RFP written to advantage a specific incumbent: capability thresholds, proprietary terminology, or evaluation criteria that only one bidder can meet.

**FAB chain**:
Feature -> Advantage -> Benefit -- the three-step structure for turning a capability into a win theme statement.

**Proof point**:
Quantified evidence (past performance metric, contract value, throughput figure) that substantiates a win theme claim.

**Compliance matrix**:
An L-to-M cross-reference table showing every proposal instruction is addressed in the proposal. Built from `MAPS_TO` relationships in the knowledge graph.

### Capture management

**Pursuit** (`rag_storage/<workspace>/pursuits/<slug>/`):
A single bid opportunity being tracked through Shipley stage gates. On-disk layout per pursuit:

- `00_pursuit.yaml` — manifest with fields: `workspace`, `slug`, `title`, `agency`, `stage` (current gate: `identify`/`qualify`/`capture`/`proposal`/`submitted`/`award`), `gate.due`, `proposal_due`, `pwin.value`/`confidence`/`trend`, `pwin_drivers[]` (weighted scoring: customer 30%, solution 30%, competition 25%, price 15%; each has `score`, `rationale`, `next_action`), `readiness` scores (7 dimensions), `shipley_folders`
- `01-identify/` through `06-award/` — Shipley phase folders; capture artifacts go here as the pursuit advances

One workspace = one pursuit tracked (workspace slug = pursuit slug). No backend routes yet — YAML on disk read/written by the UI only. `stage` in `00_pursuit.yaml` is the single source of truth for current gate.
_Avoid_: "opportunity" (generic); "bid" (use pursuit when the Shipley stage-gate context applies).

## Relationships

- A **batch** completion triggers exactly one **semantic post-processor** run. See [ADR-0001](docs/adr/0001-batch-idle-timer-deduplicates-post-processing.md).
- A **workspace** contains one knowledge graph and one VDB (vector database).
- The **entity catalog** defines the valid types for all entities in the knowledge graph.
- **Canonical relationship types** define the valid `keywords` for all relationships in the knowledge graph.
- The **extraction prompt** produces entities and relationships that populate the knowledge graph during the **ingest pipeline**.
- The **semantic post-processor** reads the knowledge graph and adds inferred relationships using the **canonical relationship types**.
- A **bootstrap** seeds a **workspace**'s knowledge graph with domain knowledge before the ingest pipeline runs.
- A **proposal instruction** maps to an **evaluation factor** via an L-to-M mapping (`MAPS_TO` relationship).
- A **win theme** is anchored to a **hot button** and supported by one or more **proof points**, structured as a **FAB chain**.
- A **compliance matrix** is derived from the set of `MAPS_TO` relationships in a workspace.

## Example dialogue

> **Dev:** "Should I call this a 'pipeline' in the function name?"
>
> **Domain expert:** "Which pipeline? The ingest pipeline (the multi-phase doc processing) or the semantic post-processor (the 5-phase inference pass)? Both exist. The ambiguity is real -- see Flagged ambiguities."

> **Dev:** "The L-to-M mapping query isn't finding anything -- are the requirements in the wrong entity type?"
>
> **Domain expert:** "L-to-M mapping is `proposal_instruction` -> `evaluation_factor` via `MAPS_TO`. Requirements are a different entity type -- they represent contractor obligations after award, not proposal structure. Check whether the extraction prompt tagged the Section L items as `proposal_instruction` or accidentally as `requirement`."

## Flagged ambiguities

- **"pipeline"** -- resolved. `src/server/document_processing.py` docstring now says "ingest pipeline"; `src/inference/semantic_post_processor.py` docstring and banner now say "semantic post-processor." Never use bare "pipeline" in new code, issue titles, or test names.
- **"entity"** -- `entity` is used generically inside LightRAG internals; do not use it as a domain term in new code, issue titles, or test names. Always use the specific entity catalog type (requirement, evaluation_factor, proposal_instruction, etc.).
- **"prompt"** -- resolved by naming convention: each prompt module names itself by system (extraction.py, query.py, multimodal prompts). Always qualify: "extraction prompt", "query prompt", or "multimodal prompt." Never write bare "prompt" when the system matters.
