# Copilot Instructions for GovCon-Capture-Vibe Project

## Project Overview
Local, zero-cost RAG app in Python for federal RFP compliance automation. Parse RFPs/PWS (A-M sections, J atts), generate Shipley-style matrices/outlines/gaps/Q&A. Ground all features in /docs Shipley materials (e.g., Proposal Guide for compliance checklists, Capture Guide for strategy, worksheets/plans for formats—reference specific pages in comments/prompts).

## Guiding Principles (Always Adhere)
1. **Simplicity**: Minimal code (<2000 lines total, <500/file); no bloat/overfitting. Concise functions/prompts; straightforward logic.
2. **Modularity**: Independent components (e.g., rfp_parser.py, gap_analyzer.py). Build/test one-by-one; relative imports.
3. **Maintainability**: Clean Python with docstrings/comments. Follow PEP-8 (79-char lines, spacing). Type hints; "# Reason:" for complex logic.
4. **Scalability/Flexibility**: Future-proof (e.g., add BOE parsing); adapt to RFP variations.
5. **Hardware Optimization**: Tune for Lenovo LEGION 5i (i9-14900HX, RTX 4060, 64GB)—7-8B Ollama models (llama3/mistral/nomic-embed-text); chunk for large docs (500+ pages) to avoid OOM; CPU/GPU via Ollama.
6. **Zero-Cost/Open-Source**: Local/offline—no APIs/networks. Plain-English outputs for GovCon (no ML jargon).
7. **Shipley Grounding**: Align features to /docs (e.g., mimic Worksheet checklists, Capture Plan overviews). Reference in code/prompts.
8. **Consistency**: Snake_case naming; modular structure (utils/ for loaders, prompts/ for Ollama chains). JSON outputs; robust error handling (e.g., log PDF parse fails).

## Tech Stack
- Python 3.13+ (latest stable).
- Env: uv/uvx for deps (no pip); always use/run in virtual env—scripts check/activate (e.g., shebang: #!/usr/bin/env python, comments remind).
- UI: Streamlit for uploads/queries/results (tables/JSON).
- Core: LightRAG + Ollama (local); LangChain fallback.
- Doc Handling: PyPDF2/docx/openpyxl; J-loader for atts.
- Config: .env for secrets (e.g., OLLAMA_BASE_URL); config.py centralizes access with defaults/validation.

## Usage Tips for Copilot
- Generate small: E.g., "Implement req extraction in rfp_parser.py, grounded in Shipley Proposal Guide p.50."
- Test: Isolate units (Pytest in /tests/; cover edges like truncated PDFs); integrate after.
- Outputs: JSON for matrices/gaps; traceable to RFP/Shipley refs.
- Avoid: Heavy deps, global state. Always virtual env; update README for changes.
- Beast Mode: Compatible—focus on code/tools (e.g., browse_pdf_attachment for /docs Shipley).

## Code Patterns
### Function Example
```python
def extract_requirements(rfp_text: str, shipley_ref: str = "Proposal Guide p.50") -> dict:
    """
    Extract RFP reqs as JSON matrix, grounded in Shipley compliance checklist.

    Args:
        rfp_text: Raw RFP content.
        shipley_ref: Shipley reference (default from /docs).

    Returns:
        JSON dict with reqs.
    """
    # Reason: Modular for chaining; uses Ollama prompt.
    # Implementation...