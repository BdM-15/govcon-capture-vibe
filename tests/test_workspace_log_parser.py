from src.server.workspace_log_parser import (
    classify_workspace_log_event,
    parse_workspace_log_lines,
)


def test_classify_workspace_log_event_detects_processing_phase() -> None:
    result = classify_workspace_log_event(
        "lightrag.operate",
        "Phase 4 · Relationship Inference",
        "INFO",
    )

    assert result == {
        "category": "processing",
        "kind": "phase",
        "phase": {"index": 4, "label": "Relationship Inference"},
    }


def test_classify_workspace_log_event_detects_query_logs() -> None:
    result = classify_workspace_log_event(
        "lightrag.query",
        "Hybrid query retrieved 8 entities",
        "INFO",
    )

    assert result["category"] == "query"
    assert result["kind"] == "info"
    assert result["phase"] is None


def test_parse_workspace_log_lines_folds_continuations_and_blank_lines() -> None:
    lines = [
        "2026-05-04 09:00:00 | INFO | lightrag | Content Information:",
        "table rows: 12",
        "",
        "2026-05-04 09:00:01 | WARNING | src.server.routes | Queue depth rising",
    ]

    parsed = parse_workspace_log_lines(lines, start_id=7)

    assert parsed[0]["id"] == 7
    assert parsed[0]["message"] == "Content Information:\ntable rows: 12\n"
    assert parsed[0]["category"] == "processing"
    assert parsed[1]["id"] == 8
    assert parsed[1]["kind"] == "warning"
    assert parsed[1]["category"] == "processing"