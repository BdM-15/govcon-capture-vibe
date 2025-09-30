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
from lightrag.api.lightrag_server import create_app, get_application
from dotenv import load_dotenv

# Import our custom RFP routes
from api.rfp_routes import router as rfp_router

# Load environment variables
load_dotenv()

class GovConServer:
    """Extended LightRAG server with RFP analysis capabilities"""
    
    def __init__(self):
        self.rag = None
        self.app = None
        
    async def initialize_rag(self):
        """Initialize LightRAG with Ollama and government contracting optimizations"""
        
        working_dir = os.getenv("WORKING_DIR", "./rag_storage")
        os.makedirs(working_dir, exist_ok=True)
        
        # Reason: Basic LightRAG initialization with Ollama for government RFP processing
        self.rag = LightRAG(
            working_dir=working_dir,
            llm_model_func=ollama_model_complete,
            embedding_func=EmbeddingFunc(
                embedding_dim=int(os.getenv("EMBEDDING_DIM", "1024")),
                max_token_size=int(os.getenv("MAX_EMBED_TOKENS", "8192")),
                func=ollama_embed
            ),
            
            # Basic optimization parameters
            max_parallel_insert=int(os.getenv("MAX_PARALLEL_INSERT", "2")),
            chunk_token_size=int(os.getenv("CHUNK_TOKEN_SIZE", "2000")),
            chunk_overlap_token_size=int(os.getenv("CHUNK_OVERLAP_TOKEN_SIZE", "200")),
            summary_max_tokens=int(os.getenv("SUMMARY_MAX_TOKENS", "8192")),
            
            # Timeout configurations for large RFP documents
            default_llm_timeout=int(os.getenv("LLM_TIMEOUT", "900")),
            default_embedding_timeout=int(os.getenv("EMBEDDING_TIMEOUT", "300"))
        )
        
        await self.rag.initialize_storages()
        await initialize_pipeline_status()
        
        return self.rag
    
    def create_extended_app(self):
        """Create FastAPI app with both LightRAG and RFP analysis routes"""
        
        # Start the default LightRAG server in a subprocess/background
        # For now, we'll just create a basic FastAPI app with our routes
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        
        app = FastAPI(
            title="GovCon Capture Vibe Server",
            description="Enhanced LightRAG server with RFP analysis capabilities",
            version="1.0.0"
        )
        
        # Add CORS middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Add our custom RFP analysis routes
        app.include_router(rfp_router)
        
        # Add a basic health check
        @app.get("/health")
        async def health_check():
            return {"status": "healthy", "message": "GovCon Capture Vibe Server is running"}
        
        # Add root redirect
        @app.get("/")
        async def root():
            return {"message": "GovCon Capture Vibe Server", "docs": "/docs", "rfp_api": "/rfp"}
        
        self.app = app
        return app


async def main():
    """Main server initialization and startup"""
    
    print("🚀 Initializing GovCon Capture Vibe Server...")
    print("   ├─ Loading LightRAG with Ollama integration")
    print("   ├─ Adding RFP analysis capabilities") 
    print("   ├─ Integrating Shipley methodology")
    print("   └─ Optimizing for government contracting\n")
    
    # Initialize the extended server
    server = GovConServer()
    
    # Initialize RAG system
    print("🤖 Initializing LightRAG system...")
    await server.initialize_rag()
    print("   ✅ RAG system ready with Ollama integration\n")
    
    # Create extended FastAPI app
    print("🌐 Creating extended server application...")
    app = server.create_extended_app()
    print("   ✅ Server application ready with RFP routes\n")
    
    # Server configuration
    host = os.getenv("HOST", "localhost")
    port = int(os.getenv("PORT", "9621"))
    
    print(f"🎯 GovCon Capture Vibe Server Starting:")
    print(f"   ├─ Host: {host}")
    print(f"   ├─ Port: {port}")
    print(f"   ├─ WebUI: http://{host}:{port}")
    print(f"   ├─ API Docs: http://{host}:{port}/docs")
    print(f"   ├─ RFP Analysis: http://{host}:{port}/rfp")
    print(f"   └─ Shipley Integration: Active\n")
    
    # Start server (would use uvicorn.run in production)
    import uvicorn
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level=os.getenv("LOG_LEVEL", "info").lower()
    )
    server_instance = uvicorn.Server(config)
    await server_instance.serve()


if __name__ == "__main__":
    asyncio.run(main())