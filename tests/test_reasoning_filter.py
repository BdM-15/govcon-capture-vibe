from src.server.chat_routes import ThinkStripper, strip_think


def test_strip_think_removes_complete_and_unclosed_blocks() -> None:
    assert strip_think("<think>scratch</think>Answer") == "Answer"
    assert strip_think("Lead <think>scratch</think> Answer") == "Lead Answer"
    assert strip_think("Answer <think>unfinished") == "Answer "


def test_strip_think_ignores_plain_text() -> None:
    assert strip_think("Answer") == "Answer"
    assert strip_think("") == ""


def test_think_stripper_handles_split_tags() -> None:
    stripper = ThinkStripper()
    chunks = ["Hel", "lo <thi", "nk>hidden", "</think> wor", "ld"]
    output = "".join(stripper.feed(chunk) for chunk in chunks) + stripper.flush()

    assert output == "Hello world"


def test_think_stripper_discards_unclosed_reasoning() -> None:
    stripper = ThinkStripper()
    output = stripper.feed("Visible <think>secret") + stripper.flush()

    assert output == "Visible "
