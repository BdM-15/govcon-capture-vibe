"""
Logging Configuration for GovCon Capture Vibe

Sets up structured logging with both file and console output.
Prevents terminal overflow by using rotating log files.

Features:
- Dedicated processing.log for RFP processing (RAG-Anything, LightRAG, semantic inference)
- Filtered console output (no HTTP health check spam)
- Separate error logging
- Automatic log rotation (10MB files, 5 backups per log)
- No duplicate log entries

Log Files Created:
    logs/processing.log - RFP extraction, entity/relationship counts, semantic inference progress
    logs/server.log - Server startup, API calls, configuration
    logs/errors.log - All errors from any component
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import List, Tuple, Optional

from src.utils.log_filters import ConsoleFilter, ProcessingFilter, ServerFilter
from src.utils.log_helpers import get_log_summary, log_graceful_failure


if sys.platform == 'win32':
    import ctypes
    import ctypes.wintypes
    import msvcrt

    class ShareDeleteRotatingFileHandler(logging.handlers.RotatingFileHandler):
        """
        RotatingFileHandler that opens files with FILE_SHARE_DELETE on Windows.

        Python's default RotatingFileHandler uses CreateFileW without
        FILE_SHARE_DELETE, which prevents other processes (e.g. workspace_cleanup.py)
        from renaming or deleting the log file while the server is running.

        With FILE_SHARE_DELETE set, any other process can rename the file out from
        under the server. The server keeps its open handle (writing to the now-orphaned
        path in temp) until it closes; the directory entry is removed immediately so
        rmdir succeeds.
        """

        _GENERIC_WRITE     = 0x40000000
        _FILE_SHARE_READ   = 0x00000001
        _FILE_SHARE_WRITE  = 0x00000002
        _FILE_SHARE_DELETE = 0x00000004
        _OPEN_ALWAYS       = 4
        _FILE_ATTRIBUTE_NORMAL = 0x80
        _INVALID_HANDLE    = ctypes.wintypes.HANDLE(-1).value

        def _open(self):
            k32 = ctypes.windll.kernel32
            k32.CreateFileW.restype = ctypes.wintypes.HANDLE
            k32.CreateFileW.argtypes = [
                ctypes.wintypes.LPCWSTR,
                ctypes.wintypes.DWORD,
                ctypes.wintypes.DWORD,
                ctypes.wintypes.LPVOID,
                ctypes.wintypes.DWORD,
                ctypes.wintypes.DWORD,
                ctypes.wintypes.HANDLE,
            ]
            handle = k32.CreateFileW(
                self.baseFilename,
                self._GENERIC_WRITE,
                self._FILE_SHARE_READ | self._FILE_SHARE_WRITE | self._FILE_SHARE_DELETE,
                None,
                self._OPEN_ALWAYS,
                self._FILE_ATTRIBUTE_NORMAL,
                None,
            )
            if handle == self._INVALID_HANDLE:
                raise OSError(f"CreateFileW failed (error {k32.GetLastError()}) for {self.baseFilename}")
            k32.SetFilePointer(handle, 0, None, 2)  # FILE_END — append mode
            fd = msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_APPEND)
            encoding = getattr(self, 'encoding', None) or 'utf-8'
            return os.fdopen(fd, self.mode, encoding=encoding)

else:
    ShareDeleteRotatingFileHandler = logging.handlers.RotatingFileHandler


# ═══════════════════════════════════════════════════════════════════════════════
# ANSI COLOR CODES (Centralized - DRY)
# ═══════════════════════════════════════════════════════════════════════════════
# Use these module-level constants instead of redefining in each file

class Colors:
    """ANSI color codes for terminal output."""
    CYAN = '\033[96m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    MAGENTA = '\033[95m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    ITALIC = '\033[3m'
    WHITE = '\033[97m'
    RESET = '\033[0m'


def log_banner(
    title: str,
    items: Optional[List[Tuple[str, str]]] = None,
    width: int = 80,
    logger: Optional[logging.Logger] = None,
    force_print: bool = False,
) -> None:
    """
    Log a standardized banner with title and optional items.

    Args:
        title: Banner title (can include emoji and ANSI codes)
        items: Optional list of (label, value) tuples to display
        width: Banner width in characters (default: 80)
        logger: Logger instance (defaults to root logger)
        force_print: When True, write directly to stdout via print() instead of
                     going through the logging system. Use this for startup banners
                     that must always be visible regardless of log handler state
                     (e.g. after third-party libs reset the root logger).
    """
    c = Colors
    separator = f"{c.CYAN}{'═' * width}{c.RESET}"

    def _emit(msg: str) -> None:
        if force_print:
            print(msg)
        else:
            _log = logger if logger is not None else logging.getLogger()
            _log.info(msg)

    _emit("")
    _emit(separator)
    _emit(f"{c.BOLD}{c.MAGENTA}{title}{c.RESET}")
    _emit(separator)

    if items:
        for label, value in items:
            if not label:
                _emit(f"{c.CYAN}{'─' * (width // 2)}{c.RESET}")
            else:
                _emit(f"{c.GREEN}{label}:{c.RESET} {value}")

    _emit(separator)
    _emit("")


def _remove_workspace_file_handlers(target_logger: logging.Logger) -> None:
    """Remove direct per-workspace file handlers from external loggers.

    ``setup_logging`` may run repeatedly as workspaces are recreated. Root
    handlers are cleared each time, but external loggers such as ``lightrag``
    can keep direct handlers when they have ``propagate=False``. Remove the
    previous workspace file handlers before attaching the new ones so errors do
    not leak to stale workspace logs.
    """
    for handler in list(target_logger.handlers):
        base_filename = str(getattr(handler, "baseFilename", ""))
        if getattr(handler, "_theseus_workspace_file_handler", False) or base_filename.endswith(("_processing.log", "_errors.log")):
            target_logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass


def setup_logging(
    log_level: str = "INFO",
    log_dir: str = "logs",
    workspace_dir: Optional[str] = None,
    max_file_size: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    console_output: bool = True
):
    """
    Set up logging with per-workspace processing logs and a central server log.

    Log Files:
        - {workspace_dir}/{workspace}_processing.log  — RFP extraction, entity/relation counts,
          semantic inference progress (one log per workspace, never shared)
        - {workspace_dir}/{workspace}_errors.log      — all errors for this workspace
        - {log_dir}/server.log                        — server startup and API calls (central)

    The workspace name is derived from the last path component of workspace_dir so
    the log filename is self-describing even when viewed outside its parent folder.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_dir: Central log directory for server.log (default: "logs")
        workspace_dir: Workspace storage path for processing.log + errors.log.
                       Defaults to log_dir when not set (backward compat).
        max_file_size: Max bytes per log file before rotation (default: 10 MB)
        backup_count: Backup files to keep per log (default: 5)
        console_output: Whether to output to console (default: True)

    Returns:
        dict: Paths to all created log files
    """
    
    # Central log directory (server.log)
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Per-workspace log directory (processing.log + errors.log)
    workspace_log_path = Path(workspace_dir) if workspace_dir else log_path
    workspace_log_path.mkdir(parents=True, exist_ok=True)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    root_logger.handlers.clear()
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    console_formatter = logging.Formatter(
        '%(levelname)-8s | %(message)s'
    )
    
    # ========================================================================
    # 1. PROCESSING.LOG - RFP processing details (per workspace)
    # ========================================================================
    # Include workspace name in the filename so logs are self-describing when
    # viewed outside their parent folder (e.g., in an editor, log viewer, or grep).
    workspace_name = workspace_log_path.name  # e.g. "afcapv_bos_i_t7"
    processing_log_file = workspace_log_path / f"{workspace_name}_processing.log"
    processing_handler = ShareDeleteRotatingFileHandler(
        processing_log_file,
        maxBytes=max_file_size,
        backupCount=backup_count,
        encoding='utf-8'
    )
    processing_handler.setLevel(logging.INFO)
    processing_handler.setFormatter(detailed_formatter)
    processing_handler.addFilter(ProcessingFilter())
    processing_handler._theseus_workspace_file_handler = True
    root_logger.addHandler(processing_handler)
    
    # ========================================================================
    # 2. SERVER.LOG - Server operations
    # ========================================================================
    server_log_file = log_path / "server.log"
    server_handler = logging.handlers.RotatingFileHandler(
        server_log_file,
        maxBytes=max_file_size,
        backupCount=backup_count,
        encoding='utf-8'
    )
    server_handler.setLevel(logging.INFO)
    server_handler.setFormatter(detailed_formatter)
    server_handler.addFilter(ServerFilter())
    root_logger.addHandler(server_handler)
    
    # ========================================================================
    # 3. ERRORS.LOG - All errors (per workspace)
    # ========================================================================
    error_log_file = workspace_log_path / f"{workspace_name}_errors.log"
    error_handler = ShareDeleteRotatingFileHandler(
        error_log_file,
        maxBytes=max_file_size,
        backupCount=backup_count,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)
    error_handler._theseus_workspace_file_handler = True
    root_logger.addHandler(error_handler)

    # CRITICAL: LightRAG's logger has propagate=False, so root handlers alone do
    # not receive its records. Attach both processing and error handlers directly
    # so workspace errors land in <workspace>_errors.log as well as processing.log.
    for external_logger_name in ("lightrag", "raganything"):
        external_logger = logging.getLogger(external_logger_name)
        _remove_workspace_file_handlers(external_logger)
        external_logger.addHandler(processing_handler)
        external_logger.addHandler(error_handler)
    
    # ========================================================================
    # 4. CONSOLE OUTPUT - Filtered (no health check spam)
    # ========================================================================
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(console_formatter)
        console_handler.addFilter(ConsoleFilter())
        root_logger.addHandler(console_handler)
    
    # Write session-start marker directly to processing log for run auditability
    from datetime import datetime as _dt
    _session_marker = (
        f"\n{'─' * 38} SESSION START {_dt.now().strftime('%Y-%m-%d %H:%M:%S')} {'─' * 38}\n"
        f"Workspace: {workspace_log_path.name}  |  Log: {processing_log_file}\n"
        f"{'─' * 94}\n"
    )
    try:
        processing_handler.stream.write(_session_marker)
        processing_handler.flush()
    except Exception:
        pass  # Non-critical

    return {
        "log_dir": str(log_path.absolute()),
        "workspace_log_dir": str(workspace_log_path.absolute()),
        "processing_log": str(processing_log_file),
        "server_log": str(server_log_file),
        "error_log": str(error_log_file),
    }
