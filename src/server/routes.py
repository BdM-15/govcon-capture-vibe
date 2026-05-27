"""Ingestion route registration for the Theseus server.

Owns the custom document-ingestion seam:
- callback-aware native LightRAG document processing adapter
- endpoint registration for /insert, /documents/upload, /scan-rfp
- replacement of LightRAG's stock POST upload routes
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

from src.server.native_ingestion import process_document_with_native_ingestion as run_native_ingestion
from src.server.processing_callback import get_processing_callback
from src.server.scan_routes import create_scan_endpoint as register_scan_endpoint
from src.server.upload_routes import (
    create_documents_upload_endpoint as register_documents_upload_endpoint,
    create_insert_endpoint as register_insert_endpoint,
)

_OVERRIDDEN_POST_PATHS = frozenset({"/insert", "/documents/upload"})
_callback = get_processing_callback()


async def process_document_with_native_ingestion(
    file_path: str,
    file_name: str,
    rag_instance,
    llm_func,
) -> dict:
    return await run_native_ingestion(
        file_path,
        file_name,
        rag_instance,
        llm_func,
        callback=_callback,
    )

def _preserve_non_overridden_post_routes(routes: Iterable[Any]) -> list[Any]:
    kept_routes: list[Any] = []
    for route in routes:
        if (
            hasattr(route, "path")
            and hasattr(route, "methods")
            and "POST" in route.methods
            and route.path in _OVERRIDDEN_POST_PATHS
        ):
            continue
        kept_routes.append(route)
    return kept_routes


def create_insert_endpoint(app, rag_instance) -> None:
    register_insert_endpoint(
        app,
        rag_instance,
        process_document_func=process_document_with_native_ingestion,
        callback=_callback,
    )


def create_documents_upload_endpoint(app, rag_instance) -> None:
    register_documents_upload_endpoint(
        app,
        rag_instance,
        process_document_func=process_document_with_native_ingestion,
        callback=_callback,
    )


def create_scan_endpoint(app, rag_instance) -> None:
    register_scan_endpoint(
        app,
        rag_instance,
        process_document_func=process_document_with_native_ingestion,
        callback=_callback,
    )


def register_custom_ingestion_routes(
    app: Any,
    rag_instance: Any,
    *,
    logger: Any,
    create_insert: Callable[[Any, Any], None] = create_insert_endpoint,
    create_upload: Callable[[Any, Any], None] = create_documents_upload_endpoint,
    create_scan: Callable[[Any, Any], None] = create_scan_endpoint,
) -> None:
    """Replace LightRAG upload routes with Theseus native ingestion handlers."""
    app.router.routes = _preserve_non_overridden_post_routes(app.router.routes)

    create_insert(app, rag_instance)
    create_upload(app, rag_instance)
    create_scan(app, rag_instance)
    logger.info("✅ Custom endpoints registered: /insert, /documents/upload, /scan-rfp")
    logger.info(
        "✅ Use LightRAG's native /query/data endpoint for structured data retrieval (agent workflows)"
    )


