"""
Utilities Module

Contains utility functions and configurations:
- Logging configuration with structured output
- Performance monitoring and metrics
- System utilities and helpers

Provides supporting infrastructure for the ontology-based RAG system.
"""

from .logging_config import setup_logging
from .performance_monitor import get_monitor

__all__ = [
    'setup_logging',
    'get_monitor'
]