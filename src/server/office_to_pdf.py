"""Convert Word documents to PDF before MinerU hybrid parsing.

MinerU 3.3+ parses ``.pptx`` and ``.xlsx`` natively on ``POST /tasks``; send
those straight through ``mineru-iteP``. Word (``.doc``/``.docx``) must not fall
back to LightRAG's native DOCX sidecar, so we pre-convert to PDF for the same
MinerU route and ``paragraph_semantic`` chunking as PDFs.

Uses LibreOffice headless (``soffice --headless --convert-to pdf``). Cached per
workspace under ``rag_storage/<workspace>/.office_pdf_cache/`` keyed by source
content hash so re-scans skip reconversion when the file is unchanged.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Word only — pptx/xlsx go direct to MinerU 3.3 office parsers on /tasks.
OFFICE_CONVERT_SUFFIXES = frozenset({".doc", ".docx"})

_WINDOWS_SOFFICE_CANDIDATES = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
)

_SOURCE_META_FILENAME = "source.meta.json"


@dataclass(frozen=True)
class OfficePdfConversion:
    """Result of preparing an Office source for MinerU."""

    enqueue_path: Path
    original_name: str
    converted: bool
    cache_dir: Path | None = None


def is_office_source(path: str | Path) -> bool:
    return Path(path).suffix.lower() in OFFICE_CONVERT_SUFFIXES


def resolve_libreoffice_executable(explicit_path: str | None = None) -> str:
    """Return a LibreOffice ``soffice`` executable path."""
    candidate = str(explicit_path or "").strip().strip('"')
    if candidate:
        resolved = Path(candidate)
        if resolved.is_file():
            return str(resolved)
        raise FileNotFoundError(f"LIBREOFFICE_PATH does not exist: {candidate}")

    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found

    if sys.platform == "win32":
        for path in _WINDOWS_SOFFICE_CANDIDATES:
            if Path(path).is_file():
                return path

    raise FileNotFoundError(
        "LibreOffice (soffice) not found on PATH. Install LibreOffice or set "
        "LIBREOFFICE_PATH to soffice.exe for Office→PDF pre-conversion."
    )


def office_pdf_cache_root(working_dir: str, workspace: str) -> Path:
    return Path(working_dir) / workspace / ".office_pdf_cache"


def workspace_inputs_dir(workspace: str) -> Path:
    return Path("inputs") / workspace


def stage_office_pdf_for_mineru(pdf_path: str | Path, *, workspace: str) -> Path:
    """Copy a cached Office→PDF artifact into ``inputs/<workspace>/``.

    LightRAG's MinerU parser resolves sources under ``inputs/<workspace>/`` by
    basename only; it does not read ``rag_storage/.office_pdf_cache/`` paths.
    """
    source = Path(pdf_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Converted PDF not found for MinerU staging: {source}")

    dest_dir = workspace_inputs_dir(workspace)
    dest_dir.mkdir(parents=True, exist_ok=True)
    destination = (dest_dir / source.name).resolve()
    if destination != source:
        shutil.copy2(source, destination)
        logger.info(
            "Office→PDF staged for MinerU: %s → %s",
            source.name,
            destination,
        )
    return destination


def _source_fingerprint(source: Path) -> tuple[int, str]:
    size, digest = _size_and_hash(source)
    return size, digest


def _size_and_hash(path: Path) -> tuple[int, str]:
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(chunk)
            size += len(chunk)
    return size, hasher.hexdigest()


def _read_source_meta(meta_path: Path) -> dict | None:
    if not meta_path.is_file():
        return None
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _cache_hit(cache_dir: Path, pdf_path: Path, source: Path, digest: str, size: int) -> bool:
    if not pdf_path.is_file():
        return False
    meta = _read_source_meta(cache_dir / _SOURCE_META_FILENAME)
    if meta is None:
        return False
    return (
        meta.get("sha256") == digest
        and int(meta.get("size_bytes") or -1) == size
        and meta.get("source_name") == source.name
    )


def convert_office_to_pdf(
    source: str | Path,
    *,
    cache_root: str | Path,
    libreoffice_path: str | None = None,
    timeout_seconds: float = 600.0,
    run_subprocess: Callable[..., subprocess.CompletedProcess] | None = None,
) -> OfficePdfConversion:
    """Convert ``source`` to a cached PDF suitable for MinerU hybrid parsing."""
    source_path = Path(source).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"Office source not found: {source_path}")

    original_name = source_path.name
    if not is_office_source(source_path):
        return OfficePdfConversion(
            enqueue_path=source_path,
            original_name=original_name,
            converted=False,
        )

    size, digest = _source_fingerprint(source_path)
    cache_dir = Path(cache_root) / digest[:16]
    pdf_path = cache_dir / f"{source_path.stem}.pdf"

    if _cache_hit(cache_dir, pdf_path, source_path, digest, size):
        logger.info(
            "Office→PDF cache hit for %s → %s",
            original_name,
            pdf_path.name,
        )
        return OfficePdfConversion(
            enqueue_path=pdf_path,
            original_name=original_name,
            converted=True,
            cache_dir=cache_dir,
        )

    cache_dir.mkdir(parents=True, exist_ok=True)
    soffice = resolve_libreoffice_executable(libreoffice_path)
    runner = run_subprocess or subprocess.run
    cmd = [
        soffice,
        "--headless",
        "--norestore",
        "--convert-to",
        "pdf",
        "--outdir",
        str(cache_dir),
        str(source_path),
    ]
    logger.info("Office→PDF converting %s via LibreOffice", original_name)
    try:
        completed = runner(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"LibreOffice timed out converting {original_name} after {timeout_seconds}s"
        ) from exc

    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        detail = stderr or stdout or f"exit code {completed.returncode}"
        raise RuntimeError(f"LibreOffice failed converting {original_name}: {detail}")

    if not pdf_path.is_file():
        produced = sorted(cache_dir.glob("*.pdf"))
        if len(produced) == 1:
            pdf_path = produced[0]
        else:
            raise RuntimeError(
                f"LibreOffice conversion of {original_name} did not produce "
                f"expected PDF at {pdf_path}"
            )

    meta = {
        "source_name": original_name,
        "source_path": str(source_path),
        "sha256": digest,
        "size_bytes": size,
        "pdf_name": pdf_path.name,
    }
    (cache_dir / _SOURCE_META_FILENAME).write_text(
        json.dumps(meta, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    logger.info(
        "Office→PDF converted %s → %s (%d bytes)",
        original_name,
        pdf_path.name,
        pdf_path.stat().st_size,
    )
    return OfficePdfConversion(
        enqueue_path=pdf_path,
        original_name=original_name,
        converted=True,
        cache_dir=cache_dir,
    )


__all__ = [
    "OFFICE_CONVERT_SUFFIXES",
    "OfficePdfConversion",
    "convert_office_to_pdf",
    "is_office_source",
    "office_pdf_cache_root",
    "resolve_libreoffice_executable",
    "stage_office_pdf_for_mineru",
    "workspace_inputs_dir",
]