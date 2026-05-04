"""Upload staging and scan-folder helpers for document ingestion routes."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from src.core import get_settings

logger = logging.getLogger(__name__)


DEFAULT_SCAN_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".gif", ".webp",
    ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".txt", ".md",
)


def sanitize_upload_filename(name: str) -> str:
    """Strip path separators and other unsafe chars from a filename."""
    return name.replace("/", "_").replace("\\", "_").lstrip(".")


def hash_file(path: Path, chunk_size: int = 65536) -> str:
    """Hash a file without loading the whole payload into memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def save_upload_to_workspace(
    file: UploadFile,
    workspace: Optional[str] = None,
) -> Path:
    """Persist an uploaded file to inputs/<workspace>/<filename>."""
    settings = get_settings()
    ws = workspace or settings.workspace
    folder = Path("./inputs") / ws
    await asyncio.to_thread(folder.mkdir, parents=True, exist_ok=True)

    safe_name = sanitize_upload_filename(file.filename)
    target = folder / safe_name

    tmp_fd, tmp_path = tempfile.mkstemp(prefix="upload_", dir=str(folder))
    os.close(tmp_fd)
    tmp = Path(tmp_path)
    try:
        with open(tmp, "wb") as handle:
            await asyncio.to_thread(shutil.copyfileobj, file.file, handle)

        if target.exists():
            existing_hash = await asyncio.to_thread(hash_file, target)
            new_hash = await asyncio.to_thread(hash_file, tmp)
            if existing_hash == new_hash:
                logger.info(
                    "📎 Upload %s already present in inputs/%s/ (identical content) — reusing existing file.",
                    safe_name,
                    ws,
                )
                tmp.unlink(missing_ok=True)
                return target

            stem = target.stem
            suffix = target.suffix
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target = folder / f"{stem}_{timestamp}{suffix}"
            logger.info(
                "📎 Upload %s collides with existing file in inputs/%s/ with different content — saving as %s.",
                safe_name,
                ws,
                target.name,
            )

        await asyncio.to_thread(tmp.replace, target)
        return target
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def resolve_scan_folder(workspace: Optional[str]) -> Path:
    """Resolve the inputs folder for a workspace."""
    settings = get_settings()
    ws = workspace or settings.workspace
    folder = Path("./inputs") / ws
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def list_scannable_files(
    folder: Path,
    extensions: tuple[str, ...] = DEFAULT_SCAN_EXTENSIONS,
) -> list[Path]:
    """List supported files directly in a folder (non-recursive)."""
    files: list[Path] = []
    for ext in extensions:
        files.extend(folder.glob(f"*{ext}"))
        files.extend(folder.glob(f"*{ext.upper()}"))

    seen = set()
    unique: list[Path] = []
    for path in files:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return sorted(unique)