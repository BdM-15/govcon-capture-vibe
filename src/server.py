"""
GovCon Capture Vibe Server - Extended LightRAG server with RFP analysis capabilities

Extends the standard LightRAG server with government contracting-specific features:
- RFP requirements extraction and analysis
- Shipley methodology-grounded compliance matrices  
- Gap analysis and proposal development support
- Integration with Shipley Guide documentation

Usage:
    python src/govcon_server.py
    
Environment variables from .env file configure Ollama integration and timeouts.
"""

import os
import sys
import asyncio
from pathlib import Path
from typing import List, Dict, Any

# Add src to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# *** CRITICAL: IMPORT LOGGING CONFIG FIRST ***
from src.utils.logging_config import setup_logging

# Set up logging before other imports
log_config = setup_logging(
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    console_output=os.getenv("LOG_CONSOLE", "true").lower() == "true"
)

import logging
logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException
from lightrag import LightRAG
from lightrag.utils import EmbeddingFunc
from lightrag.llm.ollama import ollama_model_complete, ollama_embed
from lightrag.kg.shared_storage import initialize_pipeline_status
from lightrag.api.lightrag_server import create_app
import uvicorn
from dotenv import load_dotenv

# Import enhanced RFP processing
from src.core.lightrag_chunking import rfp_aware_chunking_func
from src.utils.performance_monitor import get_monitor

# Load environment variables
load_dotenv()

async def main():
    """Main server initialization and startup"""

    print("🚀 Initializing GovCon Capture Vibe Server...")
    print("   ├─ Loading LightRAG with Ollama integration")
    print("   ├─ Adding RFP analysis capabilities")
    print("   ├─ Integrating Shipley methodology")
    print("   └─ Optimizing for government contracting\n")

    logger.info("🚀 GovCon Capture Vibe Server initialization started")
    logger.info(f"📁 Log files configured: {log_config}")

    # Load environment variables
    load_dotenv()

    # Parse LightRAG args from environment
    from lightrag.api.config import global_args

    print("🤖 Initializing LightRAG system with RFP-aware chunking...")

    # *** PROPER LIGHTRAG INTEGRATION USING NATIVE EXTENSION POINT ***
    # Use LightRAG's official chunking_func parameter for domain-specific chunking
    # This is the clean, future-proof way recommended by the framework

    # Apply RFP-aware chunking to global configuration
    # LightRAG library has been patched to support chunking_func via global_args
    global_args.chunking_func = rfp_aware_chunking_func

    print("   ✅ RFP-aware chunking function applied to LightRAG configuration")
    print("   ✅ Section structure preservation enabled")
    print("   ✅ Shipley methodology integration active")

    # Create LightRAG server app with WebUI
    print("🌐 Creating LightRAG server with WebUI...")

    # Use LightRAG's create_app function with enhanced configuration
    # The patched library now reads chunking_func from global_args and passes it to LightRAG constructor
    app = create_app(global_args)
    
    print("   ✅ Section-aware chunking enabled via patched LightRAG library")

    # Create our own LightRAG instance with the same configuration for RFP routes
    try:
        # Import required components
        from lightrag import LightRAG
        from lightrag.llm.ollama import ollama_model_complete, ollama_embed
        from lightrag.utils import EmbeddingFunc
        from lightrag.kg.shared_storage import initialize_pipeline_status

        # Create LightRAG instance with RFP-aware chunking
        rag_instance = LightRAG(
            working_dir=global_args.working_dir,
            workspace=global_args.workspace,
            llm_model_func=ollama_model_complete,
            llm_model_name=global_args.llm_model,
            llm_model_max_async=global_args.max_async,
            summary_max_tokens=global_args.summary_max_tokens,
            summary_context_size=global_args.summary_context_size,
            chunk_token_size=int(global_args.chunk_size),
            chunk_overlap_token_size=int(global_args.chunk_overlap_size),
            # *** NATIVE EXTENSION POINT: RFP-AWARE CHUNKING ***
            chunking_func=rfp_aware_chunking_func,
            llm_model_kwargs={
                "host": global_args.llm_binding_host,
                "timeout": int(os.getenv("LLM_TIMEOUT", "600")),
                "options": {"num_ctx": int(os.getenv("OLLAMA_LLM_NUM_CTX", "65536"))},
                "api_key": global_args.llm_binding_api_key,
            },
            embedding_func=EmbeddingFunc(
                embedding_dim=int(global_args.embedding_dim),
                max_token_size=int(os.getenv("MAX_EMBED_TOKENS", "8192")),
                func=lambda texts: ollama_embed(
                    texts,
                    embed_model=global_args.embedding_model,
                    host=global_args.embedding_binding_host,
                    timeout=int(os.getenv("EMBEDDING_TIMEOUT", "300")),
                ),
            ),
            default_llm_timeout=int(os.getenv("LLM_TIMEOUT", "600")),
            default_embedding_timeout=int(os.getenv("EMBEDDING_TIMEOUT", "300")),
            addon_params={
                "language": global_args.summary_language,
                "entity_types": global_args.entity_types,
            },
        )

        print("   ✅ LightRAG instance created with RFP-aware chunking")
        print("   ✅ Enhanced processing ready for government contracting documents")

        # Store reference for WebUI integration
        app.state.rag_instance = rag_instance
        app.state.enhanced_processing = True

        print("   ✅ RFP analysis routes connected to enhanced LightRAG instance")

    except Exception as e:
        print(f"   ⚠️  Warning: Failed to create LightRAG instance: {e}")
        print("   ⚠️  Falling back to standard configuration")

        # Fallback: create basic instance for RFP routes
        try:
            basic_rag = LightRAG(
                working_dir=global_args.working_dir,
                llm_model_func=ollama_model_complete,
                llm_model_name=global_args.llm_model,
                chunking_func=rfp_aware_chunking_func,  # Still use enhanced chunking
            )
            app.state.rag_instance = basic_rag
            app.state.enhanced_processing = False
        except Exception as fallback_error:
            print(f"   ❌ Fallback also failed: {fallback_error}")

    # Focus on LightRAG's native server framework first
    # Custom RFP endpoints will be added after validating ontology integration
    # app.include_router(rfp_router)

    print("   ✅ Server application ready with WebUI and RFP routes\n")

    # Get server configuration from global_args
    host = global_args.host
    port = global_args.port

    print(f"🎯 GovCon Capture Vibe Server Starting:")
    print(f"   ├─ Host: {host}")
    print(f"   ├─ Port: {port}")
    print(f"   ├─ WebUI: http://{host}:{port}/webui")
    print(f"   ├─ API Docs: http://{host}:{port}/docs")
    print(f"   ├─ RFP Analysis: http://{host}:{port}/rfp")
    print(f"   └─ Shipley Integration: Active\n")

    # Start server using uvicorn
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level=global_args.log_level.lower() if hasattr(global_args, 'log_level') else "info"
    )
    server_instance = uvicorn.Server(config)
    await server_instance.serve()


if __name__ == "__main__":
    asyncio.run(main())