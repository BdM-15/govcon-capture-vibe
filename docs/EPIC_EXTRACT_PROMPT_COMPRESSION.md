# Epic (Revised): Extraction Prompt Compression + P Chunking

**Branch:** `epic/extract-prompt-compression`  
**Regression workspace:** `mcpp_rfp`  
**Assessment:** [LIGHTRAG_GOVCON_EXTRACTION_ASSESSMENT.md](LIGHTRAG_GOVCON_EXTRACTION_ASSESSMENT.md)

---

## Alignment check — LightRAG extension model

Theseus may only extend LightRAG through **sanctioned content surfaces** (no monkeypatching extract loops or mutating library internals except documented patches e.g. Neo4j entity labels):

| Surface | What changes | Per-chunk? |
|---|---|---|
| `PROMPTS.update(GOVCON_PROMPTS)` | System/user extract prompt text | No — global |
| `addon_params["entity_types_guidance"]` | Compact catalog string at `LightRAG()` init | **No — set once** |
| `ENTITY_TYPE_PROMPT_FILE` / `govcon.yaml` | Few-shot JSON examples | No — global |
| Role `EXTRACT` LLM + strict `response_format` | Schema shape | No |
| `chunking_func` / native `P` routing | Chunk boundaries | Per file |
| **Chunk `content` banner** | `[GOVCON_DOC:…]` + `[EXTRACT_FOCUS:…]` | **Yes — via text in chunk** |

**Not in this epic:** mutating `addon_params` per chunk; wrapping LightRAG `operate` extract; bulk `DIRECTED` → typed Neo4j rel labels.

---

## Verified facts — assumptions changed

| Prior assumption | Verified fact | Plan change |
|---|---|---|
| Doc-type focus via `addon_params` routing | `addon_params` set once at init ([native_lightrag_runtime.py](../src/server/native_lightrag_runtime.py)) | Focus **only** in chunk banner ([govcon_chunking.py](../src/extraction/govcon_chunking.py)) |
| Relationship types are Neo4j edge labels | LightRAG writes `-[r:DIRECTED]-`; canonical type is **first token of `r.keywords`** ([vdb_sync.py](../src/inference/vdb_sync.py)) | Gate on **keywords first-token** distribution; do not plan bulk `apoc.refactor.setType` on extraction edges (reverts on re-ingest) |
| Post-processor retrypes all generic edges | `collect_relationship_retype_updates` only retriggers when Neo4j label is `RELATED_TO`, not `DIRECTED` | Rogue keywords are an **extract + prompt** problem; inference edges use `:INFERRED_RELATIONSHIP` |
| GUIDES excluded from strict schema | Strict schema constrains **entity `type` enum** only; `keywords` has no enum ([extraction_schema.py](../src/ontology/extraction_schema.py)) | L↔M redundancy is **examples teach GUIDES** + **`infer_lm_links` also emits GUIDES** — not a schema exclusion |
| 2pp orphan gate is meaningful | Extraction is non-deterministic | **Variance baseline** (two runs) before fixing gate threshold |
| Entity/relationship totals = success | Bloat vs precision | **Structural audit** is pass/fail; counts are appendix only |

---

## Goal

Improve **structural KG quality** on stock LightRAG with **zero extra LLM calls per chunk** in Phases 1–3. Post-processor **unchanged** until quality gates pass.

---

## Quality gates (pass/fail — not counts)

| Signal | Source |
|---|---|
| Orphan rate | VDB + Neo4j (`get_orphaned_entity_ids`) |
| Tree audit score | Qualitative rubric (below) |
| Cross-doc audit score | Qualitative rubric (below) |
| `concept` + `unknown` share | Type distribution (context + gate) |
| Rogue `keywords` first-tokens | `vdb_relationships` / Neo4j `r.keywords` |
| Post-processor dependency | `infer_lm_links` + `resolve_orphans` edge counts in PP stats |
| Entity/relationship totals | **Recorded only — never pass/fail** |

---

## L↔M ownership (resolve once this epic)

**Canonical relationship type:** `GUIDES` (not `MAPS_TO`).

| Artifact | Action |
|---|---|
| [CONTEXT.md](../CONTEXT.md) | Replace `MAPS_TO` → `GUIDES` for L↔M |
| [tools/neo4j/cypher_queries/05_workspace_section_l_m_mapping.cypher](../tools/neo4j/cypher_queries/05_workspace_section_l_m_mapping.cypher) | Query `GUIDES` (+ `EVALUATED_BY` where appropriate) |
| Bootstrap `regulations.json` `MAPS_TO` keyword | Legacy bootstrap only — document, do not use in extract prompt |

**Split responsibility (remove redundancy over time, not in Phase 1):**

| Layer | Owns | Rationale |
|---|---|---|
| **Extraction** | `GUIDES` when `proposal_instruction` and `evaluation_factor` **co-occur in the same chunk** | LightRAG is chunk-local; examples already teach this (Example 1) |
| **Inference (`infer_lm_links`)** | `GUIDES` for **cross-chunk / cross-document** instruction↔factor pairs | Humans connect L and M across files; extract cannot see whole package in one call |

**This epic:** keep both; add snapshot fields `guides_keywords_vdb` vs `inferred_guides_neo4j`. **Follow-on:** if co-chunk GUIDES rises and `infer_lm_links` adds mostly duplicates, slim inference — gated by audit, not Phase 1.

---

## Deferred (written rationale)

| Item | Deferred until | Rationale |
|---|---|---|
| Multi-pass skeleton / cross-doc extract | Phase 4 gate fails on tree + cross-doc audits | Theseus orchestration around `rebuild_knowledge_from_chunks()` — extra LLM cost; only if banner + compact prompt + P chunking insufficient |
| Bulk `DIRECTED` → typed Neo4j labels | No current consumer | LightRAG upsert reverts; retrieval uses degree + `keywords`; skills/Cypher should match on `r.keywords` or pair queries, not typed labels |
| `infer_lm_links` removal | Cross-doc audit passes + duplicate GUIDES metric | Real consumer: compliance matrix — needs correct edges, not fewer inference calls |
| `concept` strict-schema gating | After compact prompt measured | Risk conflating precision with recall loss |

---

## Phase 0 — Variance baseline + pre-epic snapshot

### 0a. Snapshot tool

**New:** `tools/snapshot_workspace_kg.py`

**Metrics:**

- `orphan_rate_vdb`, `orphan_count_neo4j`
- `entity_type_distribution` (non-gating)
- `relationship_keywords_first_token` (canonical vs rogue list)
- `guides_vdb_count`, `inferred_guides_neo4j_count`
- `structural_context`: `document`, `document_section`, `evaluation_factor`, `proposal_instruction`, `work_scope_item` counts
- `post_processor_last_stats` if parseable
- `chunk_count`, `doc_count`

### 0b. Variance baseline (before code changes)

Run **two full re-ingests** of `mcpp_rfp` with **identical** config (clear `kv_store_llm_response_cache.json` each time):

```powershell
.\.venv\Scripts\python.exe tools/snapshot_workspace_kg.py --workspace mcpp_rfp --output run-dir/artifacts/mcpp_rfp_variance_run1.json
# re-ingest
.\.venv\Scripts\python.exe tools/snapshot_workspace_kg.py --workspace mcpp_rfp --output run-dir/artifacts/mcpp_rfp_variance_run2.json
```

Compute `orphan_rate_sigma` = |run1 − run2|. **Gate margin** = `max(2.0pp, 2 × orphan_rate_sigma)` for later phases.

Save pre-epic snapshot (current workspace state before branch code): `mcpp_rfp_baseline_pre_epic.json`.

### 0c. Terminology fix (docs only)

`MAPS_TO` → `GUIDES` in CONTEXT.md + Cypher query (no extract behavior change).

| LightRAG surface | Content |
|---|---|
| N/A (docs/Cypher) | Terminology alignment |

---

## Phase 1 — Prompt dedup + compaction (0 extra LLM calls)

**Highest leverage, zero-risk first.**

| # | Change | File | LightRAG surface |
|---|---|---|---|
| 1.1 | Remove `{entity_types_guidance}` from **user** prompt | [prompts/govcon/extraction.py](../prompts/govcon/extraction.py) | `PROMPTS` user prompt |
| 1.2 | Replace `render_part_d()` with `render_extraction_guidance()` compact string in `addon_params` | [entity_catalog.py](../src/ontology/entity_catalog.py), [native_lightrag_runtime.py](../src/server/native_lightrag_runtime.py) | `addon_params` (once at init) |
| 1.3 | Trim `govcon.yaml` examples 7 → 3 (L↔M, workload, anti-pattern) | [prompts/entity_type/govcon.yaml](../prompts/entity_type/govcon.yaml) | `ENTITY_TYPE_PROMPT_FILE` |
| 1.4 | `[EXTRACT_FOCUS: …]` in chunk banner from `render_focus_paragraph(doc_type)` | [govcon_chunking.py](../src/extraction/govcon_chunking.py) | **Chunk content** (not `addon_params`) |

**Explicitly NOT doing:** per-chunk `addon_params`; `render_part_d()` remains for tests/reference only.

**Tests:** prompt budget; user prompt has no duplicate guidance; banner includes focus; compact guidance &lt; 6K chars; all 32 type names in index.

---

## Phase 2 — Reprocess + structural gate

1. Clear LLM cache  
2. Re-ingest `mcpp_rfp`  
3. Snapshot → `mcpp_rfp_post_phase1.json`  
4. Run gate checklist + qualitative audits  

### Quantitative gate (Phase 2 → Phase 3)

- [ ] Orphan rate vs pre-epic: down or within **gate margin** (from 0b)
- [ ] Rogue keyword share: down or flat
- [ ] `concept` + `unknown` share: down or flat
- [ ] `infer_lm_links` / `resolve_orphans` counts: down or flat
- [ ] Totals: logged in appendix only

### Qualitative audit rubric

#### A. Document tree audit (n = 20 entities)

**Sample:** Stratified random — 5 paths starting from `document`, 5 from `document_section`, 5 from `evaluation_factor`, 5 from `work_scope_item` (if present). Seed recorded in snapshot JSON.

**For each sample, score 0–2:**

| Score | Criterion |
|---|---|
| 0 | Missing parent `CHILD_OF` / `REFERENCES` when text implies containment |
| 1 | Parent exists but wrong name/identifier vs source chunk |
| 2 | `document` → `document_section` → (`evaluation_factor` \| `work_scope_item`) chain correct; names match RFP verbatim |

**Pass:** ≥ 70% of samples score 2; no sample scores 0 on factor/instruction nodes in solicitation files.

**Verdict template:**

```markdown
### Tree audit — mcpp_rfp post Phase 1
- Sample seed: <seed>
- Scored 2: <n>/20 | Scored 1: <n> | Scored 0: <n>
- Pass: YES/NO
- Failures: <entity_name> — <one-line reason>
```

#### B. Cross-document audit (n = 10 links)

**Sample:** 10 expected PWS `work_scope_item` or `requirement` → RFP `evaluation_factor` pairs from manual checklist (built once from `mcpp_rfp` table of contents, not LLM). Checklist stored in `run-dir/artifacts/mcpp_rfp_audit_checklist.json`.

**For each expected link, score 0–2:**

| Score | Criterion |
|---|---|
| 0 | No path via `EVALUATED_BY`, `ADDRESSES`, or `GUIDES` (keywords or `INFERRED_RELATIONSHIP`) |
| 1 | Edge exists but wrong factor/section pairing |
| 2 | Correct endpoints and relationship semantics |

**Pass:** ≥ 60% score 2 (hard package; threshold reviewed after first run).

**Verdict template:**

```markdown
### Cross-doc audit — mcpp_rfp post Phase 1
- Checklist version: <hash>
- Scored 2: <n>/10 | Scored 1: <n> | Scored 0: <n>
- Pass: YES/NO
- Misses: <pws_entity> → <expected_factor> — <reason>
```

---

## Phase 3 — P chunking trial (0 extra LLM calls)

```
LIGHTRAG_PARSER=pdf:mineru-iteP,doc:mineru-iteP,docx:native-iteP,ppt*:mineru-iteP,xlsx:legacy
```

| LightRAG surface | Content |
|---|---|
| `LIGHTRAG_PARSER` env | Parser/chunk strategy routing |
| Native pipeline | `P` heading-aligned chunks |

Reprocess, snapshot, repeat **same gates + audits**. Rollback `mineru-ite` if tree audit regresses even if totals improve.

---

## Phase 4 — Epic close

- `run-dir/artifacts/mcpp_rfp_epic_results.md` — variance baseline, gate table, audit verdicts, GUIDES split metric
- Update assessment doc with outcomes
- Decision memo: multi-pass justified? `infer_lm_links` slim justified?

**Post-processor:** no algorithm deletion this epic.

### 4b. GraphML / visualization relook (parallel to close — not blocking gates)

Early **NetworkX GraphML** (~1000 nodes, 11–12 entity types) often showed clearer **hub-and-spoke** structure (factor hubs, section clusters) than Capture Workbench. Assessment conclusion: same KG, different **presentation** + likely **sparser extract** — not a reason to revert `GRAPH_STORAGE` to NetworkX.

| Step | Deliverable | Blocks epic? |
|---|---|---|
| **4b.1 Baseline compare** | After Phase 2 re-ingest: open `mcpp_rfp` in Workbench vs optional GraphML export (LightRAG visualizer or Gephi). Record whether factor hubs are visible in **data** or only in **layout**. | No |
| **4b.2 Visual structure rubric** | Human check on `mcpp_rfp`: ≥3 `evaluation_factor` nodes with degree ≥5 and identifiable subfactor/requirement spokes; ≥2 `document_section` neighborhoods. Pass/fail logged in results memo (qualitative, not count gate). | No |
| **4b.3 UI quick wins** (follow-on PR) | `theseus-graph-helpers.js`: edge label = first token of `keywords`; node size = Neo4j `_degree` not subgraph degree; optional preset “Factor hub” (filter `evaluation_factor`, expand 2-hop). | No |
| **4b.4 Diagnosis fork** | If 4b.1 shows flat GraphML **and** flat Neo4j → extract/ontology noise (Phase 1–3 path). If GraphML is hierarchical but Workbench is not → presentation/truncation (4b.3). | Informs Phase 4 memo only |

**Hypothesis under test:** heavy Part D duplication + 32-type prompt increased `concept`/weak edges and flattened Louvain-style clusters; compact prompt should restore both **audit scores** and **incidental legibility** without a separate GraphML backend.

---

## PR stack

| PR | Scope |
|---|---|
| PR-0 | `MAPS_TO`→`GUIDES` docs/Cypher; `mcpp_rfp_audit_checklist.json` scaffold |
| PR-1 | `snapshot_workspace_kg.py` + variance procedure |
| PR-2 | Compact catalog + prompt dedup + example trim |
| PR-3 | Banner `EXTRACT_FOCUS` |
| PR-4 | P chunking + reprocess results + audit verdicts |
| PR-5 (optional) | Graph UI: `keywords` edge labels, global `_degree` sizing, factor-hub preset |

---

## Cost

| Phase | Extra extract calls/chunk |
|---|---|
| 0–3 | **0** (fewer input tokens/chunk after Phase 1) |
| Variance + reprocess | One-time ingest cost |

---

## In-scope vs out-of-scope

**In-scope:** dedup, compact `addon_params` guidance, banner focus, P chunking, snapshot + variance + audit rubrics, GUIDES terminology, `mcpp_rfp` validation, GraphML/visualization **relook** (Phase 4b rubric + diagnosis; optional PR-5 UI).

**Out-of-scope:** multi-pass extract, DIRECTED label promotion, post-processor deletion, `concept` schema gating, per-RFP config files, switching production `GRAPH_STORAGE` to NetworkX for UI reasons.