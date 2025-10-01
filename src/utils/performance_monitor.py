"""
Simple Performance Monitor for RFP Processing

Tracks chunk processing times, GPU utilization, and LLM performance
to help optimize configuration and identify bottlenecks.
"""

import time
import logging
from typing import Dict, List, Optional
from datetime import datetime
import psutil
import subprocess
import json
from pathlib import Path

logger = logging.getLogger(__name__)

class RFPPerformanceMonitor:
    """Simple performance monitoring for RFP processing"""
    
    def __init__(self, log_file: Optional[str] = None):
        """Initialize performance monitor with optional log file"""
        self.chunk_times: List[Dict] = []
        self.processing_stats: Dict = {}
        self.start_time = None
        
        # Set up log file if specified
        if log_file:
            self.log_file = Path(log_file)
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
        else:
            self.log_file = None
    
    def start_processing(self, document_name: str, total_chunks: int = None):
        """Mark the start of document processing"""
        self.start_time = time.time()
        self.processing_stats = {
            "document": document_name,
            "start_time": datetime.now().isoformat(),
            "total_chunks": total_chunks,
            "chunks_processed": 0,
            "total_processing_time": 0,
            "avg_chunk_time": 0,
            "gpu_info": self._get_gpu_info()
        }
        
        logger.info(f"📊 Performance Monitor: Started processing '{document_name}'")
        if total_chunks:
            logger.info(f"📊 Expected chunks: {total_chunks}")
    
    def start_chunk(self, chunk_id: str, chunk_size: int = None):
        """Mark the start of chunk processing"""
        chunk_start = {
            "chunk_id": chunk_id,
            "start_time": time.time(),
            "chunk_size": chunk_size,
            "start_memory": self._get_memory_usage()
        }
        
        # Store for later completion
        if not hasattr(self, '_current_chunk'):
            self._current_chunk = {}
        self._current_chunk[chunk_id] = chunk_start
        
        logger.info(f"📊 Chunk {chunk_id}: Started processing ({chunk_size} tokens)")
    
    def end_chunk(self, chunk_id: str, entities: int = None, relations: int = None):
        """Mark the end of chunk processing"""
        if not hasattr(self, '_current_chunk') or chunk_id not in self._current_chunk:
            logger.warning(f"📊 Chunk {chunk_id}: No start time found")
            return
        
        chunk_start = self._current_chunk[chunk_id]
        end_time = time.time()
        processing_time = end_time - chunk_start["start_time"]
        
        chunk_stats = {
            "chunk_id": chunk_id,
            "processing_time": processing_time,
            "chunk_size": chunk_start.get("chunk_size"),
            "entities_extracted": entities,
            "relations_extracted": relations,
            "memory_start": chunk_start["start_memory"],
            "memory_end": self._get_memory_usage(),
            "timestamp": datetime.now().isoformat()
        }
        
        self.chunk_times.append(chunk_stats)
        self.processing_stats["chunks_processed"] += 1
        
        # Calculate averages
        total_time = sum(c["processing_time"] for c in self.chunk_times)
        self.processing_stats["total_processing_time"] = total_time
        self.processing_stats["avg_chunk_time"] = total_time / len(self.chunk_times)
        
        # Log performance info
        logger.info(f"📊 Chunk {chunk_id}: Completed in {processing_time:.1f}s")
        if entities is not None:
            logger.info(f"📊 Chunk {chunk_id}: Extracted {entities} entities, {relations} relations")
        
        # Check for performance issues
        if processing_time > 300:  # 5 minutes
            logger.warning(f"⚠️ Chunk {chunk_id}: Slow processing ({processing_time:.1f}s)")
        
        # Clean up
        del self._current_chunk[chunk_id]
    
    def end_processing(self):
        """Mark the end of document processing"""
        if self.start_time:
            total_time = time.time() - self.start_time
            self.processing_stats["end_time"] = datetime.now().isoformat()
            self.processing_stats["total_document_time"] = total_time
            
            # Final summary
            chunks_processed = self.processing_stats["chunks_processed"]
            avg_time = self.processing_stats.get("avg_chunk_time", 0)
            
            logger.info(f"📊 Processing Complete: {chunks_processed} chunks in {total_time:.1f}s")
            logger.info(f"📊 Average chunk time: {avg_time:.1f}s")
            
            # Save to log file if configured
            if self.log_file:
                self._save_to_log_file()
    
    def get_performance_summary(self) -> Dict:
        """Get current performance statistics"""
        return {
            "processing_stats": self.processing_stats,
            "chunk_times": self.chunk_times,
            "gpu_info": self._get_gpu_info()
        }
    
    def _get_memory_usage(self) -> Dict:
        """Get current memory usage"""
        process = psutil.Process()
        return {
            "rss_mb": process.memory_info().rss / 1024 / 1024,
            "vms_mb": process.memory_info().vms / 1024 / 1024,
            "cpu_percent": process.cpu_percent()
        }
    
    def _get_gpu_info(self) -> Dict:
        """Get GPU information using nvidia-smi"""
        try:
            result = subprocess.run([
                "nvidia-smi", 
                "--query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits"
            ], capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                values = result.stdout.strip().split(', ')
                return {
                    "memory_used_mb": int(values[0]),
                    "memory_total_mb": int(values[1]),
                    "gpu_utilization": int(values[2]),
                    "temperature": int(values[3])
                }
        except Exception as e:
            logger.debug(f"Could not get GPU info: {e}")
        
        return {"error": "GPU info not available"}
    
    def _save_to_log_file(self):
        """Save performance data to log file"""
        try:
            performance_data = {
                "timestamp": datetime.now().isoformat(),
                "summary": self.processing_stats,
                "chunk_details": self.chunk_times
            }
            
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(performance_data, indent=2) + "\n\n")
            
            logger.info(f"📊 Performance data saved to {self.log_file}")
        except Exception as e:
            logger.error(f"Failed to save performance data: {e}")

# Global performance monitor instance
_monitor = None

def get_monitor() -> RFPPerformanceMonitor:
    """Get the global performance monitor instance"""
    global _monitor
    if _monitor is None:
        log_file = "logs/performance_monitor.jsonl"
        _monitor = RFPPerformanceMonitor(log_file)
    return _monitor

def start_processing(document_name: str, total_chunks: int = None):
    """Convenience function to start processing monitoring"""
    get_monitor().start_processing(document_name, total_chunks)

def start_chunk(chunk_id: str, chunk_size: int = None):
    """Convenience function to start chunk monitoring"""
    get_monitor().start_chunk(chunk_id, chunk_size)

def end_chunk(chunk_id: str, entities: int = None, relations: int = None):
    """Convenience function to end chunk monitoring"""
    get_monitor().end_chunk(chunk_id, entities, relations)

def end_processing():
    """Convenience function to end processing monitoring"""
    get_monitor().end_processing()