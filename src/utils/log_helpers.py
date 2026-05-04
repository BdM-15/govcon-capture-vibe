"""Small logging helper functions."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def log_graceful_failure(logger, operation: str, error: Exception, context: str = "") -> None:
    """Log expected non-fatal failure with truncated message."""
    error_msg = str(error)[:100]
    if context:
        logger.warning(
            f"⚠️ {operation} failed ({context}): {error_msg} - continuing with degraded result"
        )
    else:
        logger.warning(
            f"⚠️ {operation} failed: {error_msg} - continuing with degraded result"
        )


def get_log_summary(log_dir: str = "logs") -> dict:
    """Get summary of current log files with sizes and timestamps."""
    log_path = Path(log_dir)

    if not log_path.exists():
        return {"error": "Log directory does not exist"}

    log_files = []
    for log_file in sorted(log_path.glob("*.log*")):
        try:
            stat = log_file.stat()
            log_files.append(
                {
                    "name": log_file.name,
                    "size_mb": round(stat.st_size / 1024 / 1024, 2),
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "path": str(log_file.absolute()),
                }
            )
        except Exception as exc:  # noqa: BLE001
            log_files.append({"name": log_file.name, "error": str(exc)})

    return {
        "log_directory": str(log_path.absolute()),
        "total_files": len(log_files),
        "files": log_files,
    }