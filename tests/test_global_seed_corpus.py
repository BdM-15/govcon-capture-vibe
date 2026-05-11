from pathlib import Path

from src.core.global_store import GlobalStore

_ROOT = Path(__file__).resolve().parents[1]
_GLOBAL_ROOT = _ROOT / "global"

_EXPECTED_SEEDS = {
    "llm-wiki/shipley/shipley-capture-gate-cheat-sheet.md": {"shipley", "capture", "starter"},
    "llm-wiki/regulations/far-15-and-16-quick-reference.md": {"far", "regulations", "starter"},
    "llm-wiki/templates/pink-team-review-template.md": {"template", "color-team", "pink-team"},
    "llm-wiki/templates/red-team-readiness-template.md": {"template", "color-team", "red-team"},
    "intel/patterns/capture-signal-patterns.md": {"pattern", "capture", "signal"},
    "intel/patterns/customer-intel-refresh-patterns.md": {"pattern", "intel", "signal"},
    "intel/patterns/color-team-signal-patterns.md": {"pattern", "color-team", "signal"},
    "intel/patterns/proposal-recovery-patterns.md": {"pattern", "proposal", "signal"},
}


def _store() -> GlobalStore:
    return GlobalStore(root=_GLOBAL_ROOT)


def test_day_one_seed_corpus_exists() -> None:
    entries = {entry["path"]: entry for entry in _store().list()}

    missing = sorted(set(_EXPECTED_SEEDS) - set(entries))
    assert not missing, f"missing Ariadne starter corpus files: {missing}"


def test_day_one_seed_corpus_uses_obsidian_shape() -> None:
    store = _store()
    entries = {entry["path"]: entry for entry in store.list()}

    for path, required_tags in _EXPECTED_SEEDS.items():
        entry = entries[path]
        frontmatter = entry["frontmatter"]
        text = store.read(path)

        assert frontmatter.get("title"), f"{path} missing title frontmatter"
        assert frontmatter.get("summary"), f"{path} missing summary frontmatter"
        assert frontmatter.get("status") == "evergreen", f"{path} must be evergreen"
        assert frontmatter.get("source") == "ariadne-seed", f"{path} must record seed provenance"
        assert required_tags.issubset(set(frontmatter.get("tags") or [])), (
            f"{path} missing expected tags {sorted(required_tags)}"
        )
        assert text.startswith("---\n"), f"{path} missing YAML frontmatter"
        assert "[[" in text, f"{path} should contain at least one wikilink"