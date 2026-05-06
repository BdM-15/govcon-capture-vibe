"""Small text cleanup helpers for skill user-facing output."""

from __future__ import annotations


_MOJIBAKE_REPLACEMENTS = {
    "â€”": "-",
    "â€“": "-",
    "â€˜": "'",
    "â€™": "'",
    "â€œ": '"',
    "â€": '"',
    "â€¦": "...",
    "â†’": "->",
    "Â·": "-",
    "Â ": " ",
    "Â": "",
}

_UNICODE_PUNCT_TRANSLATION = str.maketrans(
    {
        "—": "-",
        "–": "-",
        "−": "-",
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "…": "...",
        "→": "->",
        "•": "-",
        "·": "-",
        "\u00a0": " ",
    }
)


def normalize_skill_text(text: str) -> str:
    """Make skill response text safer for Windows/UI rendering.

    Keep substance. Only collapse punctuation variants that commonly show up as
    mojibake in persisted skill output.
    """
    if not isinstance(text, str) or not text:
        return text
    normalized = text
    for bad, good in _MOJIBAKE_REPLACEMENTS.items():
        normalized = normalized.replace(bad, good)
    normalized = normalized.translate(_UNICODE_PUNCT_TRANSLATION)
    return normalized