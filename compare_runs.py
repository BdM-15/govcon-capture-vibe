#!/usr/bin/env python3
"""
Compare failed run (chunk 33 timeout) with section-aware run.

Usage:
    python compare_runs.py
"""

import json
from pathlib import Path
from datetime import datetime


def load_chunks(chunks_file: Path) -> dict:
    """Load chunks from JSON file."""
    if not chunks_file.exists():
        return {}
    
    with open(chunks_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def analyze_chunks(chunks: dict, label: str) -> dict:
    """Analyze chunk statistics."""
    if not chunks:
        return {
            'total_chunks': 0,
            'label': label,
            'completed': False
        }
    
    # Calculate stats
    chunk_list = list(chunks.values())
    
    stats = {
        'label': label,
        'total_chunks': len(chunk_list),
        'total_content_length': sum(len(c.get('content', '')) for c in chunk_list),
        'avg_content_length': sum(len(c.get('content', '')) for c in chunk_list) / len(chunk_list) if chunk_list else 0,
        'max_content_length': max((len(c.get('content', '')) for c in chunk_list), default=0),
        'min_content_length': min((len(c.get('content', '')) for c in chunk_list), default=0),
        'completed': True
    }
    
    # Check for section metadata (section-aware indicator)
    section_aware_chunks = [c for c in chunk_list if 'section' in c]
    stats['section_aware'] = len(section_aware_chunks) > 0
    stats['section_aware_percentage'] = (len(section_aware_chunks) / len(chunk_list) * 100) if chunk_list else 0
    
    if section_aware_chunks:
        sections = set(c.get('section', '') for c in section_aware_chunks if c.get('section'))
        stats['sections_found'] = sorted(sections)
        stats['section_count'] = len(sections)
    else:
        stats['sections_found'] = []
        stats['section_count'] = 0
    
    return stats


def main():
    print("=" * 80)
    print("RUN COMPARISON: Failed (Chunk 33 Timeout) vs Section-Aware")
    print("=" * 80)
    
    # Find most recent backup (failed run)
    backup_base = Path("rag_storage_backups")
    failed_run_dirs = sorted(backup_base.glob("failed_run_chunk33_*"))
    
    if not failed_run_dirs:
        print("\n❌ No failed run backup found")
        print("   Expected: rag_storage_backups/failed_run_chunk33_*/")
        return
    
    failed_run_dir = failed_run_dirs[-1]  # Most recent
    print(f"\n📁 Failed run: {failed_run_dir.name}")
    
    # Load failed run chunks
    failed_chunks_file = failed_run_dir / "kv_store_text_chunks.json"
    failed_chunks = load_chunks(failed_chunks_file)
    failed_stats = analyze_chunks(failed_chunks, "Failed Run (Chunks 1-32)")
    
    # Load current run chunks
    current_chunks_file = Path("rag_storage/kv_store_text_chunks.json")
    current_chunks = load_chunks(current_chunks_file)
    current_stats = analyze_chunks(current_chunks, "Section-Aware Run")
    
    # Display comparison
    print("\n" + "=" * 80)
    print("COMPARISON RESULTS")
    print("=" * 80)
    
    print(f"\n{'Metric':<35} | {'Failed Run':<20} | {'Section-Aware':<20}")
    print("-" * 80)
    
    print(f"{'Total chunks':<35} | {failed_stats['total_chunks']:<20} | {current_stats['total_chunks']:<20}")
    
    if failed_stats['completed'] and current_stats['completed']:
        print(f"{'Avg chunk length (chars)':<35} | {failed_stats['avg_content_length']:<20.0f} | {current_stats['avg_content_length']:<20.0f}")
        print(f"{'Max chunk length (chars)':<35} | {failed_stats['max_content_length']:<20} | {current_stats['max_content_length']:<20}")
        print(f"{'Min chunk length (chars)':<35} | {failed_stats['min_content_length']:<20} | {current_stats['min_content_length']:<20}")
        print(f"{'Section-aware':<35} | {'No':<20} | {'Yes' if current_stats['section_aware'] else 'No':<20}")
        
        if current_stats['section_aware']:
            print(f"{'Sections detected':<35} | {'-':<20} | {current_stats['section_count']:<20}")
            print(f"\nSections found: {', '.join(current_stats['sections_found'])}")
    
    print("\n" + "=" * 80)
    print("ANALYSIS")
    print("=" * 80)
    
    if not current_stats['completed']:
        print("\n⏳ Section-aware run not yet complete or not started")
        print("   Start processing and run this script again when done")
        return
    
    if failed_stats['total_chunks'] >= 32 and current_stats['total_chunks'] <= 32:
        print("\n⚠️  Section-aware run also stopped at chunk 33 area")
        print("   This suggests chunk 33 content is problematic regardless of chunking strategy")
        print("   Recommendation: Analyze chunk 33 content to identify root cause")
    
    elif current_stats['total_chunks'] > failed_stats['total_chunks']:
        print(f"\n✅ Section-aware run progressed further! ({current_stats['total_chunks']} vs {failed_stats['total_chunks']} chunks)")
        print("   Section-aware chunking appears to be helping")
    
    if current_stats['section_aware']:
        print("\n✅ Section-aware chunking is ACTIVE")
        print(f"   Detected {current_stats['section_count']} sections")
        print("   This provides better visibility into content structure")
    else:
        print("\n⚠️  Section-aware chunking NOT detected")
        print("   Possible reasons:")
        print("   1. Document doesn't have standard 'SECTION X' headers")
        print("   2. Regex patterns don't match this document format")
        print("   3. Fallback to token-based chunking occurred")
    
    # Chunk size comparison
    if failed_stats['completed'] and current_stats['completed']:
        print("\n📊 CHUNK SIZE ANALYSIS:")
        
        if current_stats['max_content_length'] < failed_stats['max_content_length']:
            reduction = (1 - current_stats['max_content_length'] / failed_stats['max_content_length']) * 100
            print(f"   ✅ Max chunk size reduced by {reduction:.1f}%")
            print(f"      Failed run: {failed_stats['max_content_length']:,} chars")
            print(f"      Section-aware: {current_stats['max_content_length']:,} chars")
            print("   This should reduce timeout risk!")
        
        elif current_stats['max_content_length'] > failed_stats['max_content_length']:
            print(f"   ⚠️  Max chunk size increased")
            print(f"      Failed run: {failed_stats['max_content_length']:,} chars")
            print(f"      Section-aware: {current_stats['max_content_length']:,} chars")
            print("   Section boundaries may not be helping in this document")
    
    print("\n" + "=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)
    
    if current_stats['total_chunks'] > 35:
        print("\n✅ SUCCESS PATH:")
        print("   1. Section-aware chunking successfully passed chunk 33 area")
        print("   2. Continue monitoring until completion")
        print("   3. Run analyze_chunks.py for detailed statistics")
        print("   4. Document findings in FINE_TUNING_ROADMAP.md")
    
    elif current_stats['total_chunks'] <= 32:
        print("\n⚠️  TROUBLESHOOTING PATH:")
        print("   1. Check logs for timeout errors around chunk 33")
        print("   2. If timeout occurred again, increase LLM_TIMEOUT further")
        print("   3. Consider extracting chunk 33 content for manual analysis")
        print("   4. May need document-specific chunking strategy")
    
    else:
        print("\n⏳ MONITORING PATH:")
        print("   1. Processing is in the critical chunk 33-35 range")
        print("   2. Monitor GPU utilization with nvidia-smi")
        print("   3. Watch logs for completion or timeout")
        print("   4. Run this comparison again when processing completes")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
