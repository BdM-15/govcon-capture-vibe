# Path B Implementation Plan: Ontology-Guided LightRAG Integration

**Date**: October 3, 2025  
**Branch**: 002-lighRAG-govcon-ontology  
**Status**: Ready to implement

---

## Context: What We Learned from Path A

### The Problem

In our exploratory Phase 1 work (Path A), we built custom preprocessing outside the LightRAG framework:

- Created `ShipleyRFPChunker` with 170+ lines of regex-based section parsing
- Preprocessed documents BEFORE LightRAG saw them
- Generated malformed section identifiers ("RFP Section J-L", "Attachment L") that don't exist in Uniform Contract Format
- Created parallel structures instead of integrating with LightRAG's existing capabilities

### The Insight

**Generic LightRAG cannot understand government contracting concepts**. It has never seen RFPs, doesn't know what CLINs are, can't distinguish "shall" requirements from suggestions, and won't recognize Section L↔M relationships. Our regex preprocessing made things worse by corrupting the input.

**The Real Problem**: We used LightRAG's generic entity extraction (trained on general text) without teaching it government contracting domain knowledge.

### What Actually Works

- ✅ LightRAG's semantic extraction framework is robust and extensible
- ✅ LightRAG accepts custom entity types via `addon_params["entity_types"]`
- ✅ Requirement-based splitting prevents timeouts
- ✅ Ontology module (`src/core/ontology.py`) is well-designed with EntityType/RelationshipType enums

### The Correct Approach (Path B)

**Modify LightRAG's extraction engine by injecting government contracting ontology, teaching it domain-specific concepts it would never learn from generic processing.**

Key modifications:

1. **Inject ontology entity types** into LightRAG's extraction prompts
2. **Add government contracting examples** (CLINs, Section M factors, FAR clauses)
3. **Constrain relationships** to valid patterns (L↔M, requirement→evaluation)
4. **Validate extractions** against ontology to ensure domain accuracy

---

## Objective

**Modify LightRAG's extraction capabilities with government contracting ontology** to transform generic document processing into specialized federal procurement intelligence. We inject domain knowledge into LightRAG's prompts to teach it concepts it would never extract using generic entity types.

**Critical**: This is NOT about using LightRAG "as-is" and hoping. We **actively modify** what LightRAG extracts by:

- Replacing generic entity types ("person", "location") with domain types ("CLIN", "REQUIREMENT", "EVALUATION_FACTOR")
- Adding government contracting examples to teach Section L↔M relationships
- Constraining relationships to valid patterns (SOW→Deliverable, Section M→Evaluation Criteria)
- Post-processing to ensure extractions match ontology

### Success Criteria

- [ ] Sections extracted as individual entities (Section A, Section B, ..., Section M) - NOT merged ("J-L")
- [ ] Entities constrained to **government contracting ontology types** (CLIN, FAR_CLAUSE, not generic "person")
- [ ] Relationships constrained to **valid government contracting patterns** (L↔M, not random connections)
- [ ] Max 25 entities per chunk (avg 10-15) via **constrained extraction prompts**
- [ ] Zero invalid entity type errors (ontology validation working)
- [ ] Zero "17" entity cleaning errors (proper entity formatting)
- [ ] Processing time <60 minutes for full RFP
- [ ] Knowledge graph reflects **government contracting domain** (not generic document structure)

---

## Architecture Overview

### Current State (Path A - To Be Archived)

```
RFP → [ShipleyRFPChunker - Regex Parsing] → [Malformed Chunks] → [LightRAG] → [Invalid KG]
      ↑ CUSTOM PREPROCESSING (170+ lines)    ↑ "J-L", "J-Line"    ↑ Extracts garbage
```

### Target State (Path B - Ontology-Modified LightRAG)

```
RFP → [Simple Chunking] → [Clean Chunks] → [MODIFIED LightRAG] → [Valid KG]
      ↑ Basic strategy      ↑ Proper sections  ↑ Ontology types injected    ↑ Domain-specific
                                                ↑ Gov contracting examples
                                                ↑ Constrained relationships
                                                ↑ Post-validation
```

**Key Difference**: LightRAG's extraction engine is **modified** with government contracting knowledge, not used generically.

---

## Implementation Plan

### Phase 1: Codebase Cleanup 🧹

**Goal**: Remove Path A artifacts, preserve learnings

#### 1.1 Archive Path A Code

```bash
# Create archive directory
mkdir -p archive/path_a_exploratory_work

# Archive custom chunking (keep as reference)
mv src/core/chunking.py archive/path_a_exploratory_work/
mv test_phase1_optimizations.py archive/path_a_exploratory_work/

# Keep ontology.py - it's good! Just needs integration
# Keep src/core/lightrag_chunking.py - simplify, don't delete
```

#### 1.2 Files to Keep (Core Framework)

- ✅ `src/core/ontology.py` - Well-designed, will integrate with LightRAG prompts
- ✅ `src/models/rfp_models.py` - PydanticAI models for RFP domain
- ✅ `src/agents/rfp_agents.py` - Agent definitions
- ✅ `docs/` - Shipley guides, ontology reference, analysis documents
- ✅ `prompts/` - Shipley methodology prompt templates

#### 1.3 Clean Up lightrag_chunking.py

**Current**: 200+ lines with RFP-aware chunking and requirement splitting  
**Target**: ~50 lines with simple strategy, let LightRAG handle structure

```python
# Simplified chunking function
def simple_chunking_func(text: str, file_path: str = None, metadata: dict = None) -> list[str]:
    """
    Simple chunking strategy for LightRAG integration.

    Let LightRAG's semantic understanding handle document structure.
    Just provide clean chunks with basic metadata.
    """
    # Basic sliding window or paragraph-based chunking
    # Add page numbers, position metadata
    # NO REGEX SECTION PARSING
    # Return clean text chunks
```

---

### Phase 2: Ontology Integration with LightRAG 🎯

**Goal**: Customize LightRAG's entity/relationship extraction with ontology constraints

#### 2.1 Customize Entity Extraction Prompt

**Location**: Where LightRAG defines `entity_extract_prompt`

```python
from src.core.ontology import EntityType, get_entity_type_descriptions

entity_extract_prompt = f"""You are an expert in government contracting and Request for Proposal (RFP) analysis.

Extract entities from the following text using ONLY these types:

{get_entity_type_descriptions()}

ENTITY EXTRACTION RULES:
1. **Maximum 25 entities per chunk** - focus on unique, meaningful entities
2. **RFP Sections**: Extract as separate entities (Section A, Section B, ..., Section M)
   - CORRECT: "Section J", "Section K", "Section L" (individual)
   - WRONG: "Section J-L" (merged sections don't exist)
3. **Attachments**: Preserve full identifiers
   - CORRECT: "Attachment J-0200000-17", "Attachment JL-1"
   - WRONG: "17", "Attachment L" (doesn't exist)
4. **Requirements**: Extract specific must-haves, deliverables, acceptance criteria
5. **Organizations**: Companies, agencies, government entities (full names)
6. **Technology**: Specific systems, software, tools (not generic terms like "computer")
7. **Personnel**: Labor categories, positions (not individual names unless key)

IGNORE:
- Generic terms ("rounding", "format", "table")
- Irrelevant references ("100m Sprint Record", "Market Selloff")
- Table row data (extract table PURPOSE as entity, not every row)
- Repetitive list items (extract list CATEGORY, not every item)

STOP after extracting the most important 25 entities.

Text to analyze:
{{input_text}}

Output format: [entity, entity_name, entity_type, description]
"""
```

**Implementation**: Create `src/core/lightrag_prompts.py` with ontology-guided prompts

#### 2.2 Customize Relationship Extraction Prompt

```python
from src.core.ontology import VALID_RELATIONSHIPS, RelationshipType

def generate_relationship_prompt():
    """Generate relationship extraction prompt with ontology constraints."""

    valid_combos = []
    for (source_type, target_type), rel_types in VALID_RELATIONSHIPS.items():
        for rel_type in rel_types:
            valid_combos.append(f"  - {source_type} --[{rel_type}]--> {target_type}")

    valid_relationships_str = "\n".join(valid_combos)

    return f"""Extract relationships between entities using ONLY these valid combinations:

{valid_relationships_str}

RELATIONSHIP EXTRACTION RULES:
1. **Maximum 20 relationships per chunk**
2. **Only connect entities already extracted** - don't invent new entities
3. **Use specific relationship types** - don't use generic "RELATED_TO"
4. **Focus on meaningful connections** that support RFP analysis

Examples:
- CORRECT: ["Section J", "CONTAINS", "Attachment JL-1"]
- CORRECT: ["NAVSTA Mayport", "REQUIRES", "Port Operations Services"]
- CORRECT: ["Technical Approach", "ADDRESSES", "PWS Section 3.2 Requirement"]
- WRONG: ["Section J-L", ...] (invalid section identifier)

STOP after extracting the most important 20 relationships.

Entities and text:
{{entities}}
{{input_text}}

Output format: [relationship, source_entity, target_entity, relationship_type, description]
"""
```

#### 2.3 Add Post-Processing Validation

```python
# src/core/ontology_validation.py

from src.core.ontology import EntityType, RelationshipType, is_valid_relationship

def validate_extracted_entities(entities: list[dict]) -> list[dict]:
    """
    Post-process entities after LightRAG extraction.

    - Validate entity types against ontology
    - Protect attachment patterns from over-cleaning
    - Reject generic/meaningless entities
    """
    validated = []

    for entity in entities:
        # Protect attachment patterns before cleaning
        if re.match(r'(Attachment\s+)?J-?\d{7}-\d{2}', entity['name']):
            entity['protected_pattern'] = True

        # Validate entity type
        try:
            entity_type = EntityType[entity['type']]
        except KeyError:
            logger.warning(f"Invalid entity type '{entity['type']}' for entity '{entity['name']}'")
            continue

        # Reject generic entities
        if entity['name'].lower() in ['rounding', 'format', 'table', 'both']:
            continue

        validated.append(entity)

    return validated

def validate_extracted_relationships(relationships: list[dict], entities: list[dict]) -> list[dict]:
    """
    Post-process relationships after LightRAG extraction.

    - Validate against VALID_RELATIONSHIPS
    - Ensure source/target entities exist
    - Reject weak/generic relationships
    """
    entity_names = {e['name'] for e in entities}
    validated = []

    for rel in relationships:
        # Check entities exist
        if rel['source'] not in entity_names or rel['target'] not in entity_names:
            continue

        # Validate relationship type combination
        source_type = next(e['type'] for e in entities if e['name'] == rel['source'])
        target_type = next(e['type'] for e in entities if e['name'] == rel['target'])

        if not is_valid_relationship(source_type, target_type, rel['type']):
            logger.warning(f"Invalid relationship: {source_type} --[{rel['type']}]--> {target_type}")
            continue

        validated.append(rel)

    return validated
```

#### 2.4 Integration Point

**Find where LightRAG calls entity/relationship extraction and inject our customization:**

```python
# In LightRAG's extraction pipeline (lightrag/operate.py or similar)

# Import our ontology-guided prompts
from src.core.lightrag_prompts import get_entity_extraction_prompt, get_relationship_extraction_prompt
from src.core.ontology_validation import validate_extracted_entities, validate_extracted_relationships

# Replace default prompts
entity_prompt = get_entity_extraction_prompt()
relationship_prompt = get_relationship_extraction_prompt()

# After extraction, validate with ontology
entities = await llm.extract_entities(chunk, entity_prompt)
entities = validate_extracted_entities(entities)  # ← Post-process with ontology

relationships = await llm.extract_relationships(chunk, entities, relationship_prompt)
relationships = validate_extracted_relationships(relationships, entities)  # ← Validate
```

---

### Phase 3: Simplified Chunking Strategy 📄

**Goal**: Replace custom regex preprocessing with simple, clean chunking

#### 3.1 Remove Complex Section Parsing

**Delete**:

- `ShipleyRFPChunker` class (archive, don't lose the ideas)
- Regex-based section identification
- Hardcoded relationship mappings

**Keep**:

- Requirement-based splitting logic (it worked!)
- Basic metadata (page numbers, chunk order)

#### 3.2 Implement Simple Chunking

```python
# src/core/simple_chunking.py

def create_simple_chunks(
    document_text: str,
    file_path: str,
    chunk_size: int = 1000,
    overlap: int = 200
) -> list[dict]:
    """
    Simple sliding window chunking with basic metadata.

    Let LightRAG semantically understand structure, don't preprocess.
    """
    chunks = []

    # Split by paragraphs or sliding window
    paragraphs = document_text.split('\n\n')

    current_chunk = []
    current_size = 0
    chunk_num = 0

    for para in paragraphs:
        para_size = len(para)

        if current_size + para_size > chunk_size and current_chunk:
            # Create chunk
            chunks.append({
                'content': '\n\n'.join(current_chunk),
                'metadata': {
                    'chunk_id': f'chunk_{chunk_num:04d}',
                    'chunk_order': chunk_num,
                    'file_path': file_path,
                    # LightRAG will extract sections semantically
                }
            })
            chunk_num += 1
            current_chunk = [para]  # Start new chunk with overlap
            current_size = para_size
        else:
            current_chunk.append(para)
            current_size += para_size

    # Last chunk
    if current_chunk:
        chunks.append({
            'content': '\n\n'.join(current_chunk),
            'metadata': {
                'chunk_id': f'chunk_{chunk_num:04d}',
                'chunk_order': chunk_num,
                'file_path': file_path,
            }
        })

    return chunks
```

---

### Phase 4: LLM Configuration Optimization ⚙️

**Goal**: Optimize Ollama settings for constrained extraction

#### 4.1 Update .env Configuration

```bash
# Core LightRAG + Ollama
HOST=localhost
PORT=9621
LLM_MODEL=mistral-nemo:latest  # 12B is sufficient with good prompts
EMBEDDING_MODEL=bge-m3:latest

# Constrained extraction settings
LLM_TIMEOUT=3600
LLM_TEMPERATURE=0.1  # Deterministic extraction
NUM_PREDICT=2048     # Reduced from 4096 - forces conciseness
OLLAMA_LLM_NUM_CTX=16384  # 16K context window

# Chunking strategy
CHUNK_TOKEN_SIZE=1000  # Simpler, smaller chunks
OVERLAP_TOKEN_SIZE=200
MAX_PARALLEL_INSERT=2
```

#### 4.2 Performance Targets

| Metric                | Path A (Current)       | Path B (Target)    |
| --------------------- | ---------------------- | ------------------ |
| Chunk 136 Processing  | 24 minutes             | <2 minutes         |
| Entities per Chunk    | 113 max                | 25 max             |
| Invalid Entity Errors | 3+ occurrences         | 0                  |
| Section ID Errors     | Many ("J-L", "J-Line") | 0                  |
| Total Processing Time | ~3 hours               | <60 minutes        |
| Entity Quality        | Mixed (noise)          | High (constrained) |

---

## Implementation Checklist

### Preparation

- [ ] Read `docs/RAG_STORAGE_ANALYSIS.md` (lessons learned from Path A)
- [ ] Review `src/core/ontology.py` (understand EntityType, RelationshipType, VALID_RELATIONSHIPS)
- [ ] Review PydanticAI models in `src/models/rfp_models.py`
- [ ] Understand Uniform Contract Format (Sections A-M, J attachments)

### Phase 1: Cleanup (Est: 30 min)

- [ ] Create `archive/path_a_exploratory_work/` directory
- [ ] Archive `src/core/chunking.py` (ShipleyRFPChunker)
- [ ] Archive `test_phase1_optimizations.py`
- [ ] Simplify `src/core/lightrag_chunking.py` to basic strategy
- [ ] Commit: "chore: Archive Path A exploratory work, prepare for Path B"

### Phase 2: Ontology Integration (Est: 2 hours)

- [ ] Create `src/core/lightrag_prompts.py`
  - [ ] Implement `get_entity_extraction_prompt()` with ontology types
  - [ ] Implement `get_relationship_extraction_prompt()` with VALID_RELATIONSHIPS
  - [ ] Add Uniform Contract Format examples (Section A-M structure)
- [ ] Create `src/core/ontology_validation.py`
  - [ ] Implement `validate_extracted_entities()`
  - [ ] Implement `validate_extracted_relationships()`
  - [ ] Add attachment pattern protection (J-XXXXXX-YY)
- [ ] Find LightRAG extraction pipeline integration point
  - [ ] Inject custom prompts
  - [ ] Add post-processing validation hooks
- [ ] Commit: "feat: Integrate ontology with LightRAG extraction prompts"

### Phase 3: Simple Chunking (Est: 1 hour)

- [ ] Create `src/core/simple_chunking.py`
- [ ] Implement sliding window strategy
- [ ] Preserve page number metadata
- [ ] Update `src/core/lightrag_chunking.py` to use simple strategy
- [ ] Remove regex section parsing entirely
- [ ] Commit: "feat: Simplify chunking strategy for clean LightRAG input"

### Phase 4: Testing & Validation (Est: 2 hours)

- [ ] Clear `rag_storage/` directory
- [ ] Update `.env` with optimized settings
- [ ] Process `inputs/__enqueued__/_N6945025R0003.pdf`
- [ ] Monitor logs for:
  - [ ] No "J-L" or "J-Line" section errors
  - [ ] No "17" entity cleaning errors
  - [ ] No invalid entity type errors
  - [ ] Max 25 entities per chunk
  - [ ] Processing <60 minutes total
- [ ] Analyze `rag_storage/graph_chunk_entity_relation.graphml`
  - [ ] Verify individual section nodes (Section A, Section J, Section K, Section L)
  - [ ] Verify proper attachment nodes (JL-1, J-0200000-17)
  - [ ] Validate relationships use ontology types only
- [ ] Create test queries to validate semantic search
- [ ] Commit: "test: Validate Path B ontology-guided extraction"

### Phase 5: Documentation (Est: 1 hour)

- [ ] Create `docs/PATH_B_IMPLEMENTATION_NOTES.md`
  - [ ] Document prompt customization approach
  - [ ] Document validation strategy
  - [ ] Include before/after knowledge graph comparison
- [ ] Update `README.md` with Path B architecture
- [ ] Update `.github/copilot-instructions.md` with new patterns
- [ ] Commit: "docs: Document Path B ontology integration approach"

---

## Key Design Principles

### 1. **Framework-Native Integration**

- Customize LightRAG's prompts, don't bypass them
- Use post-processing validation, don't preprocess with regex
- Leverage LightRAG's semantic understanding

### 2. **Ontology as Guide, Not Gatekeeper**

- Prompts constrain extraction to ontology types
- Validation ensures quality, allows LLM flexibility
- Examples teach correct structure (Sections A-M individually)

### 3. **Clean Input, Constrained Output**

- Simple chunking provides clean text to LightRAG
- Ontology-guided prompts constrain what LightRAG extracts
- Validation ensures knowledge graph maps to PydanticAI models

### 4. **Measurable Success**

- Knowledge graph entities map to Uniform Contract Format
- Zero fictitious sections ("J-L", "Attachment L")
- Entities/relationships validate against ontology
- Performance within targets (<60 min, <25 entities/chunk)

---

## Questions to Resolve During Implementation

1. **Where exactly does LightRAG define entity_extract_prompt?**

   - Need to find the integration point in LightRAG source
   - May need to subclass or monkey-patch if not configurable

2. **How to inject post-processing validation?**

   - Hook into LightRAG's extraction pipeline
   - Or wrap LightRAG's insert methods?

3. **PydanticAI Model Integration**

   - How to map knowledge graph entities back to `rfp_models.py` classes?
   - Need query/retrieval layer that instantiates Pydantic models?

4. **Shipley Methodology Integration**
   - Use Shipley prompts from `prompts/` directory?
   - Combine Shipley analysis with ontology-constrained extraction?

---

## Success Metrics

### Knowledge Graph Quality

- ✅ All RFP sections extracted as individual entities (A through M)
- ✅ No fictitious merged sections ("J-L", "J-Line")
- ✅ Attachments properly identified (JL-1, J-0200000-17)
- ✅ All entities have valid ontology types
- ✅ All relationships from VALID_RELATIONSHIPS combinations

### Performance

- ✅ Processing time <60 minutes for full RFP
- ✅ Average 10-15 entities per chunk, max 25
- ✅ Average 10-15 relationships per chunk, max 20
- ✅ Zero invalid entity type errors
- ✅ Zero entity cleaning errors ("17" preserved)

### Integration

- ✅ Knowledge graph entities mappable to PydanticAI models
- ✅ Semantic search returns ontology-aligned results
- ✅ Shipley methodology prompts work with constrained extraction
- ✅ UI can query/display ontology-structured knowledge

---

## Next Steps After Successful Implementation

1. **Advanced Ontology Features**

   - Entity importance scoring (high/medium/low)
   - Relationship strength calculation
   - Requirement traceability matrix

2. **PydanticAI Agent Integration**

   - Connect knowledge graph to `rfp_agents.py`
   - Enable natural language queries over constrained KG
   - Generate RFP responses using ontology-guided retrieval

3. **Shipley Methodology Automation**

   - Compliance matrix generation
   - Gap analysis automation
   - Win theme identification

4. **Fine-Tuning Opportunities**
   - Extract golden dataset from validated knowledge graph
   - Fine-tune mistral-nemo on RFP entity extraction
   - Improve extraction speed and quality

---

## References

- `docs/RAG_STORAGE_ANALYSIS.md` - Path A lessons learned
- `src/core/ontology.py` - EntityType, RelationshipType, VALID_RELATIONSHIPS
- `src/models/rfp_models.py` - PydanticAI domain models
- `docs/SHIPLEY_LLM_CURATED_REFERENCE.md` - Shipley methodology
- `.github/copilot-instructions.md` - Project architecture guidance

---

**Ready to implement Path B correctly. Let's build ontology-guided RAG the right way!** 🚀
