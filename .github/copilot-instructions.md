# Copilot Instructions for GovCon-Capture-Vibe Project

## Project Overview

Local, zero-cost RAG app in Python for federal RFP compliance automation. Parse RFPs/PWS (A-M sections, J atts), generate Shipley-style matrices/outlines/gaps/Q&A. Ground all features in /docs Shipley materials (e.g., Proposal Guide for compliance checklists, Capture Guide for strategy, worksheets/plans for formats—reference specific pages in comments/prompts).

**🚨 CURRENT STATUS: Complete System Rebuild in Progress**

Following RFP_ANALYZER_ROADMAP.md with incremental approach: Start with LightRAG core for text-based RFPs (90%+ of cases), then enhance with RAG-Anything for multimodal documents. Previous system produced garbage text extraction and hallucinations - new architecture eliminates these issues.

## Guiding Principles (Always Adhere)

1. **Simplicity**: Minimal code (<2000 lines total, <500/file); no bloat/overfitting. Concise functions/prompts; straightforward logic.
2. **Modularity**: Independent components (e.g., document_processor.py, extraction_agent.py, knowledge_graph.py). Build/test one-by-one; relative imports.
3. **Maintainability**: Clean Python with docstrings/comments. Follow PEP-8 (79-char lines, spacing). Type hints; "# Reason:" for complex logic.
4. **Scalability/Flexibility**: Future-proof (e.g., add BOE parsing); adapt to RFP variations.
5. **Hardware Optimization**: Tune for Lenovo LEGION 5i (i9-14900HX, RTX 4060, 64GB)—7-8B Ollama models (qwen2.5-coder/nomic-embed-text); chunk for large docs (500+ pages) to avoid OOM; CPU/GPU via Ollama.
6. **Zero-Cost/Open-Source**: Local/offline—no APIs/networks. Plain-English outputs for GovCon (no ML jargon).
7. **Shipley Grounding**: Align features to /docs (e.g., mimic Worksheet checklists, Capture Plan overviews). Reference in code/prompts.
8. **Unsloth Fine-tuning**: Phase 7 enhancement using Unsloth method for efficient training of domain-specific SLMs on RFP requirements extraction.

## Tech Stack

- Python 3.13+ (latest stable).
- Env: uv/uvx for deps (no pip); always use/run in virtual env—scripts check/activate (e.g., shebang: #!/usr/bin/env python, comments remind).
- UI: Streamlit for uploads/queries/results (tables/JSON).
- Core: LightRAG for text-based RFP processing (Phase 1-3), enhanced with RAG-Anything for multimodal documents (Phase 4-6).
- Document Processing: LightRAG native document processing for text-based RFPs (Phase 1-3), enhanced with RAG-Anything for multimodal documents (Phase 4-6).
- AI Agents: PydanticAI for structured requirement extraction with fine-tuned Ollama models (Phase 7: Unsloth fine-tuning for domain specialization).
- Config: .env for secrets (e.g., OLLAMA_BASE_URL); config.py centralizes access with defaults/validation.

## Usage Tips for Copilot

- Generate small: E.g., "Implement req extraction using LightRAG processed documents with PydanticAI agent, grounded in Shipley Proposal Guide p.50."
- Test: Isolate units (Pytest in /tests/; cover edges like truncated PDFs); integrate after.
- Outputs: JSON for matrices/gaps; traceable to RFP/Shipley refs.
- Avoid: Heavy deps, global state. Always virtual env; update README for changes.
- Unsloth Fine-tuning: Phase 7 enhancement using Unsloth method for efficient domain specialization—develop robust training set of 500-1000 labeled RFP examples.

## Code Patterns

### Function Example

```python
def extract_requirements(processed_docs: dict, shipley_ref: str = "Proposal Guide p.50") -> dict:
    """
    Extract RFP reqs as JSON matrix from LightRAG processed documents using PydanticAI agent, grounded in Shipley compliance checklist.

    Args:
        processed_docs: Dict of document_id -> content from LightRAG's full_docs storage.
        shipley_ref: Shipley reference (default from /docs).

    Returns:
        JSON dict with reqs.
    """
    # Reason: Uses LightRAG's native document processing; structured extraction with PydanticAI; modular for chaining; uses Ollama prompt.
    # Implementation...
```
