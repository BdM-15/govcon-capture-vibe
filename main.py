"""
GovCon RFP Analyzer - Main Entry Point

Local, zero-cost RAG app for federal RFP compliance automation.
Parse RFPs/PWS, generate Shipley-style matrices/outlines/gaps/Q&A.

Phase 1: LightRAG native document processing + PydanticAI structured extraction
"""

import asyncio
import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

def main():
    """Main entry point for the application."""
    print("🏛️ GovCon RFP Analyzer - Phase 1")
    print("=" * 50)
    print("Local RAG-powered federal RFP analysis")
    print("Grounded in Shipley Methodology")
    print("=" * 50)
    print()
    
    print("Available interfaces:")
    print("1. Streamlit Web Interface (recommended)")
    print("2. Command Line Interface")
    print("3. Jupyter Notebook Demo")
    print()
    
    choice = input("Select interface (1-3) or 'q' to quit: ").strip()
    
    if choice == '1':
        run_streamlit_interface()
    elif choice == '2':
        run_cli_interface()
    elif choice == '3':
        run_jupyter_demo()
    elif choice.lower() == 'q':
        print("Goodbye! 👋")
        sys.exit(0)
    else:
        print("Invalid choice. Please select 1-3 or 'q'.")
        main()


def run_streamlit_interface():
    """Launch the Streamlit web interface."""
    print("🚀 Launching Streamlit web interface...")
    print("This will open in your default web browser.")
    print("Press Ctrl+C to stop the server.")
    print()
    
    try:
        import subprocess
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", 
            str(Path(__file__).parent / "src" / "streamlit_interface.py"),
            "--server.address", "localhost",
            "--server.port", "8501",
            "--browser.serverAddress", "localhost"
        ])
    except KeyboardInterrupt:
        print("\n🛑 Streamlit server stopped.")
    except Exception as e:
        print(f"❌ Failed to launch Streamlit: {e}")
        print("Make sure you have streamlit installed: uv add streamlit")


def run_cli_interface():
    """Run the command line interface."""
    print("🖥️ Command Line Interface")
    print("Coming in Phase 2 - Basic CLI for document processing")
    print()
    
    # Placeholder for CLI implementation
    file_path = input("Enter RFP file path (or press Enter to cancel): ").strip()
    
    if file_path and Path(file_path).exists():
        print(f"📄 Processing: {file_path}")
        asyncio.run(process_file_cli(file_path))
    else:
        print("❌ File not found or cancelled.")


async def process_file_cli(file_path: str):
    """Process a single file via CLI."""
    try:
        from src.document_processor import DocumentProcessor
        from src.extraction_agent import quick_requirement_extraction
        
        print("🔄 Initializing processor...")
        processor = DocumentProcessor()
        
        print("📖 Extracting text...")
        text = processor.extract_text(file_path)
        
        print("🔍 Extracting requirements...")
        requirements = await quick_requirement_extraction(text[:10000])  # Limit for demo
        
        print(f"\n✅ Found {len(requirements)} requirements:")
        for req in requirements[:5]:  # Show first 5
            print(f"  • {req.id}: {req.text[:100]}...")
        
        if len(requirements) > 5:
            print(f"  ... and {len(requirements) - 5} more")
        
        print("\n💡 For full analysis, use the Streamlit interface!")
        
    except Exception as e:
        print(f"❌ Processing failed: {e}")


def run_jupyter_demo():
    """Launch Jupyter notebook demo."""
    print("📓 Jupyter Notebook Demo")
    print("Opening demo notebook...")
    print()
    
    try:
        import subprocess
        notebook_path = Path(__file__).parent / "lightrag_ollama_demo.py"
        
        if notebook_path.exists():
            subprocess.run([
                sys.executable, "-m", "jupyter", "notebook", 
                str(notebook_path)
            ])
        else:
            print("❌ Demo notebook not found.")
            print("Check lightrag_ollama_demo.py in the project root.")
    
    except Exception as e:
        print(f"❌ Failed to launch Jupyter: {e}")
        print("Make sure you have jupyter installed: uv add jupyter")


def check_dependencies():
    """Check if required dependencies are available."""
    missing_deps = []
    
    try:
        import lightrag
    except ImportError:
        missing_deps.append("lightrag-hku")
    
    try:
        import pydantic_ai
    except ImportError:
        missing_deps.append("pydantic-ai")
    
    try:
        import streamlit
    except ImportError:
        missing_deps.append("streamlit")
    
    if missing_deps:
        print("⚠️ Missing dependencies:")
        for dep in missing_deps:
            print(f"  • {dep}")
        print()
        print("Install with: uv sync")
        print("Or individually: uv add <package-name>")
        return False
    
    return True


if __name__ == "__main__":
    print("🔍 Checking dependencies...")
    
    if check_dependencies():
        print("✅ All dependencies available")
        print()
        main()
    else:
        print("❌ Please install missing dependencies first")
        sys.exit(1)
