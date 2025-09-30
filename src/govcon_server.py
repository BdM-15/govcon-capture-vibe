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

# Import our custom RFP routes
from api.rfp_routes import router as rfp_router

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