# LightRAG GovCon Extraction Assessment

**Project:** Theseus (`govcon-capture-vibe`)  
**Date:** 2026-06-13  
**Scope:** Independent first-principles review of LightRAG ingestion, entity/relationship ontology, and extraction prompts for federal solicitation workspaces.

---

## Executive verdict

The system **works** but is **not yet extracting at the level a human capture manager would**. Quality is held up by a large semantic post-processor, strict JSON shaping, and downstream skills — layered on top of LightRAG's **chunk-local, flat-property** graph model.

The bottleneck is not "LightRAG doesn't work." It is a **structural mismatch**:

| What humans do | What the pipeline does today |
|---|---|
| Read whole solicitation structure first (L/M/C/J, attachments, volumes) | Extract per 4K-token chunk with no document-level skeleton |
| Hold cross-section mental model (L↔M, requirement↔CDRL↔CLIN) | Rely on chunk overlap + post-processing to infer missing links |
| Store typed facts (criticality, weight, CLIN ID) as queryable fields | Embed metadata in free-text `description` strings |
| Apply world knowledge to *interpret* ambiguous text | Ask the same chunk LLM to infer win themes / ghost language per chunk |

**Bottom line:** Entity/relationship *definitions* are capture-grade. *Extraction economics* (prompt size, chunk strategy, cross-chunk linking) work against LightRAG's strengths and against human-like comprehension.

---

## Quality metrics principle (not entity/relationship quantity)

**Raw entity count and raw relationship count are not standalone success gauges.**

Higher totals often mean bloat (duplicate umbrellas, `concept` catch-all, forced `RELATED_TO`), not a better source of truth. Lower totals after strict schema or prompt compression can mean higher precision — or harmful recall loss. Counts only matter **in context** with structure and linkage quality.

### Primary signals (use these for epic gates and bakeoffs)

| Signal | What it measures | Good direction |
|---|---|---|
| **Orphan rate** | % entities with zero edges (pre/post post-processor) | Down |
| **Document tree completeness** | `document` → `document_section` → `evaluation_factor` chains auditable in sample | Chains present, named correctly |
| **Cross-document traceability** | PWS `work_scope_item`/`requirement` linked to RFP `evaluation_factor` via `EVALUATED_BY`/`ADDRESSES`/`GUIDES` | Correct links in audit sample |
| **Type precision** | Share of `concept`, `unknown`, rogue rel first-tokens | Down |
| **Quantitative preservation** | Rates, thresholds, CLIN IDs, page limits verbatim in descriptions | Up in spot-check |
| **Post-processor dependency** | Edges added by `infer_lm_links` / `resolve_orphans` | Down (extract carries load) |
| **Downstream usefulness** | Known-answer queries + manual compliance-matrix sample | Subjective pass/fail |

### Secondary / contextual (do not gate on these alone)

| Signal | Caveat |
|---|---|
| `total_entities` | Up can be bloat; down can be precision or loss |
| `total_relationships` | Same; forced edges inflate this |
| Per-type counts | Interpret with audit — e.g. more `requirement` only matters if typed and linked |

### Anti-patterns when evaluating changes

- Treating strict-schema entity drop (−48%) as failure without auditing what was dropped
- Celebrating higher relationship count when rogue keywords (`PWS HIERARCHY`, `UNKNOWN`) rose
- Using dashboard entity totals as the only before/after diff

---

## What LightRAG is optimized for (v1.5.x)

LightRAG is a **dual-level graph-augmented RAG** system:

| Layer | Indexed | Query use |
|---|---|---|
| Chunk vectors | Text (+ multimodal descriptions) | `naive` / `mix` |
| Entity vectors | Entity names + merged descriptions | `local` |
| Relation vectors | Relationship keywords + descriptions | `global` |
| Knowledge graph | Nodes + undirected edges | Degree-weighted ranking, provenance |

### Ingestion pipeline (current library)

```
Raw file → Parser (legacy / native / mineru / docling)
        → Optional VLM (i/t/e)
        → Chunking (F/R/V/P strategies)
        → Per-chunk LLM extraction (+ optional gleaning)
        → Merge/dedupe entities & relations
        → LLM summaries for long descriptions
        → graph_storage + entities_vdb + relationships_vdb
```

### Quality is ~70% ingestion, ~30% query

**Tier 1 knobs:** `EXTRACT_LLM_MODEL`, `ENTITY_EXTRACTION_USE_JSON`, domain `entity_types_guidance`, parser routing, chunk strategy, `MAX_GLEANING`.

**Tier 2 knobs:** `MAX_EXTRACTION_ENTITIES`, merge summary thresholds, `ENABLE_CONTENT_HEADINGS`, extract cache, few-shot examples.

LightRAG does **not** natively provide:

- Typed node properties (only `entity_name`, `entity_type`, `description`, provenance)
- Directed semantic edges with enforced rel types (`keywords` is overloaded)
- Cross-chunk reasoning without merge/post-processing
- Domain world knowledge at extract time (bootstrap + skills are the right layers)

Theseus uses LightRAG correctly as a **retrieval substrate**. Asking it to also be a **structured contract parser** requires orchestration beyond stock LightRAG.

---

## What Theseus got right

1. **Entity catalog** (`prompts/extraction/govcon_entity_types.yaml`) — 32 types, disambiguation, anti-patterns, Shipley framing.
2. **Relationship vocabulary** — 23 extraction-time types; rogue normalization in `schema_support.py`.
3. **JSON extraction + strict schema** — Correct response to parser fragility (`ENTITY_EXTRACTION_STRICT_SCHEMA`).
4. **Role-specific LLMs** — Fast non-reasoning extract model; reasoning model for query.
5. **GovCon chunk banner** — `[GOVCON_DOC: type=...]` suppresses template placeholder pollution.
6. **MinerU multimodal path** — Tables/images as first-class PWS/solicitation content.
7. **Semantic post-processor** — Type cleanup, relationship retyping, L↔M inference, orphan resolution, VDB sync.
8. **Seven JSON few-shot examples** — Especially high-density L↔M shape (Example 7).

AFCAP5 bakeoff (1,203 entities, grounded hybrid/mix queries) proves **usability**, not **optimality**.

---

## Critical gaps (ranked by impact)

### 1. Prompt budget (~40K+ tokens before chunk text)

Measured token estimates:

| Component | ~Tokens |
|---|---|
| Part D in system prompt | 13,084 |
| Part D **again** in user prompt (`---Entity Types---`) | +13,084 |
| Seven JSON few-shot examples | 7,764 |
| Static extraction frame | ~3,500 |
| Chunk input (`CHUNK_SIZE=4096`) | ~4,096 |
| **Total per extract call** | **~41,500** |

Part D is duplicated every chunk. Attention dilutes; extraction shallowens; `concept`/`unknown` and rogue relationship keywords increase.

### 2. `MAX_GLEANING=0`

Disabled in `.env` because MinerU quality improved and gleaning added cost/redundancy. Valid tradeoff if MinerU + prompt quality carry recall — but dense PWS/L/M chunks are where humans re-read; monitor recall metrics before treating gleaning as permanently off.

### 3. Chunk-local extraction vs cross-section reasoning

Cross-section links (L↔M, requirement↔CDRL) are deferred to `infer_lm_links` and overlap luck. Bakeoff symptom: 13 `evaluation_factor` vs 348 `requirement` in AFCAP5 — structure under-represented at extract time.

### 4. Rich ontology, flat storage

Pydantic models (`Requirement.criticality`, etc.) are not persisted on Neo4j nodes. Downstream must re-parse `description` prose or rely on embeddings. Blocks precise Cypher ("all MANDATORY requirements with >500 users").

### 5. Strategic inference at chunk time

`strategic_theme`, `customer_priority`, `pain_point` compete with compliance extraction. Bakeoff: 162 `concept` entities — soft bucket under pressure.

### 6. Terminology drift: `MAPS_TO` vs `GUIDES`

`CONTEXT.md` references `MAPS_TO` for L↔M. Canonical schema and examples use `GUIDES`. Align one canonical type across docs, Cypher, examples, post-processor.

### 7. Heading-aligned chunking (`P` strategy)

Parser routing uses `mineru-ite` without `P`. Fixed 4096-token chunks split structured blocks. LightRAG 1.5 `P` chunking uses heading breadcrumbs — valuable for structured docs, not only UCF.

### 8. Strict schema tradeoff

Tuple baseline: 4,994 entities / 8,603 rels. JSON without schema: 2,614 / 4,245. Strict schema fixes shape; may cap exploratory extraction. Evaluate per workspace.

---

## Entity ontology assessment

### Strengths

- Separates `proposal_instruction` / `evaluation_factor` / `requirement`
- Splits `workload_metric` / `performance_standard` / `requirement`
- Non-UCF equivalents explicit
- Disambiguation rules are practitioner-grade

### Problems

- **Too much for one extract pass** — 32 types × metadata × disambiguation = reference manual, not extraction hint
- **`concept` as pressure-release valve** — needs retirement or strict gating
- **Metadata in description** — not queryable; not validated
- **Orphan nodes** — entities with zero edges; `resolve_orphans` helps but root cause is under-linked chunk extraction

---

## Relationship ontology assessment

### Strengths

23 extraction types cover golden threads: `GUIDES`, `MEASURED_BY`, `SATISFIED_BY`, `TRACKED_BY`, `GOVERNED_BY`, `QUANTIFIES`, `CHILD_OF`.

### Problems

- `keywords` dual role: canonical rel type + embedding text — rogue first tokens (`PWS HIERARCHY`, `UNKNOWN`) hurt global retrieval
- Examples teach `CHILD_OF` to parent sections not always in the same chunk
- L↔M solved twice: extraction examples + `infer_lm_links`
- Undirected edges — direction matters for `GOVERNED_BY`, `SUBMITTED_TO`

---

## Extraction prompt assessment (V8)

### Works

- Shipley persona framing
- Density expectation for L↔M / CDRL / workload
- Anti-forced-relationship hygiene (Example 6)
- Custom merge prompt preserves quantitative detail

### Doesn't

| Issue | Impact |
|---|---|
| Part D duplicated system + user | ~26K wasted tokens/chunk |
| Full catalog + 7 long examples every call | Crowds out RFP text |
| Same prompt for all doc types | Suboptimal for template vs PWS vs FOPR |
| Strategic types in compliance pass | Noise vs fidelity |

---

## LightRAG capability utilization

| Capability | Theseus | Gap |
|---|---|---|
| JSON extraction | Yes | Good |
| Role-specific EXTRACT | Yes | Good |
| `addon_params` entity guidance | Yes | Overloaded (~52K chars) |
| Gleaning | Off (MinerU rationale) | Revisit if recall drops |
| `P` heading chunking | Not in routing | Section integrity |
| `mix` + rerank | Available | Good |
| Merge + summarize | Custom prompt | Good |
| `rebuild_knowledge_from_chunks` | Not used for tuning | Slow iteration |
| RAGAS / retrieval eval | Not wired | No systematic metric |

---

## Recommended target architecture

### Three-layer source of truth

```
Layer 1 — Structural ingest
  Parse → heading-aware chunks → skeleton pass → detail pass → cross-ref pass

Layer 2 — Typed KG
  Neo4j (typed properties + hierarchy) ← sync → LightRAG VDB (retrieval)

Layer 3 — Reasoning
  Bootstrap doctrine + Capture Chat (mix) + agentic skills
```

### Document-shaped KG (target hierarchy)

The capture graph is **not** volume-centric. Volumes sit **below** factors in the proposal/evaluation tree. Cross-document traceability (PWS task → RFP evaluation criterion) happens at the **document and section** layers — where humans draw their maps.

**Canonical hierarchy (top → bottom):**

```
WORKSPACE (one RFP package)
│
├─ DOCUMENT (document)                    e.g. Solicitation/RFP, PWS, Attachment J, CDRL Exhibit, Amendment
│   ├─ CHILD_OF
│   ├─ SECTION / AREA (document_section)  e.g. Section M, Section 8, Part III, Attachment 1 body
│   │   ├─ CHILD_OF
│   │   ├─ FACTOR / CRITERION (evaluation_factor)   M-side scoring tree (factor → subfactor → element)
│   │   │   ├─ CHILD_OF
│   │   │   ├─ PROPOSAL CONTAINER (proposal_volume)  Volume I/II — when named
│   │   │   │   ├─ CHILD_OF
│   │   │   │   └─ INSTRUCTION (proposal_instruction)  L-side rules scoped to that volume/factor
│   │   │   └─ SATISFIED_BY / EVALUATED_BY → deliverables, requirements (cross-layer)
│   │   └─ WORK PACKAGE (work_scope_item) / TASK area inside PWS/SOW
│   │       └─ CHILD_OF → REQUIREMENT, DELIVERABLE, WORKLOAD_METRIC, …
│   └─ REFERENCES / GUIDES / APPLIES_TO (cross-section, within same document)
│
└─ CROSS-DOCUMENT EDGES (the human “map” — highest value)
    PWS work_scope_item  ──EVALUATED_BY / ADDRESSES──►  RFP evaluation_factor
    PWS requirement      ──GOVERNED_BY──────────────────►  RFP clause / regulatory_reference
    RFP deliverable      ──TRACKED_BY───────────────────►  CDRL exhibit deliverable
    proposal_instruction ──GUIDES────────────────────────►  evaluation_factor
```

**Entity types already in the catalog for this shape:** `document`, `document_section`, `evaluation_factor`, `proposal_volume`, `proposal_instruction`, `work_scope_item`, `requirement`, `deliverable`, `amendment`.

**Relationship types for the map:** `CHILD_OF` (containment), `GUIDES` / `EVALUATED_BY` (L↔M), `REFERENCES` (explicit cross-refs), `APPLIES_TO` / `ADDRESSES` (PWS obligation scoped to eval criterion), `GOVERNED_BY`, `TRACKED_BY`.

UCF (Sections L/M) and non-UCF (Section 8, Table 1, Factor 1) differ only in **labels** — not in graph levels. Pattern-based `document_section` identifiers carry the agency-specific naming.

### Regression baseline

Use **`mcpp_rfp`** workspace (large, complex MCPP II package) — not AFCAP5 — for epic-branch before/after comparisons. Reprocess on the epic branch and diff against the current baseline snapshot using **quality signals** (orphan rate, tree audit, cross-doc links, type precision) — not raw entity/relationship totals alone. See [EPIC_EXTRACT_PROMPT_COMPRESSION.md](EPIC_EXTRACT_PROMPT_COMPRESSION.md).

---

## Prioritized recommendations

### Short-term (days)

1. **Remove duplicate Part D** from user prompt — keep one injection site.
2. **Compress active guidance** — full catalog offline; per-chunk inject ~2–4K token *active slice* (see Domain intelligence section below).
3. **Fix `MAPS_TO` / `GUIDES`** — single canonical L↔M type everywhere.
4. **Retire or gate `concept`** — map to specific types or `document_section`; forbid in strict schema except explicit government-obligation patterns.
5. **Trial `P` chunking** on MinerU PDFs — `mineru-iteP`; measure orphan rate and `CHILD_OF` quality on non-UCF FOPR.
6. **Orphan KPI** — track % entities with degree 0 pre/post post-processor per workspace.

### Medium-term (weeks)

1. **Multi-pass extraction** (Theseus orchestration, not stock LightRAG feature):
   - Pass A: skeleton (`document`, `document_section`, `proposal_volume`, `evaluation_factor`, `proposal_instruction`, hierarchy)
   - Pass B: obligations (`requirement`, `deliverable`, `workload_metric`, `clause`, commercial types)
   - Pass C: cross-links (`GUIDES`, `GOVERNED_BY`, `TRACKED_BY`) with section context injected
2. **Structured property sidecar** — parse metadata from descriptions into Neo4j properties post-extract.
3. **L↔M synthetic chunk** — concatenate detected instruction + evaluation blocks for one dedicated extract call.
4. **Shrink post-processor** as extract quality improves — keep quality gates; drop redundant algos.

### Long-term

1. Neo4j as source of truth; VDB as retrieval index.
2. Golden-set eval harness (entity recall/precision per doc type).
3. Deterministic parsers for CLIN/staffing XLSX + LLM for narrative PDFs.

---

## Domain intelligence without a 40K-token prompt

LightRAG does **not** ship dynamic per-type passes. Theseus can add them **above** LightRAG.

### Progressive disclosure (agnostic — no “read the solicitation first”)

**Concern:** Doc-type routing sounds like per-customer tuning or pre-reading the package to learn structure.

**Answer:** Progressive disclosure uses signals **already computed during ingest** — no human pre-read, no per-solicitation config files.

| Signal | When computed | Cost | What it tells extract |
|---|---|---|---|
| **Filename + file role** | Upload/scan | Zero | `Attachment 1 - PWS.pdf` → PWS patterns; `Amendment 0003.pdf` → delta patterns |
| **`govcon_doc_type` banner** | Chunk time (classifier on first 5KB + filename) | Zero | `solicitation` / `pws` / `template` / `cdrl_exhibit` |
| **MinerU heading breadcrumb** | Parse time | Zero | `Section 8` / `Factor 1` / `Task 3.2` — LightRAG `ENABLE_CONTENT_HEADINGS` |
| **Pass 1 skeleton entities** | After first extract batch on that **file** | One cheap pass per file | Known `document` + `document_section` + factor tree for Pass 2 context injection |

This is **not** “configure Theseus for MCPP vs AFCAP.” It is **five doc-type families** that exist in every federal package (solicitation body, PWS/SOW, CDRL exhibit, template, amendment). Agency variation changes **labels inside chunks**, not which family the file belongs to.

**Full 32-type ontology stays in YAML** as source of truth. Per-chunk prompt carries:

1. Compressed type index (all 32 names + one-line role) — ~800 tokens
2. **Focus paragraph** for the doc-type family (~200 tokens) — “prioritize evaluation_factor hierarchy” vs “prioritize requirement + workload_metric”
3. Top 6 disambiguation pairs (~800 tokens)
4. **One** few-shot example matching doc-type family (~2K tokens)

Total target: **~4–5K tokens** domain guidance vs **~26K today** (duplicate Part D alone).

### Pattern A — Compress only (Phase 1)

Dedup Part D + compressed index. Same single pass. **No routing risk.**

### Pattern B — Doc-type focus paragraphs (Phase 1b)

Same 32 types always **allowed** in schema; focus text **prioritizes** types common in that family without **forbidding** others. A PWS chunk that mentions a clause still extracts `clause`.

### Pattern C — Multi-pass per file (Phase 2)

| Pass | Scope | LLM calls | Extract focus |
|---|---|---|---|
| **1 — Skeleton** | Once per **file** after parse | ~1× chunk count with **short** skeleton prompt | `document`, `document_section`, `evaluation_factor` tree, `proposal_volume`, `CHILD_OF` only |
| **2 — Detail** | Same chunks | ~1× chunk count | Full types; inject Pass 1 entity names for this file as “known structure” |
| **3 — Cross-doc** | Once per **workspace** after batch | **1 LLM call** (or small set) | Link PWS `work_scope_item` / `requirement` → RFP `evaluation_factor`; uses entity lists, not full re-read |

Pass 3 replaces much of `infer_lm_links` + orphan resolution with one structured linking call.

### Pattern D — Bootstrap + skills for world knowledge

- **Bootstrap:** FAR patterns, evaluation frameworks (already done)
- **Extract:** Facts from solicitation text only
- **Skills:** Win themes, ghost language, discriminators — workspace-level synthesis

### Hybrid path (recommended — between A and B)

**Not a binary choice.** Staged rollout on `mcpp_rfp` epic branch:

| Stage | Extract calls | What changes |
|---|---|---|
| **0 — Baseline** | 1×/chunk (today) | Snapshot `mcpp_rfp` metrics |
| **1 — Compress** | 1×/chunk | Dedup Part D + compressed guidance; **0 extra calls** |
| **2 — Doc-type focus** | 1×/chunk | `addon_params` focus paragraph from `govcon_doc_type`; **0 extra calls** |
| **3 — Skeleton pass** | 2×/chunk | Pass 1 short prompt + Pass 2 detail with structure context |
| **4 — Workspace link** | 2×/chunk + 1 batch | Pass 3 cross-doc; retire most `infer_lm_links` |

**Gate between stages:** Only advance if `mcpp_rfp` improves **quality signals** (orphan rate, manual tree audit, cross-doc link correctness, type precision) — never if raw entity/relationship totals alone increased.

---

## Non-UCF and heading-aligned chunking

UCF Sections A–M are one **pattern family**. Non-UCF uses others:

- Numbered memorandum paragraphs (FOPR)
- "Section 8" / "Factor 1" / "Table 1" headings
- Attachment / Appendix / Annex IDs
- Volume I / II / III containers

`P` chunking uses **detected headings from MinerU**, not UCF letters. `document_section` entities should use **verbatim identifiers** (`Section 8`, `M.2`, `Attachment 1`) — the ontology is already pattern-based. Heading alignment helps **all** formats with visual structure.

---

## Gleaning decision record

**Current:** `MAX_GLEANING=0` — MinerU parse quality makes second pass redundant; cost/bloat concern.

**Revisit when:**

- Orphan rate rises after prompt slimming
- Recall audit shows systematic misses on dense PWS tables
- New doc type (sparse FOPR) under-extracts evaluation structure

**Alternative to global gleaning:** targeted second pass only on chunks where Pass 1 entity count < threshold or chunk is tagged `solicitation` + contains "evaluation" / "factor" signals.

---

## Post-processor philosophy

Trend: shrink as MinerU/LightRAG improve. **Keep while quality needs it:**

| Phase | Keep? | Rationale |
|---|---|---|
| Entity type cleanup | Yes | Until `concept`/`unknown` near zero |
| Relationship retyping | Yes | Until rogue keywords near zero |
| `infer_lm_links` | Maybe | Shrink if L↔M synthetic pass works |
| `resolve_orphans` | Yes until orphan KPI < 5% | Symptom of chunk extraction gaps |
| `infer_document_structure` | Yes | Zero LLM cost; regex cross-refs |
| VDB sync | Yes | Neo4j discoveries must be retrievable |

Quality over cost when tradeoff is clear.

---

## Experiments (evidence before tuning)

**Workspace:** `mcpp_rfp` only for epic-branch comparisons. Snapshot baseline before branch work.

| Experiment | Hypothesis | Success metric (not raw totals) |
|---|---|---|
| Remove duplicate Part D | Better attention on chunk text | Orphans ↓; tree audit pass; `unknown`/`concept` ↓ |
| Doc-type focus paragraphs | Precision ↑; no per-RFP tuning | Audit sample typing accuracy; `concept` ↓ |
| `mineru-iteP` vs `mineru-ite` | Section integrity | `CHILD_OF` chains valid in audit; orphans ↓ |
| Pass 1 skeleton (per file) | Document-level tree before detail | Sample paths: document → section → factor complete |
| Pass 3 workspace cross-doc | PWS→RFP map without per-chunk cost | Correct cross-doc links in audit (not edge count alone) |
| Retire `concept` (strict gating) | Forced specific typing | Audit misclass rate; `concept` share ↓ |
| Orphan KPI dashboard | Visibility | % degree-0 pre/post post-processor |

Clear `kv_store_llm_response_cache.json` between prompt experiments.

---

## Open questions (owner decisions)

1. Canonical L↔M rel type: `GUIDES` (current) or restore `MAPS_TO` in schema?
2. Stage gate: advance to Pass 1 skeleton only if Stage 1–2 compress + doc-type focus improves `mcpp_rfp` audit?
3. Neo4j typed properties: which fields first (`criticality`, `weight`, `clin_id`, `hierarchy_level`)?
4. Target orphan rate SLA (e.g. < 5% entities with zero edges post-ingest)?
5. Cross-doc rel types: `EVALUATED_BY` vs `ADDRESSES` for PWS task → RFP factor (may need both semantics)?

---

## LightRAG native vs Theseus orchestration

### What LightRAG has always done (core design, since early versions)

Stock LightRAG ingest is **one extraction call per chunk** (plus optional **gleaning**):

| Mechanism | Native LightRAG? | What it does |
|---|---|---|
| **Single extract per chunk** | Yes — core design | LLM reads chunk → emits entities + relationships → merge into graph |
| **Gleaning** (`MAX_GLEANING`, `entity_continue_extraction_*`) | Yes — longstanding | Second+ pass on the **same chunk**, same prompt family, “what did you miss?” |
| **Merge / summarize across chunks** | Yes | Same entity name across chunks → merged description |
| **Custom `entity_types_guidance`** | Yes | One guidance string per run (not per-chunk dynamic routing in stock API) |
| **`addon_params`** | Yes (evolved) | Static dict at `LightRAG()` init — Theseus can **mutate per chunk** in a wrapper (not stock behavior) |
| **`rebuild_knowledge_from_chunks()`** | Yes (utility) | Re-run extraction from stored chunks without re-parsing PDFs — useful for prompt tuning |

LightRAG has **never** shipped:

- Different extraction prompts per doc type (Theseus addition)
- Pass 1 skeleton → Pass 2 detail (Theseus addition)
- Workspace-level cross-doc linking pass (Theseus addition — today partially `infer_lm_links`)

### What is newer in LightRAG 1.5.x (since ~v1.12 era)

- JSON extraction mode (recommended over tuple delimiters)
- Role-specific LLMs (`EXTRACT`, `KEYWORD`, `QUERY`, `VLM`)
- Native parser pipeline (MinerU / Docling / native DOCX)
- Chunk strategies **F / R / V / P** (heading-aligned `P` is new relative to old fixed-only chunking)
- Section context injection (`ENABLE_CONTENT_HEADINGS`)
- Reranker integration with `mix` mode
- `ENTITY_TYPES` env removed → `entity_types_guidance` / YAML profiles

**Multi-pass with different questions per pass is a Theseus orchestration pattern**, not a LightRAG product feature. Gleaning is the only native “second pass,” and it repeats the same task — not skeleton-then-detail.

---

## Post-processing: when and what changes

### Principle: **extract first, slim second — but measure throughout**

Post-processing exists because extraction leaves gaps. Improving extraction **reduces** post-processing need; it does not eliminate it on day one.

### Epic sequencing

| Phase | Main processing (extract) | Post-processing | Rationale |
|---|---|---|---|
| **0 — Baseline** | Snapshot current `mcpp_rfp` | Snapshot orphan %, algo output counts (`infer_lm_links`, `resolve_orphans`) | Need before/after |
| **1 — Compress prompt** | Dedup Part D, compressed index, doc-type focus | **No changes** — keep all phases running | Isolate extract effect |
| **2 — Measure** | Reprocess `mcpp_rfp` | Compare post-processor stats vs baseline | If orphans ↓, extraction improved |
| **3 — Parser (`P` chunking)** | `mineru-iteP` trial | **No changes** yet | Structure edges may improve without PP touch |
| **4 — Gate review** | Audit document tree + cross-doc sample | Decide which algos are still earning their cost | Data-driven cut list |
| **5 — Extract Pass 3 (cross-doc)** | One workspace linking call at end of batch | **Replace or shrink** `infer_lm_links` | Avoid duplicate L↔M LLM work |
| **6 — Post-processor slim** | Pass 1 skeleton if still needed | Remove/disable algos metrics prove redundant | Quality-stable cost cut |

### Post-processor components — keep, shrink, or delete (decision rubric)

| Component | Phase 1–3 | After extract improvements | Notes |
|---|---|---|---|
| **Entity type cleanup** (`table`→typed, `#` prefix strip) | **Keep** | Keep until MinerU/VLM stops emitting `table` type | Mostly deterministic |
| **UNKNOWN retyping** (LLM batch) | **Keep** | **Shrink** as `unknown` → 0 | Extraction target |
| **Name canonicalization** (eval factors) | **Keep** | **Keep** — cheap, high value | Punctuation drift |
| **VDB metadata sync** | **Keep** | **Keep** — required for query parity | Non-negotiable |
| **Relationship retyping** (`RELATED_TO` → canonical) | **Keep** | **Shrink** as rogue keywords ↓ | Prompt + schema fix |
| **`infer_document_structure`** (regex) | **Keep** | **Keep** — zero LLM cost | CDRL/section refs |
| **`infer_lm_links`** (LLM) | **Keep** (for now) | **Delete or replace** when Pass 3 cross-doc works | Expensive overlap with extract goal |
| **`resolve_orphans`** (LLM) | **Keep** (for now) | **Delete** when orphan KPI < ~5% pre-PP | Symptom fix |
| **VDB sync (inferred rels)** | **Keep** | **Keep** | Neo4j → retrievable |

**Do not delete post-processing before main processing improvements are measured.** Run both in parallel during Stages 1–3 so regressions are visible. Slim post-processing only when `mcpp_rfp` metrics show extraction carries the load.

### What “delete post-processing” actually means

Not zero post-processing — a **minimal integrity pass**:

1. Deterministic type/relationship normalization (no LLM)
2. VDB sync
3. Optional regex structure inference

Target end state: **no LLM post-processing** unless a quality gate fails (orphan rate spike, cross-doc edge count below threshold).

---

## References

- Entity catalog: `prompts/extraction/govcon_entity_types.yaml`
- Extraction prompt: `prompts/govcon/extraction.py`
- JSON examples: `prompts/entity_type/govcon.yaml`
- Runtime: `src/server/native_lightrag_runtime.py`
- Post-processor: `src/inference/semantic_post_processor.py`
- Bakeoff: `docs/NATIVE_QUALITY_BAKEOFF_AFCAP5_ISR.md`
- Context: `CONTEXT.md`