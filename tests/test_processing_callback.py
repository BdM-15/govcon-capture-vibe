import asyncio
from pathlib import Path
from types import SimpleNamespace

from src.inference import semantic_post_processor
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


def test_native_batch_completion_runs_post_processing_once(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(processing_callback, "get_settings", lambda: _Settings(enable_post_processing=True))
    monkeypatch.setattr(processing_callback, "global_args", SimpleNamespace(working_dir=str(tmp_path)))
    calls = []

    async def fake_enhance_knowledge_graph(**kwargs):
        calls.append(kwargs)
        return {
            "final_entity_count": 2,
            "final_relationship_count": 1,
            "vdb_relationship_count": 1,
            "entities_corrected": 0,
            "relationships_inferred": 1,
        }

    monkeypatch.setattr(semantic_post_processor, "enhance_knowledge_graph", fake_enhance_knowledge_graph)
    callback = processing_callback.GovConProcessingCallback()
    llm_func = object()
    callback.set_llm_func(llm_func)

    async def complete_batch():
        await callback.register_request_start("a.pdf")
        await callback.register_request_start("b.pdf")
        callback.on_document_complete("inputs/a.pdf", doc_id="doc-a", duration_seconds=1.0)
        await callback.register_request_end("a.pdf")
        callback.on_document_complete("inputs/b.pdf", doc_id="doc-b", duration_seconds=1.0)
        await callback.register_request_end("b.pdf")
        await callback._check_batch_complete()
        await callback._check_batch_complete()

    asyncio.run(complete_batch())

    assert len(calls) == 1
    assert calls[0]["rag_storage_path"] == str(tmp_path / "demo")
    assert calls[0]["llm_func"] is llm_func
    stats = asyncio.run(callback.get_stats())
    assert stats["completed"] == 0
    assert stats["enhancement_pending"] is False


def test_native_error_completion_unblocks_batch_post_processing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(processing_callback, "get_settings", lambda: _Settings(enable_post_processing=True))
    monkeypatch.setattr(processing_callback, "global_args", SimpleNamespace(working_dir=str(tmp_path)))
    calls = []

    async def fake_enhance_knowledge_graph(**kwargs):
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(semantic_post_processor, "enhance_knowledge_graph", fake_enhance_knowledge_graph)
    callback = processing_callback.GovConProcessingCallback()

    async def complete_failed_batch():
        await callback.register_request_start("broken.pdf")
        callback.on_document_error("inputs/broken.pdf", doc_id="doc-broken", error="parser failed")
        await callback.register_request_end("broken.pdf")
        await callback._check_batch_complete()

    asyncio.run(complete_failed_batch())

    assert len(calls) == 1
    stats = asyncio.run(callback.get_stats())
    assert stats["completed"] == 0
    assert stats["enhancement_pending"] is False


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