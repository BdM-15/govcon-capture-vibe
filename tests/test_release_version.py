"""Release version alignment tests for Theseus packaging and README."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


def test_pyproject_version_is_1_9_1() -> None:
    with open("pyproject.toml", "rb") as file:
        pyproject = tomllib.load(file)

    assert pyproject["project"]["version"] == "1.9.1"


def test_readme_badge_and_footer_reference_1_9_1() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert re.search(r"badge/version-1\.9\.1", readme)
    assert re.search(r"\*\*Version\*\*:\s*1\.9\.1", readme)