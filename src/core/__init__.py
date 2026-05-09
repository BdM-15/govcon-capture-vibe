"""
Core module for GovCon Capture Vibe.

Provides centralized configuration, shared utilities, and custom exceptions.
"""

from src.core.config import get_settings, reset_settings, Settings
from src.core.env import env_float, env_int
from src.core.global_store import GlobalStore
from src.core.neo4j_config import Neo4jConnectionConfig, get_neo4j_connection_config
from src.core.exceptions import (
    GovConError,
    ConfigurationError,
    LLMError,
    ExtractionError,
    InferenceError,
    StorageError,
    PromptError,
    ValidationError,
)

__all__ = [
    # Configuration
    "get_settings", 
    "reset_settings", 
    "Settings",
    "env_float",
    "env_int",
    "GlobalStore",
    "Neo4jConnectionConfig",
    "get_neo4j_connection_config",
    # Exceptions
    "GovConError",
    "ConfigurationError",
    "LLMError",
    "ExtractionError",
    "InferenceError",
    "StorageError",
    "PromptError",
    "ValidationError",
]
