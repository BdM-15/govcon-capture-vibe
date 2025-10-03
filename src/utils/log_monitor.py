"""
Real-time Log Monitor for RFP Processing

Monitors LightRAG processing logs and correlates chunk IDs with RFP section metadata
to provide real-time visibility into which sections are being processed.

Usage:
    python -m src.utils.log_monitor
    
Or programmatically:
    from src.utils.log_monitor import monitor_processing_logs
    monitor_processing_logs("logs/govcon_server.log")
"""

import re
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# Import chunk metadata lookup
try:
    from src.core.lightrag_chunking import get_chunk_metadata
except ImportError:
    # Fallback if run standalone
    def get_chunk_metadata(chunk_id: str) -> Optional[Dict[str, Any]]:
        return None

logger = logging.getLogger(__name__)


# Regex patterns for LightRAG chunk processing logs
CHUNK_START_PATTERN = re.compile(r'Chunk\s+(\d+)\s+of\s+(\d+)\s+extracted')
CHUNK_ID_PATTERN = re.compile(r'chunk-([a-f0-9]{32})')
TIMEOUT_PATTERN = re.compile(r'C\[(\d+)/(\d+)\]:\s+chunk-([a-f0-9]{32})')


def parse_chunk_log_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parse a LightRAG chunk processing log line.
    
    Args:
        line: Log line to parse
        
    Returns:
        Dict with parsed info, or None if not a chunk processing line
    """
    # Check for chunk completion: "Chunk X of Y extracted Z Ent + W Rel chunk-ID"
    chunk_match = CHUNK_START_PATTERN.search(line)
    chunk_id_match = CHUNK_ID_PATTERN.search(line)
    
    if chunk_match and chunk_id_match:
        chunk_num = int(chunk_match.group(1))
        total_chunks = int(chunk_match.group(2))
        chunk_id = chunk_id_match.group(1)
        
        # Extract entity and relationship counts if present
        ent_rel_match = re.search(r'extracted\s+(\d+)\s+Ent\s+\+\s+(\d+)\s+Rel', line)
        entity_count = int(ent_rel_match.group(1)) if ent_rel_match else 0
        relation_count = int(ent_rel_match.group(2)) if ent_rel_match else 0
        
        return {
            'type': 'chunk_complete',
            'chunk_num': chunk_num,
            'total_chunks': total_chunks,
            'chunk_id': chunk_id,
            'entity_count': entity_count,
            'relation_count': relation_count,
            'timestamp': datetime.now()
        }
    
    # Check for timeout error: "C[X/Y]: chunk-ID"
    timeout_match = TIMEOUT_PATTERN.search(line)
    if timeout_match and 'ReadTimeout' in line:
        chunk_num = int(timeout_match.group(1))
        total_chunks = int(timeout_match.group(2))
        chunk_id = timeout_match.group(3)
        
        return {
            'type': 'chunk_timeout',
            'chunk_num': chunk_num,
            'total_chunks': total_chunks,
            'chunk_id': chunk_id,
            'timestamp': datetime.now()
        }
    
    return None


def format_section_info(metadata: Dict[str, Any]) -> str:
    """
    Format chunk metadata into a readable section info string.
    
    Args:
        metadata: Chunk metadata dict
        
    Returns:
        Formatted string like "Section C - Statement of Work (C.3.1, Page 45, 8 reqs)"
    """
    section_id = metadata.get('section_id', 'Unknown')
    section_title = metadata.get('section_title', 'Unknown Section')
    subsection_id = metadata.get('subsection_id', '')
    page_number = metadata.get('page_number', '?')
    requirements_count = metadata.get('requirements_count', 0)
    
    info = f"Section {section_id} - {section_title}"
    
    if subsection_id:
        info += f" ({subsection_id}, Page {page_number}"
    else:
        info += f" (Page {page_number}"
    
    if requirements_count > 0:
        info += f", {requirements_count} reqs)"
    else:
        info += ")"
    
    return info


def monitor_processing_logs(
    log_file: Path,
    follow: bool = True,
    check_interval: float = 1.0
) -> None:
    """
    Monitor LightRAG processing logs and correlate with RFP section metadata.
    
    Args:
        log_file: Path to the log file to monitor
        follow: If True, continuously monitor for new lines (like tail -f)
        check_interval: Seconds between checking for new lines (when follow=True)
    """
    log_file = Path(log_file)
    
    if not log_file.exists():
        print(f"❌ Log file not found: {log_file}")
        return
    
    print(f"📊 Monitoring RFP processing logs: {log_file}")
    print(f"   Looking for chunk completion and timeout events...\n")
    
    chunk_start_times = {}
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            # Read existing lines first
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                parsed = parse_chunk_log_line(line)
                if parsed:
                    process_chunk_event(parsed, chunk_start_times)
            
            # If follow mode, continue monitoring
            if follow:
                print("\n⏳ Waiting for new log entries (Ctrl+C to stop)...\n")
                
                while True:
                    line = f.readline()
                    if line:
                        line = line.strip()
                        parsed = parse_chunk_log_line(line)
                        if parsed:
                            process_chunk_event(parsed, chunk_start_times)
                    else:
                        time.sleep(check_interval)
    
    except KeyboardInterrupt:
        print("\n\n🛑 Monitoring stopped by user")
    except Exception as e:
        print(f"\n❌ Error monitoring logs: {e}")


def process_chunk_event(
    event: Dict[str, Any],
    chunk_start_times: Dict[int, datetime]
) -> None:
    """
    Process and log a chunk processing event with section information.
    
    Args:
        event: Parsed chunk event
        chunk_start_times: Dict tracking when each chunk started processing
    """
    event_type = event['type']
    chunk_num = event['chunk_num']
    total_chunks = event['total_chunks']
    chunk_id = event['chunk_id']
    
    # Try to get section metadata for this chunk
    full_chunk_id = f"chunk-{chunk_id}"
    metadata = get_chunk_metadata(full_chunk_id)
    
    section_info = "Section metadata not available"
    if metadata:
        section_info = format_section_info(metadata)
    
    if event_type == 'chunk_complete':
        entity_count = event['entity_count']
        relation_count = event['relation_count']
        
        # Calculate processing time if we tracked the start
        time_info = ""
        if chunk_num in chunk_start_times:
            elapsed = (event['timestamp'] - chunk_start_times[chunk_num]).total_seconds()
            time_info = f" in {elapsed:.1f}s"
        
        print(
            f"✅ Chunk {chunk_num}/{total_chunks}: {section_info} "
            f"({entity_count} Ent + {relation_count} Rel){time_info}"
        )
        
        # Remove from tracking
        if chunk_num in chunk_start_times:
            del chunk_start_times[chunk_num]
    
    elif event_type == 'chunk_timeout':
        # Track when chunk started (for next completion)
        chunk_start_times[chunk_num] = event['timestamp']
        
        print(
            f"⏱️  TIMEOUT: Chunk {chunk_num}/{total_chunks}: {section_info} "
            f"(exceeded processing timeout)"
        )


def analyze_completed_processing(log_file: Path) -> Dict[str, Any]:
    """
    Analyze a completed processing run and generate section statistics.
    
    Args:
        log_file: Path to the completed log file
        
    Returns:
        Dict with section-level statistics
    """
    log_file = Path(log_file)
    
    if not log_file.exists():
        return {'error': f'Log file not found: {log_file}'}
    
    section_stats = {}
    chunk_events = []
    
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            parsed = parse_chunk_log_line(line.strip())
            if parsed:
                chunk_events.append(parsed)
    
    # Analyze events
    for event in chunk_events:
        if event['type'] == 'chunk_complete':
            chunk_id = f"chunk-{event['chunk_id']}"
            metadata = get_chunk_metadata(chunk_id)
            
            if metadata:
                section_id = metadata.get('section_id', 'Unknown')
                
                if section_id not in section_stats:
                    section_stats[section_id] = {
                        'chunk_count': 0,
                        'total_entities': 0,
                        'total_relations': 0,
                        'timeout_count': 0
                    }
                
                section_stats[section_id]['chunk_count'] += 1
                section_stats[section_id]['total_entities'] += event['entity_count']
                section_stats[section_id]['total_relations'] += event['relation_count']
        
        elif event['type'] == 'chunk_timeout':
            chunk_id = f"chunk-{event['chunk_id']}"
            metadata = get_chunk_metadata(chunk_id)
            
            if metadata:
                section_id = metadata.get('section_id', 'Unknown')
                
                if section_id in section_stats:
                    section_stats[section_id]['timeout_count'] += 1
    
    return {
        'total_chunks': len([e for e in chunk_events if e['type'] == 'chunk_complete']),
        'total_timeouts': len([e for e in chunk_events if e['type'] == 'chunk_timeout']),
        'section_stats': section_stats
    }


if __name__ == "__main__":
    import sys
    
    # Default log file
    log_file = Path("logs/govcon_server.log")
    
    # Allow custom log file from command line
    if len(sys.argv) > 1:
        log_file = Path(sys.argv[1])
    
    monitor_processing_logs(log_file, follow=True)
