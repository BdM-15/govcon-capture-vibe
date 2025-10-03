# Copilot Instructions for GovCon-Capture-Vibe Project

## ⚠️ ABSOLUTE REQUIREMENT: Virtual Environment Activation

**BEFORE running ANY terminal command that uses Python, uv, or project dependencies, you MUST activate the virtual environment:**

```powershell
# FIRST: Activate venv as standalone command
.venv\Scripts\Activate.ps1

# THEN: Run your command in the activated environment
<your command here>
```

**NO EXCEPTIONS.** Activate venv as a **separate command**, then run subsequent commands. Do NOT chain with semicolons. See "CRITICAL: Virtual Environment Activation" section below for details.

---

## ⚠️ ABSOLUTE REQUIREMENT: Use Workspace Tools, Not PowerShell

**ALWAYS prioritize workspace tools over PowerShell commands for file operations:**

**DO** (Use Workspace Tools):

- ✅ **Read files**: Use `read_file` tool, NOT `Get-Content` or `cat` in PowerShell
- ✅ **Create files**: Use `create_file` tool, NOT `New-Item` or `echo` in PowerShell
- ✅ **Edit files**: Use `replace_string_in_file` tool, NOT `(Get-Content).Replace()` in PowerShell
- ✅ **Search content**: Use `grep_search` or `semantic_search` tools, NOT `Select-String` in PowerShell
- ✅ **List directories**: Use `list_dir` tool, NOT `Get-ChildItem` in PowerShell

**ONLY use PowerShell when**:

- Running Python scripts or applications (`python app.py`)
- Using `uv` commands (`uv pip list`, `uv sync`)
- Git operations (`git status`, `git commit`)
- System commands that have no workspace equivalent

**Why This Matters**:

- Workspace tools provide better context to the agent
- Reduces unnecessary terminal command calls
- Prevents context loss from truncated terminal output
- More reliable for file operations in the conversation history

**Example - CORRECT**:

```python
# ✅ Read a file directly
read_file("src/core/ontology.py")

# ✅ Search for a pattern
grep_search(query="EntityType", isRegexp=False, includePattern="**/*.py")

# ✅ Create a new file
create_file(filePath="src/new_module.py", content="# New module")
```

**Example - WRONG**:

```powershell
# ❌ Don't use PowerShell for file operations
Get-Content "src/core/ontology.py"
Select-String -Path "**/*.py" -Pattern "EntityType"
New-Item -Path "src/new_module.py" -ItemType File
```

---

## Project Overview

**Ontology-Modified LightRAG System** for government contracting RFP analysis. We **actively modify LightRAG's extraction capabilities** by injecting domain-specific government contracting ontology into its processing pipeline, transforming generic document processing into specialized federal procurement intelligence.

**Critical Distinction**: This is NOT generic LightRAG hoping to understand government contracting. We **modify LightRAG's internal extraction prompts** with our ontology to teach it government-specific entities, relationships, and structures that generic processing would miss.

## ⚠️ CRITICAL: Ontology-Modified LightRAG Approach

### Primary Library

**Package**: `lightrag-hku==1.4.9` (installed in `.venv/Lib/site-packages/lightrag/`)

**Core Philosophy**: **Modify LightRAG's extraction engine with domain ontology, don't rely on generic processing.**

### Why Generic LightRAG Fails for Government Contracting

**Generic LightRAG cannot**:

- Distinguish CLIN (Contract Line Item Number) from generic line items
- Recognize Section L↔M evaluation relationships
- Identify "shall" vs "should" requirement classifications (Shipley methodology)
- Extract FAR/DFARS clause applicability
- Map SOW requirements to deliverables and evaluation criteria
- Understand Uniform Contract Format (A-M sections, J attachments)

**Our Ontology-Modified Approach**:

- **Injects government contracting entity types** into LightRAG's extraction prompts
- **Constrains relationships** to valid government contracting patterns (L↔M, requirement→evaluation)
- **Teaches domain terminology** through custom examples (PWS, SOW, CLIN, Section M factors)
- **Validates extractions** against ontology to ensure domain accuracy

**DO** (Modify LightRAG's Processing):

- ✅ **Inject ontology into `addon_params["entity_types"]`** - This modifies what LightRAG extracts
- ✅ **Customize extraction prompts** via `PROMPTS` dictionary with government contracting examples
- ✅ **Add domain-specific few-shot examples** showing RFP entity patterns
- ✅ **Post-process with ontology validation** to ensure domain accuracy
- ✅ **Constrain relationships** to valid government contracting patterns

**DO NOT** (Don't Bypass the Framework):

- ❌ Create custom preprocessing that bypasses LightRAG's semantic understanding
- ❌ Build parallel extraction mechanisms outside the framework
- ❌ Use deterministic regex for entity/section identification (Path A mistake)
- ❌ Modify LightRAG source files directly
- ❌ Assume generic LightRAG will "just figure out" government contracting concepts

### Key LightRAG Modification Points

**1. Entity Type Injection** (`.venv/Lib/site-packages/lightrag/lightrag.py` line 362):

```python
# MODIFY LightRAG's entity extraction by injecting ontology types
addon_params: dict[str, Any] = field(
    default_factory=lambda: {
        "language": "English",
        "entity_types": [
            "ORGANIZATION", "REQUIREMENT", "DELIVERABLE", "CLIN",  # ← Government contracting ontology!
            "SECTION", "EVALUATION_FACTOR", "FAR_CLAUSE", "SECURITY_REQUIREMENT"
        ]  # Generic types like "person", "location" won't capture government contracting concepts
    }
)
```

**This injection happens at** `.venv/Lib/site-packages/lightrag/operate.py` line 2024:

```python
entity_types = global_config["addon_params"].get("entity_types", DEFAULT_ENTITY_TYPES)
# ↑ Our ontology types get injected into extraction prompt here
```

**2. Prompt Customization** (`.venv/Lib/site-packages/lightrag/prompt.py`):

```python
# MODIFY extraction prompts with government contracting examples
PROMPTS["entity_extraction_system_prompt"]  # Inject ontology types here: {entity_types}
PROMPTS["entity_extraction_examples"]        # Replace generic examples with RFP-specific ones
```

**Example modification**:

```python
# Generic LightRAG example (won't work for RFPs):
("Alice manages the TechCorp project", "PERSON|ORGANIZATION|PROJECT")

# Government contracting example (what we need):
("Section L.3.2 requires proposal submission by 2:00 PM EST",
 "SECTION|REQUIREMENT|DEADLINE")
```

**3. Extraction Process Flow** (`.venv/Lib/site-packages/lightrag/operate.py` line 2028+):

- Line 2024: **Our ontology entity types** injected from `addon_params`
- Line 2069: Prompts formatted with **our government contracting entity types**
- Line 2080: LLM called with **modified prompts** (not generic ones)
- Post-processing: **Validate against ontology** to ensure domain accuracy

### How to Modify LightRAG Correctly

**✅ CORRECT: Inject Ontology into LightRAG**

```python
# MODIFY LightRAG's extraction by injecting government contracting ontology
from lightrag import LightRAG
from src.core.ontology import EntityType

rag = LightRAG(
    working_dir="./rag_storage",
    addon_params={
        "language": "English",
        "entity_types": [e.value for e in EntityType],  # ← Teaches LightRAG government contracting concepts
    }
)

# This modifies how LightRAG extracts entities internally:
# - Generic: "person", "location", "organization"
# - Modified: "REQUIREMENT", "CLIN", "EVALUATION_FACTOR", "FAR_CLAUSE"
```

**✅ CORRECT: Post-Process with Ontology Validation**

```python
# After LightRAG extraction, validate results against ontology
from src.core.ontology import validate_entity_type, is_valid_relationship

# Ensure extracted entities match government contracting domain
validated_entities = [e for e in extracted_entities if validate_entity_type(e)]
# Only keep relationships valid in government contracting (e.g., Section L ↔ Section M)
validated_relations = [r for r in extracted_relations if is_valid_relationship(r)]
```

**✅ CORRECT: Add Domain-Specific Examples**

```python
# Replace LightRAG's generic examples with government contracting patterns
RFP_EXTRACTION_EXAMPLES = [
    ("Section C.3.1 states the contractor shall provide weekly status reports",
     "SECTION|C.3.1->requires->REQUIREMENT|weekly status reports"),
    ("CLIN 0001 covers base year services at $500,000",
     "CLIN|0001->has_value->PRICE|$500,000->covers->SERVICE|base year services"),
]
```

**❌ WRONG: Custom Preprocessing That Bypasses LightRAG**

```python
# DON'T DO THIS - bypasses LightRAG's semantic understanding
def custom_regex_chunker(text):
    sections = re.findall(r"Section ([A-M])", text)  # ← Deterministic, brittle
    return structured_chunks  # ← LightRAG can't learn from this, creates garbage entities
```

**❌ WRONG: Hoping Generic LightRAG Understands Government Contracting**

```python
# DON'T DO THIS - generic entity types won't capture domain concepts
rag = LightRAG(
    addon_params={
        "entity_types": ["person", "organization", "location"]  # ← Won't extract CLINs, FAR clauses, etc.
    }
)
# Generic LightRAG has never seen RFPs - it needs ontology injection to understand them!
```

### Referencing LightRAG Source

When implementing ontology integration, always reference the installed library:

- **Prompt structure**: `.venv/Lib/site-packages/lightrag/prompt.py`
- **Entity extraction**: `.venv/Lib/site-packages/lightrag/operate.py` (lines 2020-2170)
- **LightRAG class**: `.venv/Lib/site-packages/lightrag/lightrag.py` (lines 100-450)
- **Constants**: `.venv/Lib/site-packages/lightrag/constants.py`

Use `uv pip list` to verify package version, not `pip list`.

---

## ⚠️ CRITICAL: Virtual Environment Activation (ABSOLUTE REQUIREMENT)

### **MANDATORY RULE: ALWAYS ACTIVATE VENV FIRST**

**BEFORE running ANY terminal command, you MUST activate the virtual environment. NO EXCEPTIONS.**

### **The Problem**

When the AI agent opens a new terminal with `run_in_terminal`, it does NOT automatically activate the Python virtual environment (even though VS Code settings are configured for it). This causes:

- ❌ Commands fail because dependencies aren't found
- ❌ Wrong Python interpreter used (global instead of `.venv`)
- ❌ `uv`, `lightrag`, and project dependencies not available
- ❌ Confusion and wasted time debugging environment issues

### **The Solution**

**Activate venv as a STANDALONE command first, then run your actual command:**

```powershell
# ✅ CORRECT: Activate venv as standalone command
.venv\Scripts\Activate.ps1

# THEN run your command (in next terminal call)
uv pip list

# ✅ CORRECT: Two-step process
# Step 1:
.venv\Scripts\Activate.ps1
# Step 2 (after activation confirms):
python app.py

# ❌ WRONG: Chaining with semicolon
.venv\Scripts\Activate.ps1; uv pip list  # Don't do this!

# ❌ WRONG: Running command without venv activation
uv pip list  # ← Will fail! uv not in global PATH
```

**Why Standalone**: This mimics VS Code's behavior where activation is a separate step that persists in the terminal session.

### **VS Code Terminal Settings**

The workspace has a custom PowerShell profile configured in `.vscode/settings.json`:

```json
{
  "terminal.integrated.defaultProfile.windows": "PowerShell (govcon-capture-vibe)",
  "terminal.integrated.profiles.windows": {
    "PowerShell (govcon-capture-vibe)": {
      "source": "PowerShell",
      "args": ["-NoExit", "-Command", "& '.venv/Scripts/Activate.ps1'"]
    }
  }
}
```

**However**: The AI agent's `run_in_terminal` tool does NOT automatically use this profile. You MUST explicitly activate venv in every command.

### **Standard Command Patterns**

**Package Management**:

```powershell
# Step 1: Activate venv (standalone)
.venv\Scripts\Activate.ps1

# Step 2: Run your command (separate call)
uv pip list
# or
uv pip install <package>
# or
uv sync
```

**Python Execution**:

```powershell
# Step 1: Activate venv (standalone)
.venv\Scripts\Activate.ps1

# Step 2: Run your command (separate call)
python app.py
# or
python -c "import lightrag; print(lightrag.__file__)"
# or
python -m pytest
```

**LightRAG Source Inspection**:

```powershell
# Step 1: Activate venv (standalone)
.venv\Scripts\Activate.ps1

# Step 2: Inspect (separate call)
python -c "import lightrag; print(lightrag.__file__)"
```

**Git Operations** (don't need venv):

```powershell
# Git commands don't need venv activation
git status
git add .
git commit -m "message"
```

**File Operations** (don't use PowerShell at all):

```python
# ✅ CORRECT: Use workspace tools directly
read_file("src/core/ontology.py")
grep_search(query="EntityType", isRegexp=False)
list_dir("src/core")

# ❌ WRONG: Don't use PowerShell for file operations
# Get-Content "src/core/ontology.py"  # ← Use read_file instead
# Select-String -Pattern "EntityType"  # ← Use grep_search instead
```

### **Verification Before Every Command**

**Before issuing ANY command:**

1. ✅ Ask: "Is this a file operation (read/create/edit/search)?"
   - If YES: Use workspace tools (`read_file`, `create_file`, `grep_search`) - NOT PowerShell
2. ✅ Ask: "Does this command need Python/uv/project dependencies?"
   - If YES: Run `.venv\Scripts\Activate.ps1` as **standalone command** first, THEN run your command in a separate call
3. ✅ Ask: "Is this git or a system command?"
   - If YES: Run command directly (no venv needed)

### **Common Mistakes to Avoid**

```powershell
# ❌ WRONG: Forgetting venv activation
uv pip list  # Fails - uv not found

# ❌ WRONG: Assuming terminal has venv active
python app.py  # Uses wrong interpreter

# ❌ WRONG: Chaining venv activation with command
.venv\Scripts\Activate.ps1; uv pip list  # Don't chain - activate separately!

# ❌ WRONG: Using PowerShell for file operations
Get-Content "src/core/ontology.py"  # Use read_file instead
Select-String -Path "*.py" -Pattern "EntityType"  # Use grep_search instead

# ✅ CORRECT: Activate venv as standalone, THEN run command
# Command 1:
.venv\Scripts\Activate.ps1
# Command 2 (after activation):
uv pip list

# ✅ CORRECT: Use workspace tools for file operations
read_file("src/core/ontology.py")
grep_search(query="EntityType", isRegexp=False)
```

### **Why This Is Critical**

- **Package location**: `lightrag-hku==1.4.9` is installed in `.venv/Lib/site-packages/`, NOT globally
- **Tool availability**: `uv` is only available in the venv PATH
- **Import paths**: Project modules (`src.core.ontology`) only work with venv Python
- **Consistency**: Ensures agent uses same environment as user

**REMEMBER**: When in doubt, activate venv. It's always safe to activate even if already active.

---

## Path B Architecture (Ontology-Guided Framework Integration)

### Architectural Philosophy

**Guide LightRAG's semantic extraction with ontology, don't replace it with deterministic preprocessing.**

Previous Path A (archived) built custom `ShipleyRFPChunker` with regex-based section parsing that corrupted LightRAG's input, creating fictitious entities like "RFP Section J-L" (doesn't exist in Uniform Contract Format). Path B integrates ontology WITH LightRAG's framework.

## Current Architecture (Phase 2 - Production Implementation)

### **Technology Stack**

- **Server**: Extended LightRAG FastAPI server with custom RFP analysis routes
- **Frontend**: React + TypeScript WebUI (LightRAG's official interface)
- **LLM**: Ollama with qwen2.5-coder:7b (32K context, optimized prompts)
- **Embeddings**: bge-m3:latest (1024-dimensional, multilingual)
- **RAG Engine**: LightRAG knowledge graphs with hybrid search
- **Methodology**: Shipley Proposal Guide + Capture Guide integration

### **Key Components**

1. **app.py**: Main server startup script
2. **src/govcon_server.py**: Extended LightRAG server with RFP capabilities
3. **src/api/rfp_routes.py**: Custom FastAPI routes for RFP analysis
4. **prompts/**: Shipley methodology prompt templates
5. **React WebUI**: Professional interface at http://localhost:9621

## Guiding Principles (Always Adhere)

1. **LightRAG Foundation**: Build on LightRAG's established patterns, don't reinvent
2. **Shipley Methodology**: Ground all analysis in Shipley Proposal Guide standards (reference specific pages)
3. **Professional Quality**: Enterprise-grade React UI, comprehensive API documentation
4. **Local/Zero-Cost**: All processing local with Ollama, no external dependencies
5. **Modular Architecture**: Extend LightRAG cleanly, maintain separation of concerns
6. **Government Focus**: Optimize for federal RFP structure (A-M sections, J attachments)

## Implementation Standards

### **Code Organization**

```
govcon-capture-vibe/
├── app.py                          # Server startup (calls src/govcon_server.py)
├── src/
│   ├── api/
│   │   ├── __init__.py
│   │   └── rfp_routes.py           # Custom RFP analysis FastAPI routes
│   └── govcon_server.py            # Extended LightRAG server class
├── prompts/
│   └── shipley_requirements_extraction.txt  # Shipley methodology prompts
├── .env                           # Ollama + LightRAG configuration
└── README.md                      # Architecture documentation
```

### **API Route Standards**

- **Prefix**: `/rfp` for all custom routes
- **Models**: Pydantic models for request/response validation
- **Documentation**: Comprehensive docstrings with Shipley references
- **Error Handling**: Structured error responses with helpful messages
- **Methodology**: Reference specific Shipley Guide pages in responses

### **Shipley Integration Patterns**

```python
# Example: Requirements extraction with Shipley methodology
@router.post("/extract-requirements")
async def extract_requirements(section_filter: Optional[str] = None):
    """
    Extract requirements using Shipley Proposal Guide methodology (p.50-55)

    Applies Shipley requirements analysis framework:
    - Must/Should/May classification
    - Section mapping (A-M, J attachments)
    - Dependency tracking
    """
    # Load Shipley prompt template
    prompts_dir = Path(__file__).parent.parent.parent / "prompts"
    shipley_prompt = prompts_dir / "shipley_requirements_extraction.txt"

    # Apply methodology with citations
    return {
        "requirements": extracted_reqs,
        "shipley_reference": "Proposal Guide p.50-55 (Requirements Analysis)"
    }
```

### **Environment Configuration**

```bash
# Core LightRAG + Ollama setup
HOST=localhost
PORT=9621
LLM_MODEL=qwen2.5-coder:7b
EMBEDDING_MODEL=bge-m3:latest
LLM_TIMEOUT=900
EMBEDDING_TIMEOUT=300

# RFP processing optimizations
CHUNK_TOKEN_SIZE=2000
SUMMARY_MAX_TOKENS=8192
MAX_PARALLEL_INSERT=2
```

## Development Workflow

### **Critical Reference Artifacts**

When brainstorming enhancements or refining ontology, leverage these key resources alongside project artifacts:

**Project Artifacts** (Primary References):

- `/examples/` - Sample outputs (requirements, compliance matrices, QFG)
- `/prompts/` - Shipley methodology prompt templates
- `/docs/` - Shipley guides, capture plans, reference documentation
- `/src/models/` - Core Pydantic data models (RFPRequirement, ComplianceAssessment, etc.)
- `/src/agents/` - PydanticAI agents using models for structured extraction
- `/src/core/` - Ontology configuration bridging models to LightRAG

**External Repositories** (Ontology & Architecture Inspiration):

- **[LightRAG GitHub](https://github.com/HKUDS/LightRAG)** - Foundation codebase for all ontology modifications
- **[AI RFP Simulator](https://github.com/felixlkw/ai-rfp-simulator)** - Entity types, relationship patterns (Chinese, use translation)
- **[RFP Generation LangChain](https://github.com/abh2050/RFP_generation_langchain_agent_RAG)** - Automated clarification questions (Phase 6 inspiration)
- **[Awesome Procurement Data](https://github.com/makegov/awesome-procurement-data)** - Government data sources, terminology validation

**Architecture Note**: `/src/models/` and `/src/agents/` are NOT redundant:

- `models/` = Data structures (Pydantic models, enums)
- `agents/` = AI agents that USE those models for extraction
- `core/` = Bridges models to LightRAG with ontology validation

### **Extending RFP Analysis**

1. **Study Shipley Methodology**: Reference specific guide sections (p.X-Y)
2. **Cross-reference External Repos**: Check AI RFP Simulator for entity patterns, Awesome Procurement Data for terminology
3. **Create Prompt Templates**: Store in `/prompts/` with methodology citations
4. **Update Ontology if Needed**: Extend `src/core/ontology.py` entity types or relationships
5. **Add API Routes**: Extend `src/api/rfp_routes.py` with new endpoints
6. **Document Endpoints**: Include Shipley references in OpenAPI docs
7. **Test with Examples**: Validate against known RFP analysis patterns

### **LightRAG Integration**

- **Leverage Core**: Use LightRAG's document processing, knowledge graphs, search
- **Reference Foundation**: Always check [LightRAG GitHub](https://github.com/HKUDS/LightRAG) for implementation patterns
- **Extend Cleanly**: Add custom routes without modifying LightRAG core
- **Follow Patterns**: Use LightRAG's established architecture and conventions
- **Maintain Compatibility**: Ensure custom features don't break LightRAG functionality

### **UI Development** (Future Phase)

- **React Components**: Extend LightRAG's WebUI with RFP-specific interfaces
- **Component Structure**: Compliance dashboards, gap analysis views, requirement matrices
- **Integration**: Connect to custom `/rfp` API endpoints
- **Professional Design**: Match LightRAG's UI standards and patterns

## Shipley Methodology Implementation

### **Requirements Analysis** (Proposal Guide p.45-55)

```python
# Template structure for requirements extraction
{
    "id": "REQ-XXX",
    "text": "Exact RFP text verbatim",
    "section": "Section C.3.1 or J-1",
    "type": "functional|performance|interface|design|security",
    "compliance_level": "Must|Should|May",
    "shipley_reference": "Proposal Guide p.52"
}
```

### **Compliance Matrix** (Proposal Guide p.53-55)

```python
# Shipley 4-level compliance assessment
{
    "requirement_id": "REQ-001",
    "compliance_status": "Compliant|Partial|Non-Compliant|Not Addressed",
    "gap_analysis": "Detailed gap description",
    "risk_level": "High|Medium|Low",
    "recommendations": ["Specific action items"],
    "win_theme": "Competitive advantage opportunity"
}
```

### **Gap Analysis** (Capture Guide p.85-90)

- Capability gap identification
- Competitive positioning assessment
- Risk mitigation strategies
- Win theme development opportunities

## Usage Patterns for Copilot

### **Creating New RFP Analysis Features**

```python
# 1. Study applicable Shipley methodology
# Reference: Shipley Proposal Guide p.X-Y for [specific technique]

# 2. Create prompt template in /prompts/
def load_shipley_prompt(prompt_name: str) -> str:
    """Load Shipley methodology prompt template"""
    prompt_path = Path(__file__).parent.parent.parent / "prompts" / f"{prompt_name}.txt"
    return prompt_path.read_text(encoding='utf-8')

# 3. Implement API endpoint with methodology application
@router.post("/new-analysis")
async def new_analysis(request: AnalysisRequest):
    """
    New analysis applying Shipley methodology

    References: Shipley Guide p.X-Y for methodology basis
    """
    shipley_prompt = load_shipley_prompt("shipley_new_analysis")
    # Apply methodology with proper citations
```

### **Error Handling Standards**

```python
try:
    # RFP analysis logic
    result = await perform_analysis()
    return result
except Exception as e:
    logger.error(f"RFP analysis failed: {e}")
    raise HTTPException(
        status_code=500,
        detail=f"Analysis failed: {str(e)}"
    )
```

### **Response Standards**

- **Always include**: Shipley methodology references
- **Structure consistently**: Use Pydantic models for validation
- **Provide citations**: Reference specific guide pages
- **Enable traceability**: Link analysis back to RFP sources

## Testing and Validation

### **API Testing**

```bash
# Test requirements extraction
curl -X POST "http://localhost:9621/rfp/extract-requirements" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "section_filter=Section C"

# Test compliance matrix
curl -X POST "http://localhost:9621/rfp/compliance-matrix" \
  -d "format_type=shipley"

# Test comprehensive analysis
curl -X POST "http://localhost:9621/rfp/analyze" \
  -H "Content-Type: application/json" \
  -d '{"query": "technical requirements", "shipley_mode": true}'
```

### **Methodology Validation**

- Compare outputs against Shipley Guide examples
- Verify proper requirement classification
- Ensure compliance matrix completeness
- Validate gap analysis methodology application

## Common Implementation Patterns

### **Shipley Prompt Integration**

```python
# Load methodology-specific prompts
prompts_dir = Path(__file__).parent.parent.parent / "prompts"
shipley_prompt_path = prompts_dir / "shipley_requirements_extraction.txt"

if shipley_prompt_path.exists() and request.shipley_mode:
    with open(shipley_prompt_path, 'r', encoding='utf-8') as f:
        shipley_prompt = f.read()

    # Apply Shipley methodology
    analysis_prompt = f"{shipley_prompt}\n\nFocus: {request.query}"
```

### **Response Structure with Citations**

```python
return RFPAnalysisResponse(
    requirements=extracted_requirements,
    compliance_matrix=compliance_results,
    gap_analysis=gap_results,
    shipley_references=[
        "Shipley Proposal Guide p.50-55 (Compliance Matrix)",
        "Shipley Capture Guide p.85-90 (Gap Analysis)"
    ]
)
```

## Future Development Phases

### **Phase 3: Custom React Components**

- RFP analysis dashboard components
- Compliance matrix interactive tables
- Gap analysis visualization tools
- Win theme development interfaces

### **Phase 4: Advanced Shipley Integration**

- Proposal outline generation
- Win theme development automation
- Competitive analysis frameworks
- Past performance integration

## Troubleshooting for Copilot

### **Common Issues**

1. **LightRAG Integration**: Follow established patterns, don't modify core
2. **Ollama Connectivity**: Verify models are pulled and service is running
3. **API Route Registration**: Ensure routes are properly included in main app
4. **Shipley Citations**: Always reference specific guide pages in responses

### **Development Standards**

- **Documentation**: Include Shipley methodology references
- **Error Handling**: Provide helpful error messages with context
- **Testing**: Validate against known RFP analysis examples
- **Performance**: Optimize for large RFP documents (500+ pages)

---

**Build on LightRAG's foundation. Extend with Shipley methodology. Maintain professional quality.**
