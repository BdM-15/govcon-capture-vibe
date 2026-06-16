"""CLI: ensure Theseus server matches workspace readiness gate code."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.skills.ensure_theseus_server import main

if __name__ == "__main__":
    raise SystemExit(main())