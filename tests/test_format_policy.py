"""CI guardrail: assert tuple-mode vestiges are permanently absent.

Phase 2.5 (issue #124) deleted all tuple-mode compatibility code.
These tests prevent accidental re-introduction:
  - ENTITY_EXTRACTION_USE_JSON must NOT appear in .env
  - govcon_lightrag_native.txt must NOT exist at its original path
  - output_sanitizer.py must NOT exist
    - entity_extraction_use_json must be hardcoded True in native_lightrag_runtime.py
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

_ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# 1. .env must not contain ENTITY_EXTRACTION_USE_JSON
# ---------------------------------------------------------------------------

def test_env_no_tuple_flag():
    env_path = _ROOT / ".env"
    if not env_path.exists():
        return  # no .env in CI — skip gracefully
    content = env_path.read_text(encoding="utf-8")
    # Match only actual key assignments, not comments
    assigned = re.search(r"^\s*ENTITY_EXTRACTION_USE_JSON\s*=", content, re.MULTILINE)
    assert not assigned, (
        ".env still contains an ENTITY_EXTRACTION_USE_JSON assignment — tuple-mode flag must "
        "be removed. See Phase 2.5 (issue #124)."
    )


# ---------------------------------------------------------------------------
# 2. Tuple extraction prompt must not exist at its original location
# ---------------------------------------------------------------------------

def test_tuple_prompt_file_absent():
    stale_path = _ROOT / "prompts" / "extraction" / "govcon_lightrag_native.txt"
    assert not stale_path.exists(), (
        f"{stale_path} still exists — tuple-mode extraction prompt must be deleted. "
        "The archived copy lives in docs/archive/. See Phase 2.5 (issue #124)."
    )


# ---------------------------------------------------------------------------
# 3. output_sanitizer.py must not exist
# ---------------------------------------------------------------------------

def test_output_sanitizer_absent():
    stale_path = _ROOT / "src" / "extraction" / "output_sanitizer.py"
    assert not stale_path.exists(), (
        f"{stale_path} still exists — tuple-mode output sanitizer must be deleted. "
        "See Phase 2.5 (issue #124)."
    )


# ---------------------------------------------------------------------------
# 4. native_lightrag_runtime.py must hardcode entity_extraction_use_json=True
# ---------------------------------------------------------------------------

def test_entity_extraction_use_json_hardcoded_true():
    """Parse native_lightrag_runtime.py AST to confirm the kwarg is True, not a variable."""
    init_path = _ROOT / "src" / "server" / "native_lightrag_runtime.py"
    source = init_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(init_path))

    found_value: bool | None = None

    for node in ast.walk(tree):
        # Look for dict literals containing "entity_extraction_use_json"
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if not (isinstance(key, ast.Constant) and key.value == "entity_extraction_use_json"):
                continue
            if isinstance(value, ast.Constant) and value.value is True:
                found_value = True
            elif isinstance(value, ast.Constant) and value.value is False:
                found_value = False
            else:
                found_value = None  # variable reference — treat as failure

    assert found_value is True, (
        "native_lightrag_runtime.py: entity_extraction_use_json must be hardcoded True. "
        "Found: %r. See Phase 2.5 (issue #124)." % found_value
    )


# ---------------------------------------------------------------------------
# 5. Tuple prompt keys must not be registered in govcon_prompt.py
# ---------------------------------------------------------------------------

# Patterns that must NOT appear as active dict-key assignments in govcon_prompt.py.
# Uses word-boundary anchors so that json-variant keys (entity_extraction_json_*)
# do not match. Each pattern looks for  GOVCON_PROMPTS["<key>"]  or  PROMPTS["<key>"].
_BANNED_TUPLE_KEY_PATTERNS = [
    r'GOVCON_PROMPTS\["entity_extraction_system_prompt"\]',
    r'GOVCON_PROMPTS\["entity_extraction_user_prompt"\]',
    r'GOVCON_PROMPTS\["entity_continue_extraction_user_prompt"\]',
    r'GOVCON_PROMPTS\["DEFAULT_TUPLE_DELIMITER"\]',
    r'GOVCON_PROMPTS\["DEFAULT_COMPLETION_DELIMITER"\]',
]


def test_tuple_prompt_keys_absent():
    prompt_path = _ROOT / "prompts" / "govcon_prompt.py"
    source = prompt_path.read_text(encoding="utf-8")
    found = [p for p in _BANNED_TUPLE_KEY_PATTERNS if re.search(p, source)]
    assert not found, (
        f"govcon_prompt.py still assigns tuple-mode keys matching: {found}. "
        "See Phase 2.5 (issue #124)."
    )
