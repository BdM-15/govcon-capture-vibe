"""Route override helpers for the Theseus server."""

from __future__ import annotations

from typing import Any, Callable

from src.server.routes import (
    create_documents_upload_endpoint,
    create_insert_endpoint,
    create_scan_endpoint,
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
    """Replace LightRAG upload endpoints with Theseus multimodal handlers."""
    new_routes = []
    for route in app.router.routes:
        if hasattr(route, "path") and hasattr(route, "methods") and "POST" in route.methods:
            if route.path in ["/insert", "/documents/upload"]:
                continue
        new_routes.append(route)
    app.router.routes = new_routes

    create_insert(app, rag_instance)
    create_upload(app, rag_instance)
    create_scan(app, rag_instance)
    logger.info("✅ Custom endpoints registered: /insert, /documents/upload, /scan-rfp")
    logger.info(
        "✅ Use LightRAG's native /query/data endpoint for structured data retrieval (agent workflows)"
    )