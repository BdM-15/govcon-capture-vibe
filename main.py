"""
GovCon RFP Analyzer - Simple Streamlit Launch

This is now just a launcher for the Streamlit app.
Use: streamlit run app.py instead
"""

import subprocess
import sys
from pathlib import Path

def main():
    """Launch the Streamlit interface directly."""
    print("🏛️ GovCon RFP Analyzer")
    print("Use: streamlit run app.py")
    print()
    print("Launching Streamlit app...")
    
    try:
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", "app.py",
            "--server.address", "localhost",
            "--server.port", "8501"
        ])
    except Exception as e:
        print(f"❌ Failed to launch: {e}")

if __name__ == "__main__":
    main()
