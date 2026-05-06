from src.skills.text_normalization import normalize_skill_text


def test_normalize_skill_text_repairs_common_mojibake_and_unicode_punctuation() -> None:
    raw = "Bad â€” dash, â€™quoteâ€™, ellipsisâ€¦, arrowâ†’, nbspÂ test, bullet ·, curly “ok”."

    normalized = normalize_skill_text(raw)

    assert normalized == 'Bad - dash, \'quote\', ellipsis..., arrow->, nbsp test, bullet -, curly "ok".'