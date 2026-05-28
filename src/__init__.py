"""
GovCon Capture Vibe - Ontology-Based RAG for Government Contract Analysis

Module Architecture & Dependency Flow:

┌─────────────────────────────────────────────────────────────┐
│                    Module Dependency Hierarchy              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. core/ (Foundation Layer)                                │
│     ├── prompt_loader.py - External prompt loading         │
│     └── Shared utilities used by all modules               │
│                                                             │
│  2. ingestion/ & inference/ (Processing Layer)              │
│     ├── ingestion/detector.py - UCF format detection       │
│     ├── ingestion/processor.py - Section-aware extraction  │
│     ├── inference/graph_io.py - GraphML/kv_store I/O       │
│     └── inference/engine.py - LLM relationship inference   │
│     Dependencies: core/                                     │
│                                                             │
│  3. server/ (Orchestration Layer)                           │
│     ├── config.py - Environment configuration              │
│     ├── native_lightrag_runtime.py - Native LightRAG setup│
│     └── routes.py - FastAPI endpoints                      │
│     Dependencies: core/, ingestion/, inference/            │
│                                                             │
│  4. Server entry points                                    │
│     Dependencies: server/                                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘

Dependency Flow (Bottom-Up):
    
    core
      ↓
    ┌───────────┬────────────┐
    ↓           ↓            ↓
  ingestion  inference  (independent)
    ↓           ↓
    └───────────┴────────────┘
              ↓
            server
              ↓
    server entry point + app

Import Rules:
- ✅ core can import: nothing (foundation)
- ✅ ingestion/inference can import: core
- ✅ server can import: core, ingestion, inference
- ❌ NO circular imports (enforced by structure)
- ❌ NO horizontal imports (ingestion <-> inference)

Module Responsibilities:

core/
  - Prompt loading from external Markdown files
  - Shared utilities and constants
  - Domain-agnostic helpers

ingestion/
  - UCF (Uniform Contract Format) detection
  - Section-aware document processing
  - Format normalization

inference/
  - LLM-powered relationship inference
  - Knowledge graph enhancement
  - 5 semantic inference algorithms:
    1. Document hierarchy (DOCUMENT → SECTION)
    2. Clause clustering (FAR/DFARS → sections)
    3. Instruction↔evaluation mapping (proposal_instruction → evaluation_factor; UCF Section L↔M or non-UCF equivalent)
    4. Requirement evaluation (requirements → factors)
    5. Work-deliverable linking (SOW → deliverables)

server/
  - Environment configuration (catalog-driven entity types)
  - Native LightRAG runtime initialization
  - FastAPI endpoints
  - Semantic post-processing orchestration

Usage Example:

    # Entry point (app.py or server module)
    from src.server.native_lightrag_runtime import initialize_native_lightrag
    
    # Server imports from ingestion and inference
    from src.ingestion import detect_ucf_format
    from src.inference import infer_all_relationships
    
    # Ingestion and inference import from core
    from src.core.prompt_loader import load_prompt

For detailed architecture documentation, see:
- HANDOFF_SUMMARY.md - Branch 004 results and quick start
- docs/BRANCH_004_CODE_OPTIMIZATION.md - Charter and constraints
- README.md - Current project overview
- docs/README.md - Current documentation index
"""

__version__ = "4.0.0"
__branch__ = "004-code-optimization"
__status__ = "COMPLETE - Ready for merge to main"
