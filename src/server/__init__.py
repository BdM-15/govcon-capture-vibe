"""
Server module for Theseus + native LightRAG integration

This module provides:
- Configuration (config.py): ontology-backed entity catalog, API credentials, chunking settings
- Initialization (native_lightrag_runtime.py): direct LightRAG runtime with GovCon prompts
- Routes (routes.py): FastAPI endpoints + semantic post-processing

Usage:
    from src.server.config import configure_lightrag_args
    from src.server.native_lightrag_runtime import initialize_native_lightrag
    from src.server.routes import create_insert_endpoint, create_documents_upload_endpoint
"""

__all__ = [
    "configure_lightrag_args",
    "configure_native_parser_args",
    "initialize_native_lightrag",
    "create_insert_endpoint",
    "create_documents_upload_endpoint",
]
