import logging

from src.utils.logging_config import ConsoleFilter, ProcessingFilter, ServerFilter


def _record(name: str, level: int = logging.INFO, message: str = "hello"):
    return logging.LogRecord(name, level, __file__, 1, message, (), None)


def test_console_filter_allows_expected_and_blocks_access() -> None:
    filt = ConsoleFilter()

    assert filt.filter(_record("src.raganything_server")) is True
    assert filt.filter(_record("src.inference.semantic_post_processor")) is True
    assert filt.filter(_record("uvicorn.access")) is False
    assert filt.filter(_record("other.logger")) is False
    assert filt.filter(_record("other.logger", level=logging.ERROR)) is True


def test_processing_filter_matches_logger_or_keyword() -> None:
    filt = ProcessingFilter()

    assert filt.filter(_record("raganything.worker")) is True
    assert filt.filter(_record("other.logger", message="Processing done")) is True
    assert filt.filter(_record("other.logger", message="boring")) is False


def test_server_filter_excludes_processing_loggers() -> None:
    filt = ServerFilter()

    assert filt.filter(_record("lightrag.llm.client")) is False
    assert filt.filter(_record("raganything.worker")) is False
    assert filt.filter(_record("src.raganything_server")) is True