"""
Logging Configuration for GovCon Capture Vibe

Sets up structured logging with both file and console output.
Prevents terminal overflow by using rotating log files.
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from datetime import datetime

def setup_logging(
    log_level: str = "INFO",
    log_dir: str = "logs",
    max_file_size: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    console_output: bool = True
):
    """
    Set up comprehensive logging configuration
    
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
    
    # Clear any existing handlers
    root_logger.handlers.clear()
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)-20s | %(funcName)-15s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # 1. Main application log (rotating file)
    main_log_file = log_path / "govcon_server.log"
    file_handler = logging.handlers.RotatingFileHandler(
        main_log_file,
        maxBytes=max_file_size,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(file_handler)
    
    # 2. Performance monitoring log (separate file)
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
    perf_logger.addHandler(perf_handler)
    perf_logger.setLevel(logging.INFO)
    
    # 3. Error log (errors only)
    error_log_file = log_path / "errors.log"
    error_handler = logging.handlers.RotatingFileHandler(
        error_log_file,
        maxBytes=max_file_size,
        backupCount=backup_count,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(error_handler)
    
    # 4. Console output (optional, simplified)
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level.upper()))
        console_handler.setFormatter(simple_formatter)
        root_logger.addHandler(console_handler)
    
    # 5. LightRAG-specific logging (to separate file)
    lightrag_log_file = log_path / "lightrag.log"
    lightrag_handler = logging.handlers.RotatingFileHandler(
        lightrag_log_file,
        maxBytes=max_file_size,
        backupCount=backup_count,
        encoding='utf-8'
    )
    lightrag_handler.setLevel(logging.INFO)
    lightrag_handler.setFormatter(detailed_formatter)
    
    # Apply to LightRAG loggers
    lightrag_logger = logging.getLogger('lightrag')
    lightrag_logger.addHandler(lightrag_handler)
    lightrag_logger.setLevel(logging.INFO)
    
    # Log startup message
    startup_msg = f"""
🚀 GovCon Capture Vibe Logging Initialized
   📁 Log Directory: {log_path.absolute()}
   📊 Main Log: {main_log_file.name}
   ⚡ Performance Log: {perf_log_file.name}
   🔴 Error Log: {error_log_file.name}
   🔧 LightRAG Log: {lightrag_log_file.name}
   📏 Max File Size: {max_file_size / 1024 / 1024:.1f}MB
   🗂️ Backup Count: {backup_count}
   📺 Console Output: {console_output}
   🎯 Log Level: {log_level.upper()}
    """
    
    logger = logging.getLogger(__name__)
    logger.info(startup_msg.strip())
    
    return {
        "log_dir": str(log_path.absolute()),
        "main_log": str(main_log_file),
        "performance_log": str(perf_log_file),
        "error_log": str(error_log_file),
        "lightrag_log": str(lightrag_log_file)
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
    # Get log level from environment or default to INFO
    log_level = os.getenv("LOG_LEVEL", "INFO")
    console_output = os.getenv("LOG_CONSOLE", "true").lower() == "true"
    
    setup_logging(
        log_level=log_level,
        console_output=console_output
    )