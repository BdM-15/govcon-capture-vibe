#!/usr/bin/env python3
"""
Real-time monitoring of section-aware chunking processing.

Monitors lightrag.log for:
- Section detection confirmation
- Chunk processing with section context
- Performance metrics
- Warnings and errors

Usage:
    python monitor_section_processing.py
    
Press Ctrl+C to stop monitoring.
"""

import time
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict


def parse_log_line(line: str) -> dict:
    """Parse a log line and extract key information."""
    info = {
        'timestamp': None,
        'level': None,
        'message': None,
        'chunk_num': None,
        'total_chunks': None,
        'entities': None,
        'relations': None,
        'section': None,
        'is_section_aware': False,
        'is_warning': False,
        'is_error': False
    }
    
    # Extract timestamp and level
    match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+\|\s+(\w+)\s+\|', line)
    if match:
        info['timestamp'] = match.group(1)
        info['level'] = match.group(2)
    
    # Check for section-aware indicators
    if '🎯' in line or 'RFP document detected' in line:
        info['is_section_aware'] = True
        info['message'] = 'Section-aware chunking activated!'
    
    if '📝' in line or 'Section' in line:
        info['is_section_aware'] = True
        # Extract section info
        section_match = re.search(r'Section ([A-M])', line)
        if section_match:
            info['section'] = section_match.group(1)
    
    if '📊' in line or 'Section distribution' in line:
        info['is_section_aware'] = True
        info['message'] = 'Section distribution summary'
    
    # Extract chunk completion info
    chunk_match = re.search(r'Chunk (\d+) of (\d+) extracted (\d+) Ent \+ (\d+) Rel', line)
    if chunk_match:
        info['chunk_num'] = int(chunk_match.group(1))
        info['total_chunks'] = int(chunk_match.group(2))
        info['entities'] = int(chunk_match.group(3))
        info['relations'] = int(chunk_match.group(4))
    
    # Check for warnings and errors
    if 'WARNING' in line or info['level'] == 'WARNING':
        info['is_warning'] = True
    if 'ERROR' in line or info['level'] == 'ERROR':
        info['is_error'] = True
    
    return info


def format_progress_bar(current: int, total: int, width: int = 40) -> str:
    """Create a progress bar."""
    progress = current / total
    filled = int(width * progress)
    bar = '█' * filled + '░' * (width - filled)
    percentage = progress * 100
    return f"[{bar}] {percentage:.1f}% ({current}/{total})"


def main():
    log_file = Path("logs/lightrag.log")
    
    if not log_file.exists():
        print("❌ Error: logs/lightrag.log not found")
        print("   Make sure the server is running: python app.py")
        return
    
    print("=" * 80)
    print("SECTION-AWARE CHUNKING MONITOR")
    print("=" * 80)
    print(f"Monitoring: {log_file}")
    print("Press Ctrl+C to stop")
    print("=" * 80)
    
    # Track statistics
    stats = {
        'section_aware_detected': False,
        'chunks_completed': 0,
        'total_chunks': 0,
        'total_entities': 0,
        'total_relations': 0,
        'warnings': 0,
        'errors': 0,
        'sections_seen': set(),
        'chunk_times': [],
        'last_chunk_time': None,
        'start_time': None
    }
    
    # Track per-section stats
    section_stats = defaultdict(lambda: {'chunks': 0, 'entities': 0, 'relations': 0})
    
    # Follow the log file
    with open(log_file, 'r', encoding='utf-8') as f:
        # Move to end of file
        f.seek(0, 2)
        
        print("\n⏳ Waiting for processing to start...\n")
        
        try:
            while True:
                line = f.readline()
                
                if not line:
                    time.sleep(0.5)
                    continue
                
                info = parse_log_line(line)
                
                # Section-aware detection
                if info['is_section_aware'] and not stats['section_aware_detected']:
                    stats['section_aware_detected'] = True
                    print("\n" + "=" * 80)
                    print("🎯 SECTION-AWARE CHUNKING DETECTED!")
                    print("=" * 80)
                    if info['message']:
                        print(f"   {info['message']}")
                    print()
                
                # Chunk completion
                if info['chunk_num']:
                    stats['chunks_completed'] = info['chunk_num']
                    stats['total_chunks'] = info['total_chunks']
                    stats['total_entities'] += info['entities']
                    stats['total_relations'] += info['relations']
                    
                    if stats['start_time'] is None:
                        stats['start_time'] = datetime.now()
                    
                    # Calculate chunk time
                    now = datetime.now()
                    if stats['last_chunk_time']:
                        chunk_time = (now - stats['last_chunk_time']).total_seconds()
                        stats['chunk_times'].append(chunk_time)
                    stats['last_chunk_time'] = now
                    
                    # Track section stats
                    if info['section']:
                        stats['sections_seen'].add(info['section'])
                        section_stats[info['section']]['chunks'] += 1
                        section_stats[info['section']]['entities'] += info['entities']
                        section_stats[info['section']]['relations'] += info['relations']
                    
                    # Display progress
                    print(f"\r{info['timestamp']} | ", end='')
                    print(format_progress_bar(info['chunk_num'], info['total_chunks']), end='')
                    
                    if info['section']:
                        print(f" | Section {info['section']}", end='')
                    
                    print(f" | {info['entities']} Ent + {info['relations']} Rel", end='')
                    
                    if stats['chunk_times']:
                        avg_time = sum(stats['chunk_times']) / len(stats['chunk_times'])
                        print(f" | Avg: {avg_time:.1f}s", end='')
                    
                    print(flush=True)
                    
                    # Special alert for chunk 33 area
                    if info['chunk_num'] == 33:
                        print("\n⚠️  CHUNK 33 REACHED - This was the timeout chunk!")
                        print("   Monitoring closely...\n")
                    
                    if 32 <= info['chunk_num'] <= 35:
                        elapsed = (now - stats['last_chunk_time']).total_seconds() if stats['last_chunk_time'] else 0
                        print(f"   📊 Chunk {info['chunk_num']} completed in {elapsed:.1f}s")
                
                # Warnings
                if info['is_warning']:
                    stats['warnings'] += 1
                    if stats['warnings'] <= 5:  # Only show first 5
                        print(f"\n⚠️  Warning: {line.strip()}")
                
                # Errors
                if info['is_error']:
                    stats['errors'] += 1
                    print(f"\n❌ Error: {line.strip()}")
                    
                    # Check for timeout
                    if 'ReadTimeout' in line or 'timeout' in line.lower():
                        print("\n🚨 TIMEOUT DETECTED!")
                        chunk_match = re.search(r'C\[(\d+)/(\d+)\]', line)
                        if chunk_match:
                            chunk_num = chunk_match.group(1)
                            print(f"   Failed chunk: {chunk_num}")
        
        except KeyboardInterrupt:
            print("\n\n" + "=" * 80)
            print("MONITORING STOPPED")
            print("=" * 80)
            
            # Display final statistics
            if stats['chunks_completed'] > 0:
                print("\n📊 FINAL STATISTICS:")
                print(f"   Chunks completed: {stats['chunks_completed']}/{stats['total_chunks']}")
                print(f"   Total entities: {stats['total_entities']}")
                print(f"   Total relations: {stats['total_relations']}")
                print(f"   Warnings: {stats['warnings']}")
                print(f"   Errors: {stats['errors']}")
                
                if stats['chunk_times']:
                    avg_time = sum(stats['chunk_times']) / len(stats['chunk_times'])
                    min_time = min(stats['chunk_times'])
                    max_time = max(stats['chunk_times'])
                    print(f"\n⏱️  TIMING:")
                    print(f"   Average chunk time: {avg_time:.1f}s")
                    print(f"   Fastest chunk: {min_time:.1f}s")
                    print(f"   Slowest chunk: {max_time:.1f}s")
                
                if stats['start_time']:
                    elapsed = (datetime.now() - stats['start_time']).total_seconds()
                    print(f"   Total elapsed: {elapsed/60:.1f} minutes")
                
                if stats['sections_seen']:
                    print(f"\n📍 SECTIONS PROCESSED: {', '.join(sorted(stats['sections_seen']))}")
                    
                    print("\n📈 PER-SECTION BREAKDOWN:")
                    for section in sorted(section_stats.keys()):
                        s = section_stats[section]
                        avg_ent = s['entities'] / s['chunks'] if s['chunks'] > 0 else 0
                        avg_rel = s['relations'] / s['chunks'] if s['chunks'] > 0 else 0
                        print(f"   Section {section}: {s['chunks']} chunks | "
                              f"{s['entities']} ent ({avg_ent:.1f} avg) | "
                              f"{s['relations']} rel ({avg_rel:.1f} avg)")
                
                print(f"\n✅ Section-aware chunking: {'ACTIVE' if stats['section_aware_detected'] else 'NOT DETECTED'}")
            
            print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
