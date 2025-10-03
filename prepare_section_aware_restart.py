#!/usr/bin/env python3
"""
Prepare for section-aware chunking restart after chunk 33 timeout.

This script:
1. Backs up the failed run (chunks 1-32)
2. Clears rag_storage for fresh start
3. Clears logs
4. Prepares monitoring

Usage:
    python prepare_section_aware_restart.py
    
Then manually run:
    python app.py
"""

import json
import shutil
from pathlib import Path
from datetime import datetime


def main():
    print("=" * 80)
    print("SECTION-AWARE CHUNKING RESTART PREPARATION")
    print("=" * 80)
    
    # Timestamp for backup
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Paths
    rag_storage = Path("rag_storage")
    backup_base = Path("rag_storage_backups")
    backup_dir = backup_base / f"failed_run_chunk33_{timestamp}"
    logs_dir = Path("logs")
    
    # Step 1: Backup failed run
    print("\n[1/4] Backing up failed run (chunks 1-32)...")
    if rag_storage.exists() and any(rag_storage.iterdir()):
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy all rag_storage files
        file_count = 0
        for file in rag_storage.glob("*"):
            if file.is_file():
                shutil.copy2(file, backup_dir / file.name)
                file_count += 1
        
        print(f"   ✅ Backed up {file_count} files to: {backup_dir}")
        
        # Analyze what we have
        try:
            chunks_file = rag_storage / "kv_store_text_chunks.json"
            if chunks_file.exists():
                with open(chunks_file, 'r', encoding='utf-8') as f:
                    chunks = json.load(f)
                print(f"   📊 Captured {len(chunks)} chunks from failed run")
        except Exception as e:
            print(f"   ⚠️  Could not analyze chunks: {e}")
    else:
        print("   ⚠️  No rag_storage to backup (directory empty or missing)")
    
    # Step 2: Clear rag_storage
    print("\n[2/4] Clearing rag_storage for fresh start...")
    if rag_storage.exists():
        for file in rag_storage.glob("*"):
            if file.is_file():
                file.unlink()
        print("   ✅ rag_storage cleared")
    else:
        rag_storage.mkdir(parents=True, exist_ok=True)
        print("   ✅ rag_storage created")
    
    # Step 3: Clear logs
    print("\n[3/4] Clearing logs...")
    log_files = [
        logs_dir / "lightrag.log",
        logs_dir / "govcon_server.log",
        logs_dir / "errors.log"
    ]
    
    for log_file in log_files:
        if log_file.exists():
            log_file.write_text("", encoding='utf-8')
            print(f"   ✅ Cleared {log_file.name}")
        else:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            log_file.touch()
            print(f"   ✅ Created {log_file.name}")
    
    # Step 4: Create analysis outputs directory
    print("\n[4/4] Preparing analysis outputs directory...")
    analysis_dir = Path("analysis_outputs")
    analysis_dir.mkdir(exist_ok=True)
    print(f"   ✅ Analysis outputs ready at: {analysis_dir}")
    
    # Summary
    print("\n" + "=" * 80)
    print("✅ PREPARATION COMPLETE")
    print("=" * 80)
    print("\n📋 NEXT STEPS:")
    print("\n1. Start server with section-aware chunking:")
    print("   python app.py")
    print("\n2. Upload RFP document:")
    print("   - Open http://localhost:9621")
    print("   - Click 'Upload Document'")
    print("   - Select: inputs/__enqueued__/_N6945025R0003.pdf")
    print("\n3. Monitor section detection (in new terminal):")
    print("   python monitor_section_processing.py")
    print("\n4. Watch for section-aware logs:")
    print('   - Look for: "🎯 RFP document detected"')
    print('   - Look for: "📝 Chunk X: Section Y - Title"')
    print('   - Look for: "📊 Section distribution"')
    print("\n⚠️  CRITICAL: If section detection fails, you'll see standard token-based chunking")
    print("   This means fallback occurred - document format may not match expected patterns")
    print("\n" + "=" * 80)
    print(f"Backup location: {backup_dir}")
    print("=" * 80)


if __name__ == "__main__":
    main()
