# Copilot Instructions for GovCon-Capture Project

## Project Overview
Build a local, zero-cost RAG app in Python to automate federal RFP compliance analysis. Features: Extract requirements (Sections A-M, J attachments), generate Shipley-style matrices/outlines, perform gap analysis on proposals (PDF/Word/Excel), and detect ambiguities for Q&A. Use modular Ollama prompts outputting JSON. Inspired by Shipley Proposal/Capture Guides and attached worksheets/plans.

## Guiding Principles (Always Adhere)
- **Simplicity**: Generate minimal, lean code—no bloat, overfitting, or unnecessary features. Target <2000 lines total; use concise functions/prompts. Avoid complex logic; prefer straightforward implementations.
- **Modularity**: Structure as independent components (e.g., RFP parser module, gap analyzer function). Build/test one feature at a time for easy scaling (e.g., add Excel parsing later).
- **Maintainability**: Clean, readable Python with docstrings and comments. No magic numbers; use YAML configs (e.g., settings.yaml for Ollama models/endpoints).
- **Scalability/Flexibility**: Design for future adds without rework. Handle varying RFP structures (e.g., PWS in attachments); make prompts adaptable.
- **Hardware Optimization**: Tune for Lenovo LEGION 5i (i9-14900HX, RTX 4060, 64GB RAM)—use 7-8B Ollama models (e.g., llama3, mistral, nomic-embed-text); chunk docs for large RFPs (500+ pages) to avoid OOM; support CPU/GPU via Ollama.
- **Zero-Cost/Open-Source**: Fully local/offline—no APIs, networks, or paid tools. Outputs in plain English for GovCon pros (no ML jargon).
- **Features Focus**: Chain Ollama prompts for: Req extraction (JSON matrix), outline gen, gap scoring (0-100%), ambiguity Q&A (professional questions). Reference Shipley formats (e.g., compliance checklists).

## Tech Stack
- Python 3.13+.
- Env: uv/uvx for deps (no pip); e.g., `uv add streamlit lightrag ollama pypdf2 python-docx openpyxl`.
- UI: Streamlit for file uploads/queries/results (tables/JSON).
- Core: LightRAG + Ollama (local); fallback to LangChain if needed.
- Doc Handling: PyPDF2/docx/openpyxl; J-attachment loader for PWS.

## Usage Tips for Copilot
When generating code:
- Start small: E.g., "Implement RFP extraction prompt in a function."
- Test Locally: Include simple tests (e.g., on APS-4 RFP sample).
- Outputs: Always JSON for matrices/gaps; traceable to RFP refs.
- Avoid: Heavy deps, global state, or rigid testing frameworks.

Version: 1.0 | Updated: 2025-09-27