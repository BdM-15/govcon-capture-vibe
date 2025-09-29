# GovCon-CapThiThis project is a lightweight, zero-cost, open-source- **Compliance Matrix / Outline**: Simple JSON and table views you can filter—like a checklist of "Did we answer this?"

- **Gap Scan**: Estimates coverage (0–100%), points out missing or weak areas, suggests what to add.
- **Question Builder**: Spots unclear or conflicting items (e.g., page limits vs. stated task volume) and drafts professional clarification questions.
- **AI Chat Interface**: After parsing, chat with the data (e.g., "Summarize Section M sub-factors"). Uses RAG for cited responses; see example prompts below.
- **Simple Interface**: Web page (Streamlit) to upload files and view tables/JSON.to reduce capture and proposal prep effort in government contracting (GovCon). It uses a simple "search + local AI model" approach (often called RAG) to:

1. Parse federal solicitations (RFPs, PWS in attachments) for compliance requirements (e.g., Sections A-M, CLINs, evaluation factors).
2. Generate Shipley-style compliance matrices, proposal outlines, gap analyses, and ambiguity questions for Q&A periods.ject is a lightweight, zero-cost, open-source tool to reduce capture and proposal prep effort in government contracting (GovCon). It uses a simple "search + local AI model" approach (often called RAG) to:

3. Parse federal solicitations (RFPs, PWS in attachments) for compliance requirements (e.g., Sections A-M, CLINs, evaluation factors).
4. Generate Shipley-style compliance matrices, proposal outlines, gap analyses, and ambiguity questions for Q&A periods.project is a lightweight, zero-cost, open-source tool to reduce capture and proposal prep effort in government contracting (GovCon). It uses a modern multimodal RAG approach with RAG-Anything + LightRAG integration to:ure-Vibe: Local Tool to Read Federal RFPs and Track Requirements

## Executive Summary

Reads a federal RFP, pulls out the important stuff (deadlines, instructions, evaluation points, tasks), and gives you a clean checklist so you don’t miss anything. Runs fully on your own machine with local AI models—no fees, no data leaving your box.

**🚨 CURRENT STATUS: Complete System Rebuild in Progress**

The existing system produces unacceptable results (garbage text extraction, hallucinations, only 3-7 requirements extracted vs expected 80-100). We're rebuilding from scratch using modern AI techniques with RAG-Anything + LightRAG integration for reliable, accurate RFP analysis.

## Overview

This project is a lightweight, zero-cost, open-source tool to reduce capture and proposal prep effort in government contracting (GovCon). It uses a simple “search + local AI model” approach (often called RAG) to:

1. Parse federal solicitations (RFPs, PWS in attachments) for compliance requirements (e.g., Sections A-M, CLINs, evaluation factors).
2. Generate Shipley-style compliance matrices, proposal outlines, gap analyses, and ambiguity questions for Q&A periods.
3. Compare proposals (Word/PDF/Excel) against RFPs to flag misses (e.g., "US-sourced components").

Inspired by Shipley Proposal/Capture Guides and examples like Proposal Development Worksheets/Capture Plans (see /docs for PDFs). Built iteratively with vibe-coding and GitHub Copilot as the primary coder.

**Key Goals (Plain English)**

- Cut 70–80% of the manual grind of reading and tracing requirements.
- Run fully on your own computer (offline after setup).
- Avoid subscription or per-token API costs.
- Achieve 95%+ accuracy in requirement extraction from any RFP (no fixed quantity targets).

**Quick What-It-Does Summary**
Drop in an RFP (PDF/Word). The tool:

1. Processes documents using LightRAG's native document processing for text-based RFPs.
2. Extracts structured requirements using PydanticAI agents with fine-tuned models.
3. Indexes everything in LightRAG for semantic search and relationship mapping.
4. Builds compliance matrices, gap analyses, and clarification questions.
5. Provides AI chat interface for querying the processed RFP data.

![Shipley Proposal Guide Cover](assets/shipley-proposal-guide-cover.png)  
![Shipley Proposal Guide Title Page](assets/shipley-proposal-guide-title.png)  
![Shipley Capture Guide Cover](assets/shipley-capture-guide-cover.png)  
![Shipley Capture Guide Title Page](assets/shipley-capture-guide-title.png)  
![Proposal Development Worksheet Example](assets/proposal-development-worksheet.png)  
![Capture Plan Template](assets/capture-plan-template.png)  
![RFP Sample Page](assets/rfp-sample-page.png)

## Features (Planned/Iterative)

- **RFP Reading & Pulling Out Requirements**: Step-by-step pass through the document to make a clean, consistent list. Includes page/section citations for traceability.
  - Section A (Cover / SF-33 or SF1449): Deadlines (Q&A and proposal), time zone, points of contact, set-aside type, disclaimers, any listed incumbent contract IDs (e.g., "KBRwyle W52P1J-12-G-0061-0001"), eligibility limits (e.g., BOA / IDIQ), included or excluded functional areas (e.g., Transportation excluded).
  - Section B (with periods often clarified in Section F): Line items (CLINs / SLINs), type (FFP, T&M, etc.), quantities/units, base and option periods (e.g., base 366 days including a 60-day transition), funding ceilings or Not-To-Exceed values.
  - Section C (or in Section J attachments): Work description (PWS/SOW), tasks, locations, logistics notes (e.g., APS-4 maintenance/supply), what the Government provides vs. what the Contractor must provide, main functional areas.
  - Section L (Instructions): Required volumes, page limits, formatting (margins, font, naming), how/where to submit, required forms and certifications, how long the offer must stay valid (e.g., 180 days), how to send questions.
  - Section M (Evaluation): Factors and sub-factors (technical, past performance, price/cost, management, small business, etc.), order of importance, whether it is “best value/tradeoff” or “lowest price acceptable”, how risk is judged, how it ties back to Sections L and C.
  - Section J (Attachments List): Which attachment holds the PWS, deliverables list (CDRLs), Government Furnished lists (e.g., Attachment 0014 for Government Furnished Equipment), wage determinations, specs/drawings.
  - Section F (Deliveries / Performance): Delivery or event schedule, formal deliverables list, start-up (transition in) and closeout (transition out) items.
  - Section H (Special Requirements): Conflict of interest rules, key personnel rules, government-furnished property/equipment handling, cybersecurity (e.g., CMMC), travel rules, security clearance needs.
  - Other Items Derived: Small business participation targets, data rights notes, how “relevant” past performance is defined, any must-have certifications.
  - Planned Output Format (concept): One JSON array where each item looks like: `{ section, reference, type (instruction|evaluation|work|admin), snippet, importance_score }`.
  - Examples:
    - Raw extracted requirements: `examples/sample_requirements.json`
    - Questions for Government (QFG): `examples/sample_qfg.json`
    - Older minimal sample (legacy): `examples/sample_output.json`
- **Compliance Matrix / Outline**: Simple JSON and table views you can filter—like a checklist of “Did we answer this?”
- **Gap Scan**: Estimates coverage (0–100%), points out missing or weak areas, suggests what to add.
- **Question Builder**: Spots unclear or conflicting items (e.g., page limits vs. stated task volume) and drafts professional clarification questions.
- **AI Chat Interface**: After parsing, chat with the data (e.g., "Summarize Section M sub-factors"). Uses RAG for cited responses; see example prompts below.
- **Simple Interface**: Web page (Streamlit) to upload files and view tables/JSON.
- Future Additions: Read Excel for basis-of-estimate style data, reuse a library of past answers.

### Prompt Templates

Located in the `prompts/` folder for reuse / refinement:

- `extract_requirements_prompt.txt` – Builds the requirements JSON (see `examples/sample_requirements.json`).
- `generate_qfg_prompt.txt` – Creates clarification questions (see `examples/sample_qfg.json`).

#### Chat Query Examples

Example user inputs for the AI chat (save as .txt in prompts/ for testing):

- `chat_query_example1.txt`: "What are the sub-factors under Section M.3 for Transition Risk Management? Cite RFP refs and pages."
- `chat_query_example2.txt`: "Summarize critical themes from the parsed RFP, focusing on evaluation factors. Prioritize by importance score."
- `chat_query_example5.txt`: "Generate 3 clarification questions for ambiguities in PWS tasks (Section C or J Att). Reference critical summary themes."
- `chat_query_example7.txt`: "Provide an executive overview of the RFP like Shipley Capture Plan p.2, using critical summary and all reqs."

**No-Limit Extraction Policy**: The extraction prompt now outputs _every_ actionable requirement—no artificial cap. If a model output is ever cut off, a truncation marker object is appended so you know to rerun.

### Pipeline (Planned Flow)

1. **Document Processing**: Upload RFP files → LightRAG native document processing for text-based RFPs → structured content for analysis.
2. Extract Requirements (all sections, no truncation) → JSON.
3. Generate Questions for Government (optional if Q&A window open).

Status: Document processing pipeline complete; prompt templates complete.

## Tech Stack

- **Core**: Python 3.13+ with LightRAG for text-based RFP processing, enhanced with RAG-Anything for multimodal documents.
- **Document Processing**: LightRAG native document processing for text-based RFPs (Phase 1-3), enhanced with RAG-Anything for multimodal documents (Phase 4-6).
- **AI Agents**: PydanticAI for structured requirement extraction with fine-tuned Ollama models (Phase 7: Unsloth fine-tuning for domain specialization).
- **LLM/Embeddings**: Ollama (local) with 7-8B models (e.g., qwen2.5-coder:7b, bge-m3) for efficiency.
- **UI**: Streamlit for simple, interactive web app.
- **Env Setup**: uv/uvx (faster alternative to plain pip).
- **Dev Tools**: VS Code, GitHub Copilot/PowerShell for scripting.
- **Constraints**: Optimized for hardware (Lenovo LEGION 5i: i9-14900HX, RTX 4060, 64GB RAM)—CPU/GPU for Ollama, avoid heavy deps.

All open-source, local-run; no cloud/internet required post-setup.

## Setup Instructions

1. Clone: `git clone https://github.com/BdM-15/govcon-capture-vibe.git`
2. Install uv: Follow [uv docs](https://docs.astral.sh/uv/) (e.g., via curl).
3. Create env: `uv venv --python 3.13`
4. Activate: `source .venv/bin/activate` (or Windows equiv).
5. Install deps: `uv sync`
6. Ollama setup: `ollama pull qwen2.5-coder:7b` and `ollama pull bge-m3:latest`.
7. Run: `streamlit run app.py`

## Current Status

🚨 **Complete System Rebuild in Progress** (Following RFP_ANALYZER_ROADMAP.md)

**Previous System Issues (Resolved):**

- ❌ Garbage text extraction (90%+ PDF headers/footers)
- ❌ LLM hallucinations (generic responses)
- ❌ Only 3-7 requirements extracted (expected 80-100)
- ❌ Fragile JSON parsing with complex error handling

**New Architecture Implementation:**

- **Phase 1**: LightRAG foundation with clean text extraction ✅
- **Phase 2**: PydanticAI extraction agent ⏳
- **Phase 3**: Streamlit interface ⏳
- **Phase 4**: RAG-Anything multimodal enhancement ⏳
- **Phase 5**: Advanced features ⏳
- **Phase 6**: Production ready ⏳
- **Phase 7**: Unsloth fine-tuning for domain specialization ⏳

**Success Criteria:**

- 95%+ accuracy in requirement identification and classification (no fixed quantity targets)
- Process PDFs in <5 minutes with <4GB memory usage
- No hallucinations or generic responses
- Proper A-M section mapping and traceability
- Clean text extraction (no binary garbage)

## Development Approach

- **Structured Implementation**: Following 7-phase roadmap in RFP_ANALYZER_ROADMAP.md
- **LightRAG Core First**: Start with text-based RFP processing, enhance with RAG-Anything for multimodal
- **PydanticAI Agents**: Structured extraction with fine-tuned models for domain expertise
- **Unsloth Fine-tuning**: Phase 7 enhancement using Unsloth method for efficient domain specialization
- **Principles**: Minimal code (<2000 lines total, <500/file), modular components, type safety, comprehensive validation
- **Architecture**: LightRAG handles document processing → PydanticAI extracts requirements → LightRAG provides knowledge graph and retrieval
- **Inspirations/Forks**:
  - Shipley Guides (Proposal/Capture PDFs in /docs)
  - Repos: [HKUDS/RAG-Anything](https://github.com/HKUDS/RAG-Anything), [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG), [felixlkw/ai-rfp-simulator](https://github.com/felixlkw/ai-rfp-simulator),[abh2050/RFP_generation_langchain_agent_RAG](https://github.com/abh2050/RFP_generation_langchain_agent_RAG), [makegov/awesome-procurement-data](https://github.com/makegov/awesome-procurement-data)
- **Hardware Optimization**: Tuned for Lenovo LEGION 5i (i9-14900HX, RTX 4060, 64GB RAM)—7-8B Ollama models with GPU acceleration

## Contributing

Fork and PR. Focus on GovCon-specific enhancements (e.g., FAR/DFARS checks).

## License

MIT.

## Discussion Notes

- Zero-cost: Local Ollama, no paid APIs/tools.
- Flexibility: Handle varying RFP structures (e.g., DoD vs. civilian agencies).
- Prompts: Modular Ollama prompts for extraction/outline/gaps/ambiguities (JSON outputs).
- Future: Integrate with Capture Plans; add API if scaled.

Last updated: September 29, 2025 (scoped-down system rebuild focusing on RFP overview, requirements extraction, and chat features following RFP_ANALYZER_ROADMAP.md).
