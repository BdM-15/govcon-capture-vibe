"""
Simple Chunk Analysis Script

Analyzes completed RFP processing to show which sections had issues.
Run this after processing completes (or fails) to see section-to-chunk mapping.

Usage:
    python analyze_chunks.py
"""

import json
import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime

def parse_lightrag_log(log_file: Path):
    """Parse lightrag.log to extract chunk processing info."""
    chunks = []
    
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            # Match: "Chunk X of Y extracted Z Ent + W Rel chunk-HASH"
            match = re.search(r'Chunk\s+(\d+)\s+of\s+(\d+)\s+extracted\s+(\d+)\s+Ent\s+\+\s+(\d+)\s+Rel\s+chunk-([a-f0-9]+)', line)
            if match:
                chunk_num = int(match.group(1))
                total = int(match.group(2))
                entities = int(match.group(3))
                relations = int(match.group(4))
                chunk_hash = match.group(5)
                
                # Extract timestamp
                time_match = re.match(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', line)
                timestamp = time_match.group(1) if time_match else None
                
                chunks.append({
                    'chunk_num': chunk_num,
                    'total': total,
                    'entities': entities,
                    'relations': relations,
                    'chunk_hash': chunk_hash,
                    'chunk_id': f'chunk-{chunk_hash}',
                    'timestamp': timestamp
                })
            
            # Check for timeouts
            timeout_match = re.search(r'C\[(\d+)/(\d+)\]:\s+chunk-([a-f0-9]+)', line)
            if timeout_match and 'ReadTimeout' in line:
                chunk_num = int(timeout_match.group(1))
                chunk_hash = timeout_match.group(3)
                print(f"\n⏱️  TIMEOUT detected: Chunk {chunk_num} (chunk-{chunk_hash})")
    
    return chunks


def load_chunk_metadata(storage_dir: Path):
    """Load chunk metadata from rag_storage if available."""
    metadata_file = storage_dir / 'kv_store_text_chunks.json'
    
    if not metadata_file.exists():
        return None
    
    try:
        with open(metadata_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data
    except Exception as e:
        print(f"Warning: Could not load chunk metadata: {e}")
        return None


def analyze_processing(log_file: Path, storage_dir: Path):
    """Main analysis function."""
    print("=" * 80)
    print("📊 RFP PROCESSING ANALYSIS")
    print("=" * 80)
    print()
    
    # Parse log
    print("📖 Parsing lightrag.log...")
    chunks = parse_lightrag_log(log_file)
    
    if not chunks:
        print("❌ No chunk data found in log file")
        return
    
    print(f"✅ Found {len(chunks)} processed chunks")
    print()
    
    # Load metadata if available
    print("🔍 Loading chunk metadata...")
    metadata = load_chunk_metadata(storage_dir)
    
    if metadata:
        print(f"✅ Metadata loaded ({len(metadata)} records)")
    else:
        print("⚠️  Metadata not available (processing may not be complete)")
    print()
    
    # Calculate statistics
    total_entities = sum(c['entities'] for c in chunks)
    total_relations = sum(c['relations'] for c in chunks)
    avg_entities = total_entities / len(chunks) if chunks else 0
    avg_relations = total_relations / len(chunks) if chunks else 0
    
    print("=" * 80)
    print("📈 PROCESSING STATISTICS")
    print("=" * 80)
    print(f"Total Chunks Processed:  {len(chunks)}")
    print(f"Total Entities Extracted: {total_entities}")
    print(f"Total Relations Extracted: {total_relations}")
    print(f"Average Entities/Chunk:  {avg_entities:.1f}")
    print(f"Average Relations/Chunk:  {avg_relations:.1f}")
    print()
    
    # Show chunk details
    print("=" * 80)
    print("📋 CHUNK PROCESSING DETAILS")
    print("=" * 80)
    print()
    
    for chunk in chunks:
        # Try to get section info from metadata
        section_info = "Section metadata not available"
        if metadata and chunk['chunk_id'] in metadata:
            chunk_meta = metadata[chunk['chunk_id']]
            if isinstance(chunk_meta, dict) and 'metadata' in chunk_meta:
                meta = chunk_meta['metadata']
                section_id = meta.get('section_id', '?')
                section_title = meta.get('section_title', 'Unknown')
                page = meta.get('page_number', '?')
                reqs = meta.get('requirements_count', 0)
                section_info = f"Section {section_id} - {section_title} (Page {page}, {reqs} reqs)"
        
        print(f"Chunk {chunk['chunk_num']:2d}/{chunk['total']}: "
              f"{chunk['entities']:2d} Ent + {chunk['relations']:2d} Rel | "
              f"{section_info}")
    
    print()
    print("=" * 80)
    
    # Section summary if metadata available
    if metadata:
        print("📊 SECTION SUMMARY")
        print("=" * 80)
        print()
        
        section_stats = defaultdict(lambda: {'chunks': 0, 'entities': 0, 'relations': 0})
        
        for chunk in chunks:
            if chunk['chunk_id'] in metadata:
                chunk_meta = metadata[chunk['chunk_id']]
                if isinstance(chunk_meta, dict) and 'metadata' in chunk_meta:
                    section_id = chunk_meta['metadata'].get('section_id', 'Unknown')
                    section_stats[section_id]['chunks'] += 1
                    section_stats[section_id]['entities'] += chunk['entities']
                    section_stats[section_id]['relations'] += chunk['relations']
        
        for section_id in sorted(section_stats.keys()):
            stats = section_stats[section_id]
            print(f"Section {section_id}: {stats['chunks']} chunks, "
                  f"{stats['entities']} entities, {stats['relations']} relations")
        
        print()
        print("=" * 80)


if __name__ == "__main__":
    # Paths
    log_file = Path("logs/lightrag.log")
    storage_dir = Path("rag_storage")
    
    if not log_file.exists():
        print(f"❌ Log file not found: {log_file}")
        print("   Make sure you're running this from the project root directory")
        exit(1)
    
    analyze_processing(log_file, storage_dir)
    
    print()
    print("💡 TIP: This script will show section details once processing completes")
    print("   and the kv_store_text_chunks.json file is created.")
