"""Environment defaults required by LightRAG cross-provider role validation."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def apply_cross_provider_role_env_defaults(environ: dict[str, str] | None = None) -> None:
    """Delegate to repo-root bootstrap (safe before/after src is on sys.path)."""
    root = Path(__file__).resolve().parents[2]
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    from theseus_bootstrap_env import apply_theseus_env_defaults

    apply_theseus_env_defaults(environ)