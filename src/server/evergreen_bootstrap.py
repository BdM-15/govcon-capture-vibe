"""Evergreen bootstrap — co-process platform-wide docs on first workspace upload.

When the first document lands in a new workspace, this module seeds the workspace
KG with all `.md` files from `rag_storage/_platform/evergreen/` so every pursuit
starts with accumulated organisational context.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def list_evergreen_files(evergreen_dir: Path) -> list[Path]:
    """Return all `.md` files under *evergreen_dir*; empty list if dir absent."""
    if not evergreen_dir.exists():
        return []
    return sorted(p for p in evergreen_dir.iterdir() if p.is_file() and p.suffix == ".md")


async def is_new_workspace(rag_instance) -> bool:
    """Return True when doc_status holds no documents (workspace has never been used)."""
    try:
        doc_status = rag_instance.lightrag.doc_status
        result = await doc_status.get_docs_paginated(limit=1)
        # result is (([(id, data), ...], total_count), ...) or similar tuple
        _docs_with_ids, total_count = result[0]
        return total_count == 0
    except Exception:
        # If doc_status API is unavailable, treat as non-empty to be safe.
        return False


async def seed_evergreen_docs(
    rag_instance,
    evergreen_dir: Path,
    process_document_func,
    callback,
    *,
    workspace: str,
) -> int:
    """Process every `.md` in *evergreen_dir* through the ingestion pipeline.

    Returns the number of files actually processed (0 if dir absent or empty).
    Errors on individual files are logged and skipped — they do not abort seeding.
    """
    files = list_evergreen_files(evergreen_dir)
    if not files:
        return 0

    processed = 0
    for file_path in files:
        await callback.register_request_start(file_path.name)
        try:
            logger.info("🌿 Seeding evergreen doc into '%s': %s", workspace, file_path.name)
            await process_document_func(
                str(file_path),
                file_path.name,
                rag_instance,
                rag_instance.llm_model_func,
            )
            processed += 1
        except Exception as exc:
            logger.error("❌ Evergreen seed failed for %s: %s", file_path.name, exc)
        finally:
            await callback.register_request_end(file_path.name)

    logger.info("🌿 Seeded workspace '%s' with %d evergreen doc(s)", workspace, processed)
    return processed
