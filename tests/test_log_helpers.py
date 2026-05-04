from src.utils.log_helpers import get_log_summary, log_graceful_failure


class _Logger:
    def __init__(self):
        self.messages = []

    def warning(self, message):
        self.messages.append(message)


def test_log_graceful_failure_formats_with_and_without_context() -> None:
    logger = _Logger()

    log_graceful_failure(logger, "Table extraction", RuntimeError("boom"), "chunk-1")
    log_graceful_failure(logger, "Inference", RuntimeError("bad"))

    assert logger.messages[0] == "⚠️ Table extraction failed (chunk-1): boom - continuing with degraded result"
    assert logger.messages[1] == "⚠️ Inference failed: bad - continuing with degraded result"


def test_get_log_summary_handles_missing_and_existing_logs(tmp_path) -> None:
    missing = get_log_summary(str(tmp_path / "nope"))
    assert missing == {"error": "Log directory does not exist"}

    (tmp_path / "server.log").write_text("hello", encoding="utf-8")
    (tmp_path / "errors.log.1").write_text("x", encoding="utf-8")

    summary = get_log_summary(str(tmp_path))

    assert summary["total_files"] == 2
    assert [file["name"] for file in summary["files"]] == ["errors.log.1", "server.log"]