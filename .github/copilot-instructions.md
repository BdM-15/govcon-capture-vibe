# Copilot Instructions for GovCon-Capture-Vibe Project

## Project Overview

**Enhanced LightRAG Server** for federal RFP compliance automation. Professional React-based WebUI with custom RFP analysis capabilities grounded in Shipley methodology. Replaces traditional Streamlit interfaces with LightRAG's official server architecture plus custom government contracting extensions.

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

### **Extending RFP Analysis**

1. **Study Shipley Methodology**: Reference specific guide sections (p.X-Y)
2. **Create Prompt Templates**: Store in `/prompts/` with methodology citations
3. **Add API Routes**: Extend `src/api/rfp_routes.py` with new endpoints
4. **Document Endpoints**: Include Shipley references in OpenAPI docs
5. **Test with Examples**: Validate against known RFP analysis patterns

### **LightRAG Integration**

- **Leverage Core**: Use LightRAG's document processing, knowledge graphs, search
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
