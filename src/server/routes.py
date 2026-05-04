"""
FastAPI Routes Module

Custom endpoints for RAG-Anything + LightRAG server:
- /insert: Document upload with automatic semantic post-processing
- /documents/upload: WebUI document upload (also triggers post-processing)

Architecture:
1. Document Upload → process_document_with_semantic_inference()
2. RAG-Anything Processing → MinerU multimodal parsing
3. Native LightRAG Extraction → Entity/relationship extraction (18 types)
4. GovConProcessingCallback → Detects batch completion via RAG-Anything callbacks
5. Auto-Enhancement → Semantic post-processing runs ONCE after last document
"""

from src.server.document_processing import process_document_with_semantic_inference as run_document_processing
from src.server.processing_callback import get_processing_callback
from src.server.scan_routes import create_scan_endpoint as register_scan_endpoint
from src.server.upload_routes import (
    create_documents_upload_endpoint as register_documents_upload_endpoint,
    create_insert_endpoint as register_insert_endpoint,
)
_callback = get_processing_callback()


async def process_document_with_semantic_inference(
    file_path: str,
    file_name: str,
    rag_instance,
    llm_func
) -> dict:
    return await run_document_processing(
        file_path,
        file_name,
        rag_instance,
        llm_func,
        callback=_callback,
    )


def create_insert_endpoint(app, rag_instance):
    register_insert_endpoint(
        app,
        rag_instance,
        process_document_func=process_document_with_semantic_inference,
        callback=_callback,
    )


def create_documents_upload_endpoint(app, rag_instance):
    register_documents_upload_endpoint(
        app,
        rag_instance,
        process_document_func=process_document_with_semantic_inference,
        callback=_callback,
    )


def create_scan_endpoint(app, rag_instance):
    register_scan_endpoint(
        app,
        rag_instance,
        process_document_func=process_document_with_semantic_inference,
        callback=_callback,
    )


