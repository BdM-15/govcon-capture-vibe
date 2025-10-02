"""
Logging Configuration for GovCon Capture Vibe

Sets up structured logging with both file and console output.
Prevents terminal overflow by using rotating log files.

Features:
- Dedicated lightrag.log for RFP processing details
- Filtered console output (no HTTP spam)
- Separate error logging
- Performance monitoring
- No duplicate log entries
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from datetime import datetime


class HTTPFilter(logging.Filter):
    """Filter out FastAPI HTTP request logs from console output"""
    
    def filter(self, record):
        # Filter out uvicorn access logs (GET/POST requests)
        if record.name == "uvicorn.access":
            return False
        
        # Filter out common HTTP patterns in messages
        http_patterns = [
            "POST /documents/paginated",
            "GET /documents/paginated",
            "GET /health",
            "POST /health",
            "GET /api/",
            "POST /api/",
            "HTTP/1.1",
        ]
        
        message = record.getMessage()
        for pattern in http_patterns:
            if pattern in message:
                return False
        
        return True


class LightRAGFilter(logging.Filter):
    """Filter to only allow LightRAG processing logs"""
    
    def filter(self, record):
        # Only allow logs from lightrag, nano-vectordb, and related processing
        allowed_loggers = [
            "lightrag",
            "nano-vectordb",
            "src.core.lightrag_chunking",
            "src.core.lightrag_integration",
        ]
        
        for logger_name in allowed_loggers:
            if record.name.startswith(logger_name):
                return True
        
        return False


class ServerFilter(logging.Filter):
    """Filter for server-related logs (non-LightRAG processing)"""
    
    def filter(self, record):
        # Exclude LightRAG processing details from server log
        excluded_loggers = [
            "lightrag",
            "nano-vectordb",
        ]
        
        for logger_name in excluded_loggers:
            if record.name.startswith(logger_name):
                return False
        
        return True

def setup_logging(
    log_level: str = "INFO",
    log_dir: str = "logs",
    max_file_size: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    console_output: bool = True
):
    """
    Set up comprehensive logging configuration with clean separation
    
    Log Files:
        - lightrag.log: RFP processing details (chunk extraction, entities, relationships)
        - govcon_server.log: Server operations (startup, initialization, API calls)
        - errors.log: All errors from any source
        - performance.log: Optional timing metrics
    
    Console Output:
        - Filtered to show only important messages (no HTTP spam)
        - Shows RFP processing progress
        - Shows errors and warnings
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_dir: Directory for log files
        max_file_size: Maximum size of each log file before rotation
        backup_count: Number of backup log files to keep
        console_output: Whether to also output to console
    """
    
    # Create logs directory
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Clear any existing handlers to prevent duplication
    root_logger.handlers.clear()
    
    # Configure LightRAG logger with its own handlers
    lightrag_logger = logging.getLogger('lightrag')
    lightrag_logger.handlers.clear()
    lightrag_logger.setLevel(logging.INFO)
    lightrag_logger.propagate = False  # Don't propagate to root to avoid duplicates
    
    # Configure nano-vectordb logger
    vectordb_logger = logging.getLogger('nano-vectordb')
    vectordb_logger.handlers.clear()
    vectordb_logger.setLevel(logging.INFO)
    vectordb_logger.propagate = False
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)-20s | %(funcName)-15s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    console_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # ========================================================================
    # 1. LIGHTRAG.LOG - RFP Processing Details (chunk extraction, entities, relationships)
    # ========================================================================
    lightrag_log_file = log_path / "lightrag.log"
    lightrag_file_handler = logging.handlers.RotatingFileHandler(
        lightrag_log_file,
        maxBytes=max_file_size,
        backupCount=backup_count,
        encoding='utf-8'
    )
    lightrag_file_handler.setLevel(logging.INFO)
    lightrag_file_handler.setFormatter(detailed_formatter)
    lightrag_file_handler.addFilter(LightRAGFilter())
    
    # Add to both lightrag and nano-vectordb loggers
    lightrag_logger.addHandler(lightrag_file_handler)
    vectordb_logger.addHandler(lightrag_file_handler)
    
    # ========================================================================
    # 2. GOVCON_SERVER.LOG - Server operations (no LightRAG processing noise)
    # ========================================================================
    server_log_file = log_path / "govcon_server.log"
    server_file_handler = logging.handlers.RotatingFileHandler(
        server_log_file,
        maxBytes=max_file_size,
        backupCount=backup_count,
        encoding='utf-8'
    )
    server_file_handler.setLevel(logging.INFO)
    server_file_handler.setFormatter(detailed_formatter)
    server_file_handler.addFilter(ServerFilter())
    root_logger.addHandler(server_file_handler)
    
    # ========================================================================
    # 3. ERRORS.LOG - All errors from any source
    # ========================================================================
    error_log_file = log_path / "errors.log"
    error_handler = logging.handlers.RotatingFileHandler(
        error_log_file,
        maxBytes=max_file_size,
        backupCount=backup_count,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)
    
    # Add to root logger and LightRAG logger to catch all errors
    root_logger.addHandler(error_handler)
    lightrag_logger.addHandler(error_handler)
    vectordb_logger.addHandler(error_handler)
    
    # ========================================================================
    # 4. PERFORMANCE.LOG - Optional timing metrics
    # ========================================================================
    perf_log_file = log_path / "performance.log"
    perf_handler = logging.handlers.RotatingFileHandler(
        perf_log_file,
        maxBytes=max_file_size,
        backupCount=backup_count,
        encoding='utf-8'
    )
    perf_handler.setLevel(logging.INFO)
    perf_handler.setFormatter(detailed_formatter)
    
    # Add performance handler only to performance monitor
    perf_logger = logging.getLogger('performance_monitor')
    perf_logger.handlers.clear()
    perf_logger.addHandler(perf_handler)
    perf_logger.setLevel(logging.INFO)
    perf_logger.propagate = False
    
    # ========================================================================
    # 5. CONSOLE OUTPUT - Filtered (no HTTP spam, only important messages)
    # ========================================================================
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(console_formatter)
        console_handler.addFilter(HTTPFilter())  # Filter out HTTP request spam
        
        # Add to root logger for server messages
        root_logger.addHandler(console_handler)
        
        # Add to LightRAG logger for processing updates
        lightrag_console = logging.StreamHandler(sys.stdout)
        lightrag_console.setLevel(logging.INFO)
        lightrag_console.setFormatter(console_formatter)
        lightrag_console.addFilter(HTTPFilter())
        lightrag_logger.addHandler(lightrag_console)
    
    # Log startup message
    startup_msg = f"""
🚀 GovCon Capture Vibe Logging Initialized
   📁 Log Directory: {log_path.absolute()}
   � LightRAG Processing: {lightrag_log_file.name} (chunk extraction, entities, relationships)
   📊 Server Operations: {server_log_file.name} (startup, API calls, general operations)
   🔴 Error Log: {error_log_file.name} (all errors from any source)
   ⚡ Performance Log: {perf_log_file.name} (timing metrics)
   📏 Max File Size: {max_file_size / 1024 / 1024:.1f}MB per file
   🗂️ Backup Count: {backup_count} files per log
   📺 Console Output: {console_output} (filtered - no HTTP spam)
   🎯 Log Level: {log_level.upper()}
    """
    
    logger = logging.getLogger(__name__)
    logger.info(startup_msg.strip())
    
    return {
        "log_dir": str(log_path.absolute()),
        "lightrag_log": str(lightrag_log_file),
        "server_log": str(server_log_file),
        "error_log": str(error_log_file),
        "performance_log": str(perf_log_file)
    }

def get_log_files_info(log_dir: str = "logs") -> dict:
    """Get information about current log files"""
    log_path = Path(log_dir)
    
    if not log_path.exists():
        return {"error": "Log directory does not exist"}
    
    log_files = []
    for log_file in log_path.glob("*.log*"):
        try:
            stat = log_file.stat()
            log_files.append({
                "name": log_file.name,
                "size_mb": stat.st_size / 1024 / 1024,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "path": str(log_file.absolute())
            })
        except Exception as e:
            log_files.append({
                "name": log_file.name,
                "error": str(e)
            })
    
    return {
        "log_directory": str(log_path.absolute()),
        "total_files": len(log_files),
        "files": sorted(log_files, key=lambda x: x.get("modified", ""))
    }

# Configure logging when module is imported
if __name__ != "__main__":
    # Only set up basic logging if not explicitly configured elsewhere
    # This prevents double initialization
    pass