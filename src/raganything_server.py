"""
RAG-Anything Server with LightRAG WebUI
Multimodal RAG system for government contracting documents

Architecture:
- src/server/config.py: Configuration (ontology-backed entity catalog, API credentials, chunking)
- src/server/initialization.py: RAGAnything initialization (tri-LLM, custom prompts)
- src/server/routes.py: FastAPI endpoints + semantic post-processing
- This file: Main entry point + server orchestration

Workflow:
1. Document Upload → /insert endpoint → UCF detection
2. Dual-Path Processing → Section-aware OR standard extraction
3. Entity Extraction → catalog-driven custom types (extraction LLM: non-reasoning)
4. Semantic Post-Processing → 8 LLM inference algorithms (reasoning LLM)
5. Knowledge Graph Storage → Neo4j or local GraphML
"""

# CRITICAL: Load .env BEFORE any imports that might import LightRAG
# LightRAG's dataclass field defaults evaluate os.getenv() at import time:
#   chunk_token_size: int = field(default=int(os.getenv("CHUNK_SIZE", 1200)))
# If .env isn't loaded first, it uses the hardcoded 1200 default
import os
import sys
from dotenv import load_dotenv
load_dotenv(override=True)

# Windows MAX_PATH mitigation for MinerU document processing
# MinerU CLI creates mineru-api-client-{random} temp dirs under the system temp
# directory. Long document names (≥60 chars) push the output path:
#   {TEMP}\mineru-api-client-{8}\output\{uuid-36}\{name-69}\auto\{name-69}_origin.pdf
# to ~259 chars — hitting Windows' 260-char MAX_PATH limit and causing
# FileNotFoundError when MinerU tries to write _origin.pdf.
# Fix: redirect Python's tempfile module to a shorter base path.
if sys.platform == "win32":
    import tempfile
    _mineru_temp = os.environ.get("MINERU_TEMP_DIR", r"C:\T")
    os.makedirs(_mineru_temp, exist_ok=True)
    tempfile.tempdir = _mineru_temp

# Now safe to import modules that may import LightRAG
import asyncio
import logging

# Import centralized settings AFTER load_dotenv
from src.core import get_settings

# Suppress verbose logging from libraries
logging.getLogger("raganything").setLevel(logging.WARNING)
logging.getLogger("lightrag").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

from lightrag.api.config import global_args
import uvicorn

# Import modular components (AFTER load_dotenv() so they see environment variables)
from src.server.config import configure_raganything_args
from src.server.initialization import initialize_raganything, get_rag_instance
from src.server.app_runtime import build_server_runtime
from src.server.routes import register_custom_ingestion_routes
from src.server.startup_banner import build_startup_banner_items
from src.server.ui_query_bridge import make_ui_query_bridges
from src.server.ui_routes import register_ui
from lightrag.api.lightrag_server import create_app

# Set up logging
logger = logging.getLogger(__name__)


async def main():
    """Main server startup with RAG-Anything + LightRAG WebUI
    
    Architecture:
    - RAG-Anything: Document ingestion (MinerU multimodal parser)
    - LightRAG: WebUI + query endpoints (knowledge graph queries)
    - Semantic Post-Processing: Automatic LLM-powered relationship inference
    
    Custom Features:
    - /insert endpoint: Overrides default LightRAG for semantic enhancement
    - Background monitor: Auto-detects WebUI uploads, triggers inference
    - UCF detection: Section-aware extraction for federal RFPs
    """
    # Initialization message moved to app.py for cleaner startup
    
    # Step 1: Configure LightRAG global_args
    configure_raganything_args()
    
    # Step 2: Initialize RAG-Anything for document processing
    await initialize_raganything()
    rag_instance = get_rag_instance()
    
    if not rag_instance:
        raise RuntimeError("Failed to initialize RAG-Anything instance")
    
    settings = get_settings()
    runtime = build_server_runtime(
        rag_instance,
        settings=settings,
        global_args_obj=global_args,
        logger=logger,
        create_app_fn=create_app,
        register_custom_ingestion_routes_fn=register_custom_ingestion_routes,
        make_ui_query_bridges_fn=make_ui_query_bridges,
        register_ui_fn=register_ui,
        build_startup_banner_items_fn=build_startup_banner_items,
    )

    # Step 5: Start server
    config = uvicorn.Config(app=runtime.app, host=runtime.host, port=runtime.port, log_level="info")
    server_instance = uvicorn.Server(config)
    await server_instance.serve()


if __name__ == "__main__":
    asyncio.run(main())
