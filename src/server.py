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

# Import our custom RFP routes and enhanced processing
from src.api.rfp_routes import router as rfp_router, set_rag_instance
from src.core.lightrag_integration import RFPAwareLightRAG
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
    
    print("🤖 Initializing LightRAG system...")
    
    # *** CRITICAL: PATCH LIGHTRAG BEFORE CREATE_APP ***
    # We need to monkey-patch LightRAG's core methods BEFORE create_app is called
    # This is the only way to ensure our enhanced processing is used
    
    print("   🔧 Patching LightRAG core with enhanced RFP processing...")
    
    import lightrag
    from src.core.lightrag_integration import RFPAwareLightRAG
    
    # Store original LightRAG class
    OriginalLightRAG = lightrag.LightRAG
    
    # Create a new LightRAG class that automatically wraps with RFP awareness
    class EnhancedLightRAG(OriginalLightRAG):
        """Enhanced LightRAG that automatically applies RFP processing"""
        
        def __init__(self, *args, **kwargs):
            # Initialize base LightRAG
            super().__init__(*args, **kwargs)
            
            # Wrap self with RFP awareness
            self._rfp_wrapper = RFPAwareLightRAG(self)
            
            print(f"   ✅ LightRAG instance enhanced with RFP awareness")
        
        async def ainsert(self, content, **kwargs):
            """Override ainsert to use RFP-aware processing"""
            print(f"   🔍 Enhanced ainsert called with content type: {type(content)}")
            print(f"   🔍 Content length: {len(str(content)) if content else 0}")
            print(f"   🔍 Kwargs: {list(kwargs.keys())}")
            
            try:
                # Use our enhanced wrapper for processing
                print(f"   🎯 Calling enhanced wrapper ainsert...")
                result = await self._rfp_wrapper.ainsert(content, **kwargs)
                print(f"   ✅ Enhanced processing completed successfully")
                return result
            except Exception as e:
                print(f"   ⚠️ Enhanced processing failed, using standard: {e}")
                import traceback
                print(f"   📋 Traceback: {traceback.format_exc()}")
                # Fallback to standard processing
                return await super().ainsert(content, **kwargs)
        
        async def aquery(self, query, **kwargs):
            """Override aquery to use RFP-aware processing"""
            try:
                # Use our enhanced wrapper for querying
                return await self._rfp_wrapper.aquery(query, **kwargs)
            except Exception as e:
                print(f"   ⚠️ Enhanced query failed, using standard: {e}")
                # Fallback to standard processing
                return await super().aquery(query, **kwargs)
        
        def get_processing_status(self):
            """Get RFP processing status"""
            if hasattr(self, '_rfp_wrapper'):
                return self._rfp_wrapper.get_processing_status()
            return {"enhanced_processing_available": False}
        
        def detect_rfp_document(self, *args, **kwargs):
            """Delegate RFP detection to wrapper"""
            if hasattr(self, '_rfp_wrapper'):
                return self._rfp_wrapper.detect_rfp_document(*args, **kwargs)
            return False
    
    # Replace LightRAG class globally
    lightrag.LightRAG = EnhancedLightRAG
    
    # Also replace in the API module
    import lightrag.api.lightrag_server as lightrag_server_module
    lightrag_server_module.LightRAG = EnhancedLightRAG
    
    # *** PROPER LIGHTRAG INTEGRATION - CUSTOM CHUNKING FUNCTION ***
    # Instead of monkey-patching, we use LightRAG's official extension point:
    # the configurable chunking_func parameter
    
    from src.core.chunking import ShipleyRFPChunker
    
    def create_rfp_aware_chunking_function():
        """
        Create custom chunking function for LightRAG that preserves RFP structure
        
        This is the PROPER way to extend LightRAG for domain-specific needs.
        LightRAG's chunking_func is designed to be replaced for custom domains.
        """
        rfp_chunker = ShipleyRFPChunker()
        
        def rfp_aware_chunking_func(content: str, **kwargs) -> List[Dict[str, Any]]:
            """
            Custom chunking function that preserves RFP section structure
            
            Args:
                content: Document text to chunk
                **kwargs: Additional parameters (chunk_token_size, etc.)
                
            Returns:
                List of chunk dictionaries compatible with LightRAG
            """
            try:
                # Check if this looks like an RFP document
                is_rfp = rfp_chunker._detect_rfp_structure(content)
                
                if is_rfp:
                    print(f"   🎯 RFP document detected - using enhanced section-aware chunking")
                    
                    # Use our enhanced RFP chunking
                    rfp_chunks = rfp_chunker.process_document(content)
                    
                    # Convert to LightRAG format
                    lightrag_chunks = []
                    for i, chunk in enumerate(rfp_chunks):
                        chunk_dict = {
                            'content': chunk.content,
                            'metadata': {
                                'chunk_id': chunk.chunk_id,
                                'section_id': chunk.section_id,
                                'section_title': chunk.section_title,
                                'subsection_id': chunk.subsection_id,
                                'chunk_order': chunk.chunk_order,
                                'page_number': chunk.page_number,
                                'relationships': chunk.relationships,
                                'requirements_count': len(chunk.requirements),
                                'has_requirements': len(chunk.requirements) > 0,
                                'rfp_enhanced': True,
                                **chunk.metadata
                            }
                        }
                        lightrag_chunks.append(chunk_dict)
                    
                    print(f"   ✅ Enhanced chunking: {len(lightrag_chunks)} RFP-aware chunks created")
                    return lightrag_chunks
                
                else:
                    print(f"   📄 Standard document - using default LightRAG chunking")
                    # Fall back to standard LightRAG chunking for non-RFP documents
                    from lightrag.operate import chunking_by_token_size
                    return chunking_by_token_size(content, **kwargs)
                    
            except Exception as e:
                print(f"   ⚠️ Enhanced chunking failed: {e}")
                # Always fall back to standard chunking on error
                from lightrag.operate import chunking_by_token_size
                return chunking_by_token_size(content, **kwargs)
        
        return rfp_aware_chunking_func
    
    # Create the custom chunking function
    rfp_chunking_func = create_rfp_aware_chunking_function()
    
    print("   ✅ RFP-aware chunking function created")
    print("   ✅ RAG system ready with Ollama integration\n")
    
    # *** APPLY CUSTOM CHUNKING TO LIGHTRAG'S CREATE_APP ***
    # We need to modify the global_args to use our custom chunking function
    # This ensures the WebUI LightRAG instance also uses RFP-aware chunking
    
    # Store the original chunking function (if any)
    original_chunking_func = getattr(global_args, 'chunking_func', None)
    
    # Apply our custom chunking function to global_args
    global_args.chunking_func = rfp_chunking_func
    
    print("   🎯 Applied RFP-aware chunking to LightRAG WebUI")
    
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
        
        # Create LightRAG instance with same config as the server + custom chunking
        base_rag_instance = LightRAG(
            working_dir=global_args.working_dir,
            workspace=global_args.workspace,
            llm_model_func=ollama_model_complete,
            llm_model_name=global_args.llm_model,
            llm_model_max_async=global_args.max_async,
            summary_max_tokens=global_args.summary_max_tokens,
            summary_context_size=global_args.summary_context_size,
            chunk_token_size=int(global_args.chunk_size),
            chunk_overlap_token_size=int(global_args.chunk_overlap_size),
            # *** CUSTOM CHUNKING FUNCTION - THE PROPER EXTENSION POINT ***
            chunking_func=rfp_chunking_func,  # Use our RFP-aware chunking
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
        
        # *** ENHANCED RFP INTEGRATION ***
        # Wrap the base LightRAG instance with RFP-aware processing
        from src.core.lightrag_integration import RFPAwareLightRAG
        enhanced_rag_instance = RFPAwareLightRAG(base_rag_instance)
        
        print("   ✅ Enhanced RFP-aware LightRAG instance created")
        print("   ✅ Custom chunking function applied - RFP structure preserved")
        print("   ✅ Section-aware chunking with Shipley methodology integration")
        
        # *** CRITICAL: Replace the LightRAG instance in the app ***
        # LightRAG's create_app creates internal routes using its own instance
        # We need to replace that instance with our enhanced wrapper
        
        # Get the document router from the app and replace its RAG instance
        for route in app.routes:
            if hasattr(route, 'path') and route.path.startswith('/documents'):
                # Find the route dependencies and update them to use our enhanced instance
                if hasattr(route, 'endpoint') and hasattr(route.endpoint, '__closure__'):
                    # The LightRAG instance is in the closure of the route functions
                    # We need to monkey-patch this at the module level
                    pass
        
        # Better approach: Override the document processing functions
        import lightrag.api.routers.document_routes as doc_routes_module
        
        # Store original functions
        original_pipeline_enqueue_file = doc_routes_module.pipeline_enqueue_file
        original_pipeline_index_file = doc_routes_module.pipeline_index_file
        
        # Create enhanced wrappers
        async def enhanced_pipeline_enqueue_file(rag, file_path, track_id=None):
            """Enhanced pipeline enqueue with RFP detection"""
            print(f"   🔍 Enhanced pipeline_enqueue_file called with file: {file_path}")
            print(f"   🔍 RAG instance type: {type(rag)}")
            print(f"   🔍 Has detect_rfp_document: {hasattr(rag, 'detect_rfp_document')}")
            
            try:
                # Check if we have our enhanced instance
                if hasattr(rag, 'detect_rfp_document'):
                    print(f"   🎯 Using enhanced RAG instance for enqueue")
                    # Use our enhanced processing
                    return await original_pipeline_enqueue_file(rag, file_path, track_id)
                else:
                    print(f"   🔧 Wrapping standard RAG with enhanced processing")
                    # Wrap the standard instance temporarily
                    temp_enhanced = RFPAwareLightRAG(rag)
                    return await original_pipeline_enqueue_file(temp_enhanced, file_path, track_id)
            except Exception as e:
                print(f"   ⚠️ Enhanced pipeline enqueue failed, using standard: {e}")
                import traceback
                print(f"   📋 Traceback: {traceback.format_exc()}")
                return await original_pipeline_enqueue_file(rag, file_path, track_id)
        
        async def enhanced_pipeline_index_file(rag, file_path, track_id=None):
            """Enhanced pipeline index with RFP detection"""
            print(f"   🔍 Enhanced pipeline_index_file called with file: {file_path}")
            print(f"   🔍 RAG instance type: {type(rag)}")
            print(f"   🔍 Has detect_rfp_document: {hasattr(rag, 'detect_rfp_document')}")
            
            try:
                # Check if we have our enhanced instance
                if hasattr(rag, 'detect_rfp_document'):
                    print(f"   🎯 Using enhanced RAG instance for index")
                    # Use our enhanced processing
                    return await original_pipeline_index_file(rag, file_path, track_id)
                else:
                    print(f"   🔧 Wrapping standard RAG with enhanced processing")
                    # Wrap the standard instance temporarily
                    temp_enhanced = RFPAwareLightRAG(rag)
                    return await original_pipeline_index_file(temp_enhanced, file_path, track_id)
            except Exception as e:
                print(f"   ⚠️ Enhanced pipeline index failed, using standard: {e}")
                import traceback
                print(f"   📋 Traceback: {traceback.format_exc()}")
                return await original_pipeline_index_file(rag, file_path, track_id)
            except Exception as e:
                print(f"Enhanced pipeline index failed, using standard: {e}")
                return await original_pipeline_index_file(rag, file_path, track_id)
        
        # Replace the functions in the module
        doc_routes_module.pipeline_enqueue_file = enhanced_pipeline_enqueue_file
        doc_routes_module.pipeline_index_file = enhanced_pipeline_index_file
        
        print("   ✅ Document processing pipeline enhanced with RFP awareness")
        
        # Pass the enhanced instance to RFP routes
        set_rag_instance(enhanced_rag_instance)
        
        # Store reference to enhanced processor for WebUI integration
        app.state.rag_instance = enhanced_rag_instance
        app.state.enhanced_processing = True
        
        print("   ✅ LightRAG WebUI now uses enhanced RFP processing by default")
        
    except Exception as e:
        print(f"   ⚠️  Warning: Failed to create enhanced LightRAG instance: {e}")
        print("   ⚠️  Falling back to standard LightRAG processing")
        
        # Fallback: use base instance for RFP routes
        set_rag_instance(base_rag_instance)
        app.state.rag_instance = base_rag_instance
        app.state.enhanced_processing = False
    
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