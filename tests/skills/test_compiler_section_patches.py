"""Tests for compiler brief section-patch merge (no full rewrite)."""

from __future__ import annotations

from src.skills.research_harness import (
    apply_section_patches_to_brief,
    brief_structure_preserved,
    parse_compiler_section_patches,
)


def _sample_brief() -> str:
    return "\n".join(
        [
            "# Mission Readiness Frame Brief (chain compiler)",
            "",
            "## 1. Mission Readiness Frame",
            "",
            "Short outcome.",
            "",
            "## 5. Evaluation Cross-Walk Table (One Row per Material Factor/Subfactor)",
            "",
            "| Factor | Readiness | Proof |",
            "| --- | --- | --- |",
            "| Factor A | link a | proof a |",
            "| Factor B | link b | proof b |",
            "",
            "## Executive Synthesis",
            "",
            "Thin synthesis.",
            "",
        ]
    )


def test_apply_section_patches_replaces_only_named_sections() -> None:
    original = _sample_brief()
    patches = [
        {
            "heading": "## 1. Mission Readiness Frame",
            "content": "Expanded outcome with cited rationale [1] and program context.",
        }
    ]
    merged = apply_section_patches_to_brief(original, patches)
    assert "Expanded outcome with cited rationale" in merged
    assert "Short outcome." not in merged
    assert "| Factor A | link a | proof a |" in merged
    assert "Thin synthesis." in merged


def test_brief_structure_preserved_rejects_shrinking_rewrite() -> None:
    original = _sample_brief()
    rewrite = "# Mission Readiness Frame Brief\n\n## 1. Mission Readiness Frame\n\nTiny."
    ok, reason = brief_structure_preserved(original, rewrite)
    assert not ok
    assert "headings changed" in reason or "shrank" in reason


def test_brief_structure_preserved_accepts_targeted_patch() -> None:
    original = _sample_brief()
    merged = apply_section_patches_to_brief(
        original,
        [
            {
                "heading": "1. Mission Readiness Frame",
                "content": "Much longer expanded outcome " + ("detail " * 40),
            }
        ],
    )
    ok, reason = brief_structure_preserved(original, merged)
    assert ok, reason


def test_parse_compiler_section_patches_from_fenced_json() -> None:
    content = (
        '```json\n{"section_patches":[{"heading":"## Executive Synthesis","content":"x"}]}\n```'
    )
    patches = parse_compiler_section_patches(content)
    assert len(patches) == 1
    assert patches[0]["heading"] == "## Executive Synthesis"