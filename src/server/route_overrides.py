"""Compatibility shim for legacy imports of ingestion route overrides."""

from src.server.routes import register_custom_ingestion_routes

__all__ = ["register_custom_ingestion_routes"]