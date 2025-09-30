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
- Local Ollama integration (qwen2.5-coder:7b + bge-m3)

Usage:
    python app.py
    
Then visit: http://localhost:9621
"""

import asyncio
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Import our extended server
from govcon_server import main

if __name__ == "__main__":
    print("🎯 Starting GovCon Capture Vibe...")
    print("   Enhanced LightRAG server with RFP analysis capabilities")
    print("   Grounded in Shipley methodology for government contracting\n")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"\n❌ Server error: {e}")
        sys.exit(1)