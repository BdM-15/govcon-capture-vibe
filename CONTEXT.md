# Theseus

Ontology-backed RAG system that ingests federal RFPs into a knowledge graph and answers govcon capture questions through a Shipley-methodology mentor persona.

## Language

### Core system concepts

**Workspace**:
An isolated knowledge graph + vector database for exactly one RFP. Lives at `rag_storage/<name>/`. All entities, relationships, and embeddings are workspace-scoped.
_Avoid_: project, environment, instance.

**Ingest pipeline**:
The 7-phase sequence that turns a raw RFP document into graph data: upload -> MinerU parse -> multimodal analysis -> LightRAG chunking -> entity extraction -> relationship extraction -> semantic post-processing trigger.
_Avoid_: "the pipeline" (ambiguous -- see Flagged ambiguities).

**Semantic post-processor**:
The 6-phase inference pass that runs automatically after a batch completes: data loading -> entity normalization -> relationship normalization -> relationship inference -> workload enrichment -> VDB sync. Lives in `src/inference/`.
_Avoid_: "post-processing pipeline" (pipeline is overloaded -- see Flagged ambiguities).

**Bootstrap**:
One-time pre-seeding of a workspace's knowledge graph with curated govcon domain knowledge (Shipley methodology, FAR patterns, evaluation frameworks) before any RFP documents are uploaded. Controlled by `.ontology_bootstrap` marker file per workspace.
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

- **"pipeline"** was used to mean both the 7-phase ingest sequence and the 6-phase post-ingest inference pass -- resolved: use **ingest pipeline** for the former and **semantic post-processor** for the latter. Never use bare "pipeline."
- **"entity"** is used generically in Python code (e.g., LightRAG internals) but must never be used as a domain term in issue titles, test names, or refactor proposals -- always use the specific catalog type (requirement, evaluation_factor, etc.).
- **"prompt"** without qualification is ambiguous -- three independent prompt systems exist (extraction, query, multimodal). Always say which one.