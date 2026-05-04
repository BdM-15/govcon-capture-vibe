import asyncio

from src.server import processing_callback


class _Settings:
    def __init__(self, *, batch_timeout_seconds=5, enable_post_processing=False, workspace="demo"):
        self.batch_timeout_seconds = batch_timeout_seconds
        self.enable_post_processing = enable_post_processing
        self.workspace = workspace


def test_register_request_start_and_end_updates_stats(monkeypatch) -> None:
    monkeypatch.setattr(processing_callback, "get_settings", lambda: _Settings())
    callback = processing_callback.GovConProcessingCallback()

    asyncio.run(callback.register_request_start("demo.pdf"))
    stats = asyncio.run(callback.get_stats())
    assert stats["pending_uploads"] == 1
    assert stats["enhancement_pending"] is True

    asyncio.run(callback.register_request_end("demo.pdf"))
    stats = asyncio.run(callback.get_stats())
    assert stats["pending_uploads"] == 0


def test_check_batch_complete_resets_state_when_post_processing_disabled(monkeypatch) -> None:
    monkeypatch.setattr(processing_callback, "get_settings", lambda: _Settings(enable_post_processing=False))
    callback = processing_callback.GovConProcessingCallback()
    callback.completed_docs.add("doc-1")
    callback.enhancement_pending = True

    asyncio.run(callback._check_batch_complete())

    stats = asyncio.run(callback.get_stats())
    assert stats["completed"] == 0
    assert stats["enhancement_pending"] is False
    assert stats["enhancement_running"] is False


def test_schedule_batch_check_replaces_existing_timer(monkeypatch) -> None:
    monkeypatch.setattr(processing_callback, "get_settings", lambda: _Settings())
    callback = processing_callback.GovConProcessingCallback()
    scheduled = []

    class _Timer:
        def __init__(self):
            self.cancelled = False

        def cancel(self):
            self.cancelled = True

    class _Loop:
        def call_later(self, delay, fn):
            timer = _Timer()
            scheduled.append((delay, fn, timer))
            return timer

    monkeypatch.setattr(processing_callback.asyncio, "get_event_loop", lambda: _Loop())

    callback._schedule_batch_check()
    first_timer = callback._batch_timer
    callback._schedule_batch_check()

    assert len(scheduled) == 2
    assert first_timer.cancelled is True
    assert scheduled[0][0] == 5