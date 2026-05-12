# Context

Domain vocabulary for Project Theseus — an ontology-based RAG system for federal RFP analysis.

Use this glossary when naming code, writing issues, proposing refactors, writing tests, or any output that touches the codebase. Prefer these terms; avoid the synonyms listed under _Avoid_.

---

## Architecture vocabulary

**Module**
Anything with an interface and an implementation. Scale-agnostic — applies equally to a function, class, file, or vertical slice.
_Avoid_: unit, component, service.

**Interface**
Everything a caller must know to use a module correctly: type signature, invariants, ordering constraints, error modes, required configuration.
_Avoid_: API, signature (too narrow).

**Depth**
Leverage at the interface — how much behaviour a caller exercises per unit of interface they learn. A deep module has a large implementation behind a small interface.

**Seam**
A place where behaviour can be changed without editing the calling code. Where an interface lives.
_Avoid_: boundary (overloaded with DDD's bounded context).

**Adapter**
A concrete implementation that fills a seam and satisfies an interface.

**Leverage**
What callers gain from depth: more capability per unit of interface they must learn.

**Locality**
What maintainers gain from depth: changes, bugs, and knowledge concentrate at one place.

---

## Govcon domain vocabulary

### Core system

**Workspace**
An isolated knowledge graph + vector store for one RFP. Lives under `rag_storage/<name>/`. Each workspace is independent: different entities, relationships, embeddings.

**Pipeline**
The 7-phase document processing sequence: upload → MinerU parse → multimodal analysis → LightRAG chunking → entity extraction → relationship extraction → semantic post-processing.

**Semantic post-processing**
6-phase pipeline that runs after batch ingestion: data loading → entity normalization → relationship normalization → relationship inference → workload enrichment → VDB sync.

**Extraction prompt (System 1)**
The LightRAG prompt that extracts entities and relationships from text chunks. Lives in `prompts/govcon_prompt.py` → `_build_v8_system_prompt()`.

**Query/response prompt (System 2)**
The LightRAG RAG response prompt with Shipley mentor persona. Lives in `prompts/govcon_prompt.py` → `rag_response`.

**Multimodal prompt (System 3)**
The VLM prompt for tables, images, and equations from MinerU. Lives in `prompts/multimodal/govcon_multimodal_prompts.py`.

### Entity ontology

33 entity types defined in `prompts/extraction/govcon_entity_types.yaml` and exported as `src/ontology/schema.py → VALID_ENTITY_TYPES`. Key types:

- `requirement` — a stated or implied obligation the offeror must meet
- `evaluation_factor` — a criterion used to evaluate proposals (Section M)
- `proposal_instruction` — a direction to offerors on how to structure or submit (Section L)
- `deliverable` — a product or artifact the awardee must provide
- `clause` — a FAR/DFARS clause incorporated by reference or full text
- `clin` — contract line item number
- `performance_standard` — measurable threshold for a deliverable or task
- `win_theme` — a discriminator the proposal team intends to emphasize
- `compliance_artifact` — evidence that a requirement is met
- `company` — a bidder, incumbent, or teaming partner

_Avoid_: "entity" as a generic synonym for any of the above — always use the specific type.

### Relationship ontology

35 canonical relationship types defined in `src/ontology/schema.py → VALID_RELATIONSHIP_TYPES`. Key types:

- `MAPS_TO` — links a `proposal_instruction` (Section L) to an `evaluation_factor` (Section M)
- `SATISFIES` — links a `compliance_artifact` to a `requirement`
- `CHILD_OF` — structural parent/child between sections or work items
- `REFERENCES` — a clause or requirement references another entity
- `SCORED_BY` — an evaluation factor scored by a criterion

### Shipley methodology terms

- **Hot button** — a customer priority signal in the RFP text
- **Ghost language** — language written to favour a specific bidder
- **Win theme** — a proof-point-backed discriminator tied to a hot button
- **FAB chain** — Feature → Advantage → Benefit chain for a win theme
- **Proof point** — quantified evidence supporting a claim
- **Compliance matrix** — L↔M cross-reference showing every instruction is addressed

---

## Architectural decisions

ADRs live in `docs/adr/` (system-wide). None yet — this directory is a placeholder for decisions resolved via `/grill-with-docs`.
