# Copilot Instructions for GovCon-Capture-Vibe Project

## Project Overview

Local, zero-cost RAG app in Python for federal RFP compliance automation. Parse RFPs/PWS (A-M sections, J atts), generate Shipley-style matrices/outlines/gaps/Q&A. Ground all features in /docs Shipley materials (e.g., Proposal Guide for compliance checklists, Capture Guide for strategy, worksheets/plans for formats—reference specific pages in comments/prompts).

## Guiding Principles (Always Adhere)

1. **Simplicity**: Minimal code (<2000 lines total, <500/file); no bloat/overfitting. Concise functions/prompts; straightforward logic.
2. **Modularity**: Independent components (e.g., rfp_rag.py, gap_analyzer.py). Build/test one-by-one; relative imports.
3. **Maintainability**: Clean Python with docstrings/comments. Follow PEP-8 (79-char lines, spacing). Type hints; "# Reason:" for complex logic.
4. **Scalability/Flexibility**: Future-proof (e.g., add BOE parsing); adapt to RFP variations.
5. **Hardware Optimization**: Tune for Lenovo LEGION 5i (i9-14900HX, RTX 4060, 64GB)—7-8B Ollama models (llama3/mistral/nomic-embed-text); chunk for large docs (500+ pages) to avoid OOM; CPU/GPU via Ollama.
6. **Zero-Cost/Open-Source**: Local/offline—no APIs/networks. Plain-English outputs for GovCon (no ML jargon).
7. **Shipley Grounding**: Align features to /docs (e.g., mimic Worksheet checklists, Capture Plan overviews). Reference in code/prompts.
8. **LightRAG Native**: Use LightRAG's document processing pipeline from the start—no custom PDF extraction. Leverage LightRAG's built-in text extraction, chunking, and metadata handling.

## Tech Stack

- Python 3.13+ (latest stable).
- Env: uv/uvx for deps (no pip); always use/run in virtual env—scripts check/activate (e.g., shebang: #!/usr/bin/env python, comments remind).
- UI: Streamlit for uploads/queries/results (tables/JSON).
- Core: LightRAG + Ollama (local); LangChain fallback.
- Doc Handling: LightRAG's native document processing pipeline (automatic text extraction, chunking, and metadata for PDF/Word/Excel).
- Config: .env for secrets (e.g., OLLAMA_BASE_URL); config.py centralizes access with defaults/validation.

## Usage Tips for Copilot

- Generate small: E.g., "Implement req extraction using LightRAG's processed documents, grounded in Shipley Proposal Guide p.50."
- Test: Isolate units (Pytest in /tests/; cover edges like truncated PDFs); integrate after.
- Outputs: JSON for matrices/gaps; traceable to RFP/Shipley refs.
- Avoid: Heavy deps, global state. Always virtual env; update README for changes.
- LightRAG Native: Use LightRAG's document processing pipeline from the start—no custom extraction needed.

## Code Patterns

### Function Example

```python
def extract_requirements(processed_docs: dict, shipley_ref: str = "Proposal Guide p.50") -> dict:
    """
    Extract RFP reqs as JSON matrix from LightRAG processed documents, grounded in Shipley compliance checklist.

    Args:
        processed_docs: Dict of document_id -> content from LightRAG's full_docs storage.
        shipley_ref: Shipley reference (default from /docs).

    Returns:
        JSON dict with reqs.
    """
    # Reason: Uses LightRAG's native document processing; modular for chaining; uses Ollama prompt.
    # Implementation...
```
