"""
GovCon Capture Vibe - RFP Analysis Tool

Startup script for the extended LightRAG server with government contracting features.
Replaces the previous Streamlit interface with a professional React-based WebUI
that includes custom RFP analysis capabilities grounded in Shipley methodology.

Features:
- Document processing with LightRAG knowledge graphs
- Requirements extraction and compliance matrices
- Gap analysis using Shipley Capture Guide methods
- Professional React WebUI with custom RFP components
- Neo4j enterprise graph storage (auto-started via Docker)

Usage:
    python app.py
    
This will:
1. Start Neo4j container (if not already running)
2. Wait for Neo4j health check
3. Start GovCon RAG server
    
Then visit: http://localhost:9621
"""

import asyncio
import sys
import subprocess
import time
import os

# Fix Windows console encoding for Unicode characters
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
from pathlib import Path

# Import LightRAG and the temporary RAG-Anything compatibility dependency from pip
# BEFORE adding src to path. This prevents any old fork from shadowing the pip package.
from raganything import RAGAnything
from lightrag.api.lightrag_server import create_app as _verify_lightrag_import

# NOW add src to Python path for our custom server module
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Import the LightRAG-first Capture Workbench server.
from raganything_server import main


def check_docker_available():
    """Check if Docker is available and running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def is_neo4j_enabled():
    """Check if Neo4j is enabled in .env configuration."""
    graph_storage = os.getenv("GRAPH_STORAGE", "NetworkXStorage")
    return graph_storage == "Neo4JStorage"


def is_neo4j_running():
    """Check if Neo4j container is already running."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=govcon-neo4j", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return "govcon-neo4j" in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def start_neo4j():
    """Start Neo4j container using docker-compose."""
    print("🚀 Starting Neo4j container...\n")
    
    compose_file = Path(__file__).parent / "docker-compose.neo4j.yml"
    if not compose_file.exists():
        print(f"❌ Docker Compose file not found: {compose_file}")
        return False
    
    try:
        # Start Neo4j in detached mode
        result = subprocess.run(
            ["docker-compose", "-f", str(compose_file), "up", "-d"],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            print(f"❌ Failed to start Neo4j:\n{result.stderr}")
            return False
        
        print("✅ Neo4j container started successfully\n")
        return True
    
    except subprocess.TimeoutExpired:
        print("❌ Timeout starting Neo4j container")
        return False
    except FileNotFoundError:
        print("❌ docker-compose command not found. Please install Docker Desktop.")
        return False


def wait_for_neo4j(timeout=60):
    """Wait for Neo4j to become healthy."""
    print("⏳ Waiting for Neo4j to be ready", end="", flush=True)
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            result = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Health.Status}}", "govcon-neo4j"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            health_status = result.stdout.strip()
            if health_status == "healthy":
                print(" ✅\n")
                return True
            
            print(".", end="", flush=True)
            time.sleep(2)
        
        except (subprocess.TimeoutExpired, FileNotFoundError):
            print(".", end="", flush=True)
            time.sleep(2)
    
    print(" ⏱️ Timeout\n")
    return False


def stop_neo4j():
    """Stop Neo4j container gracefully."""
    print("\n🛑 Stopping Neo4j container...")
    
    compose_file = Path(__file__).parent / "docker-compose.neo4j.yml"
    if not compose_file.exists():
        return
    
    try:
        subprocess.run(
            ["docker-compose", "-f", str(compose_file), "down"],
            capture_output=True,
            text=True,
            timeout=30
        )
        print("✅ Neo4j container stopped\n")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


def manage_neo4j_startup():
    """Manage Neo4j container startup if Neo4JStorage is configured."""
    if not is_neo4j_enabled():
        print("ℹ️  NetworkXStorage mode (set GRAPH_STORAGE=Neo4JStorage to enable Neo4j)")
        return True

    print("🔍 Checking Neo4j...")
    
    # Check if Docker is available
    if not check_docker_available():
        print("❌ Docker is not available or not running.")
        print("   Please start Docker Desktop and try again.\n")
        print("   Alternative: Change GRAPH_STORAGE=NetworkXStorage in .env\n")
        return False
    
    # Check if Neo4j is already running
    if is_neo4j_running():
        print("✅ Neo4j container already running\n")
        return True
    
    # Start Neo4j
    if not start_neo4j():
        return False
    
    # Wait for Neo4j to be healthy
    if not wait_for_neo4j():
        print("⚠️  Neo4j health check timeout (continuing anyway)")
        print("   You can verify Neo4j at: http://localhost:7474\n")
    
    return True


if __name__ == "__main__":
    # ANSI color codes for PowerShell
    CYAN = '\033[96m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    MAGENTA = '\033[95m'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    DIM = '\033[2m'
    
    print(f"""
{CYAN}{'═' * 65}{RESET}
  {MAGENTA}Project Theseus{RESET}
  {DIM}Ontology-Based RAG for Federal RFP Analysis{RESET}
{CYAN}{'═' * 65}{RESET}
""")
    
    # Now initialize logging (after banner is displayed)
    from src.core.config import get_settings as _get_settings
    from src.utils.logging_config import setup_logging
    import os as _os
    _settings = _get_settings()
    # Workspace-specific log dir: ./rag_storage/{workspace}/processing.log
    _workspace_log_dir = _os.path.join(_settings.working_dir, _settings.workspace)
    log_info = setup_logging(
        log_level="INFO",
        log_dir="logs",
        workspace_dir=_workspace_log_dir,
        max_file_size=10 * 1024 * 1024,  # 10MB per file
        backup_count=5,
        console_output=True
    )
    
    neo4j_started_by_us = False
    
    try:
        # Manage Neo4j startup
        if not manage_neo4j_startup():
            print("\n❌ Neo4j startup failed. Exiting.\n")
            sys.exit(1)
        
        neo4j_started_by_us = is_neo4j_enabled() and is_neo4j_running()
        
        # Start the RAG server
        print("🚀 Starting Project Theseus...\n")
        asyncio.run(main())
    
    except KeyboardInterrupt:
        print("\n\n🛑 Server stopped by user")
        if neo4j_started_by_us:
            stop_neo4j()
    
    except Exception as e:
        print(f"\n❌ Server error: {e}")
        if neo4j_started_by_us:
            stop_neo4j()
        sys.exit(1)