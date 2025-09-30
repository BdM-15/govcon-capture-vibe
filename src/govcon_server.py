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

# Add src to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from lightrag import LightRAG
from lightrag.utils import EmbeddingFunc
from lightrag.llm.ollama import ollama_model_complete, ollama_embed
from lightrag.kg.shared_storage import initialize_pipeline_status
from lightrag.api.lightrag_server import create_app
import uvicorn
from dotenv import load_dotenv

# Import our custom RFP routes and enhanced processing
from api.rfp_routes import router as rfp_router, set_rag_instance
import sys
sys.path.append(str(Path(__file__).parent))
from lightrag_rfp_integration import RFPAwareLightRAG

# Load environment variables
load_dotenv()

async def main():
    """Main server initialization and startup"""
    
    print("🚀 Initializing GovCon Capture Vibe Server...")
    print("   ├─ Loading LightRAG with Ollama integration")
    print("   ├─ Adding RFP analysis capabilities") 
    print("   ├─ Integrating Shipley methodology")
    print("   └─ Optimizing for government contracting\n")

    # Load environment variables
    load_dotenv()
    
    # Parse LightRAG args from environment
    from lightrag.api.config import global_args
    
    print("🤖 Initializing LightRAG system...")
    print("   ✅ RAG system ready with Ollama integration\n")
    
    # Create LightRAG server app with WebUI using the correct API
    print("🌐 Creating LightRAG server with WebUI...")
    
    # Use LightRAG's create_app function with global_args
    app = create_app(global_args)
    
    # The LightRAG instance is created inside create_app but not accessible.
    # We need to create our own instance with the same configuration to pass to RFP routes
    try:
        # Import LightRAG and create an instance with the same config as the server
        from lightrag import LightRAG
        from lightrag.llm.ollama import ollama_model_complete, ollama_embed
        from lightrag.utils import EmbeddingFunc
        from lightrag.kg.shared_storage import initialize_pipeline_status
        
        # Create LightRAG instance with same config as the server
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
            llm_model_kwargs={
                "host": global_args.llm_binding_host,
                "timeout": int(os.getenv("LLM_TIMEOUT", "600")),
                "options": {"num_ctx": int(os.getenv("NUM_CTX", "65536"))},
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
        
        # Pass the LightRAG instance to RFP routes
        set_rag_instance(rag_instance)
        
        # Initialize RFP-aware processor for enhanced document processing
        rfp_processor = RFPAwareLightRAG(rag_instance)
        
        # Store reference to enhanced processor for potential future use
        app.state.rfp_processor = rfp_processor
        
        print("   ✅ LightRAG instance created and connected to RFP analysis routes")
        print("   ✅ RFP-aware document processor initialized with Shipley methodology")
        
    except Exception as e:
        print(f"   ⚠️  Warning: Failed to create LightRAG instance for RFP routes: {e}")
    
    # Add our custom RFP analysis routes to the existing app
    app.include_router(rfp_router)
    
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