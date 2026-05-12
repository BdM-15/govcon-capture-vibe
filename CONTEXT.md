# Theseus

Ontology-backed RAG system that ingests federal RFPs into a knowledge graph and answers govcon capture questions through a Shipley-methodology mentor persona.

## Language

### Core system concepts

**Workspace**:
An isolated knowledge graph + vector database for exactly one RFP. Lives at `rag_storage/<name>/`. All entities, relationships, and embeddings are workspace-scoped. Created manually: user names the workspace, switches to it via the UI, then uploads documents through the Documents page. Not auto-created on first upload.
_Avoid_: project, environment, instance.

**Knowledge graph (KG)**:
The Neo4j graph database holding all entities and relationships for a workspace. Always Neo4j — NetworkX is not used. Accessed via `src/core/neo4j_io.py`. The semantic post-processor reads from and writes to this graph. Skills query it via the `kg_query(cypher)` and `kg_entities(types[])` tools.
_Avoid_: "the graph" alone (ambiguous between the KG and GraphML files on disk).

**Ingest pipeline**:
The 7-phase sequence that turns a raw RFP document into graph data: upload -> MinerU parse -> multimodal analysis -> LightRAG chunking -> entity extraction -> relationship extraction -> semantic post-processing trigger.
_Avoid_: "the pipeline" (ambiguous -- see Flagged ambiguities).

**Semantic post-processor**:
The 6-phase inference pass that runs exactly once after a batch completes. Phases: (1) data loading, (2) entity normalization, (3) relationship normalization, (4) relationship inference, (5) workload enrichment (optional), (6) VDB sync. Lives in `src/inference/`.

Phase 4 runs 3 **inference algorithms** in parallel (`src/inference/algorithms/`): `infer_lm_links` (L↔M cross-document linking), `infer_document_structure` (heuristic regex, zero LLM cost), `resolve_orphans` (reconnect unlinked entities). Algorithms are the mechanisms inside Phase 4; phases are the overarching structure of the whole pass.
_Avoid_: "post-processing pipeline" (pipeline is overloaded -- see Flagged ambiguities). Never conflate phases with algorithms.

**Batch**:
A user-defined group of documents uploaded together for which exactly one semantic post-processor run is guaranteed. Auto-detected by an idle-timeout window (`BATCH_TIMEOUT_SECONDS`): when no new document completes for that duration, the batch is declared complete and post-processing fires once. Without batching, uploading N documents would trigger N post-processor runs -- each exponentially more expensive as the graph grows.
_Avoid_: job, run, upload session.

**Skill run directory**:
Per-invocation working directory for one skill execution. Path: `rag_storage/<workspace>/skill_runs/<skill>/<YYYYMMDD_HHMMSS_slug>/`. Contains `artifacts/` (skill output files), `tool_outputs/` (raw tool call results), `run.md` (run envelope), `transcript.json` (tool call log). Scoped to one workspace + one skill execution. Created by `SkillRunStore.create_run_dir()`.
_Avoid_: run-dir, output dir, workspace.

**Inputs directory** (`inputs/<workspace>/`):
Filesystem staging area for batch ingest. Drop PDFs/DOCX here, then call `POST /scan-rfp` to process all unprocessed files in the folder sequentially. Already-processed files are skipped. The server also copies uploaded files here when using the Documents UI (`/documents/upload`). `inputs/__enqueued__/` is a reserved name (never written to by any code — skip it).
_Avoid_: upload folder, queue (there is no queue; scan is synchronous per-file in a background task).

**Bootstrap**:
One-time pre-seeding of a workspace's knowledge graph with curated govcon domain knowledge (Shipley methodology, FAR patterns, evaluation frameworks) before any RFP documents are uploaded. Triggered automatically at server startup via `maybe_bootstrap_ontology()` in `src/server/rag_post_init.py`. Gate: `AUTO_BOOTSTRAP_ONTOLOGY` env var (default `true`). Fresh workspace (no marker) + env enabled -> ontology entities/relationships become the initial KG foundation. `.ontology_bootstrap` marker written after success; present -> skip on subsequent startups. `ONTOLOGY_BOOTSTRAP_FORCE=true` re-seeds even if marker exists.
_Avoid_: initialization (overloaded with server startup), seed.

**Entity catalog**:
The YAML-driven registry of 33 govcon entity types at `prompts/extraction/govcon_entity_types.yaml`. Single source of truth -- `VALID_ENTITY_TYPES` in `src/ontology/schema.py` is derived from it at import time.
_Avoid_: entity types list, entity schema.

**Canonical relationship types**:
The 35 fixed relationship type strings defined in `src/ontology/schema.py -> VALID_RELATIONSHIP_TYPES`. Every relationship in the knowledge graph must use one of these as its `keywords` first token.
_Avoid_: edge types, link types, relationship schema.

### Prompt systems

**Extraction prompt** (System 1):
The LightRAG prompt that extracts entities and relationships from text chunks during the ingest pipeline. Lives at `prompts/govcon/extraction.py -> build_v8_system_prompt()`.
_Avoid_: "the prompt" (three prompt systems exist -- always qualify which one).

**Query prompt** (System 2):
The RAG response prompt that answers user queries through the Shipley mentor persona. Lives at `prompts/govcon/query.py`.

**Multimodal prompt** (System 3):
The VLM prompt for analyzing tables, images, and equations extracted by MinerU. Lives at `prompts/multimodal/govcon_multimodal_prompts.py`.

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
> **Domain expert:** "Which pipeline? The ingest pipeline (the 7-phase doc processing) or the semantic post-processor (the 6-phase inference pass)? Both exist. The ambiguity is real -- see Flagged ambiguities."

> **Dev:** "The L-to-M mapping query isn't finding anything -- are the requirements in the wrong entity type?"
>
> **Domain expert:** "L-to-M mapping is `proposal_instruction` -> `evaluation_factor` via `MAPS_TO`. Requirements are a different entity type -- they represent contractor obligations after award, not proposal structure. Check whether the extraction prompt tagged the Section L items as `proposal_instruction` or accidentally as `requirement`."

## Flagged ambiguities

- **"pipeline"** -- resolved. `src/server/document_processing.py` docstring now says "ingest pipeline"; `src/inference/semantic_post_processor.py` docstring and banner now say "semantic post-processor." Never use bare "pipeline" in new code, issue titles, or test names.
- **"entity"** -- `entity` is used generically inside LightRAG internals; do not use it as a domain term in new code, issue titles, or test names. Always use the specific entity catalog type (requirement, evaluation_factor, proposal_instruction, etc.).
- **"prompt"** -- resolved by naming convention: each prompt module names itself by system (extraction.py, query.py, multimodal prompts). Always qualify: "extraction prompt", "query prompt", or "multimodal prompt." Never write bare "prompt" when the system matters.
