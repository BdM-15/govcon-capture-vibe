import asyncio

from src.server import document_processing


class _DocStatus:
    def __init__(self, existing=None):
        self.existing = existing
        self.upserts: list[dict] = []

    async def get_by_id(self, doc_id):
        return self.existing

    async def upsert(self, payload):
        self.upserts.append(payload)


class _LightRAG:
    def __init__(self, doc_status):
        self.doc_status = doc_status


class _Rag:
    def __init__(self, doc_status):
        self.lightrag = _LightRAG(doc_status)


def test_filter_discarded_content_blocks_reports_removed_count() -> None:
    filtered, discarded = document_processing.filter_discarded_content_blocks(
        [
            {"type": "text", "text": "keep"},
            {"type": "header", "text": "drop"},
            {"type": "table", "text": "keep too"},
        ]
    )

    assert discarded == 1
    assert [block["type"] for block in filtered] == ["text", "table"]


def test_summarize_processed_content_prefers_text_block() -> None:
    summary, content_length = document_processing.summarize_processed_content(
        "demo.pdf",
        [{"type": "text", "text": "hello world"}, {"type": "table", "text": "tab"}],
    )

    assert summary == "hello world"
    assert content_length == len("hello world") + len("tab")


def test_summarize_processed_content_falls_back_to_type_breakdown() -> None:
    summary, content_length = document_processing.summarize_processed_content(
        "demo.pdf",
        [{"type": "table", "text": "x"}, {"type": "image"}],
    )

    assert summary == "[NON-TEXT] demo.pdf (1 image, 1 table)"
    assert content_length == 1


def test_record_failed_doc_writes_failed_status(monkeypatch) -> None:
    monkeypatch.setattr(document_processing, "now_local_iso", lambda: "now")
    doc_status = _DocStatus()
    rag = _Rag(doc_status)

    asyncio.run(
        document_processing.record_failed_doc(
            rag,
            "C:/tmp/demo.pdf",
            "demo.pdf",
            None,
            "boom",
        )
    )

    payload = next(iter(doc_status.upserts[0].values()))
    assert payload["status"] == "failed"
    assert payload["content_summary"] == "[FAILED] demo.pdf"
    assert payload["error_msg"] == "boom"


def test_ensure_doc_status_processed_backfills_missing_entry(monkeypatch) -> None:
    monkeypatch.setattr(document_processing, "now_local_iso", lambda: "now")
    doc_status = _DocStatus(existing=None)
    rag = _Rag(doc_status)

    asyncio.run(
        document_processing.ensure_doc_status_processed(
            rag,
            "demo.pdf",
            "doc-1",
            [{"type": "table", "text": "x"}],
            1.234,
        )
    )

    payload = doc_status.upserts[0]["doc-1"]
    assert payload["status"] == "processed"
    assert payload["content_summary"] == "[NON-TEXT] demo.pdf (1 table)"
    assert payload["metadata"]["duration_seconds"] == 1.23


def test_ensure_doc_status_processed_skips_existing_entry() -> None:
    doc_status = _DocStatus(existing={"status": "processed"})
    rag = _Rag(doc_status)

    asyncio.run(
        document_processing.ensure_doc_status_processed(
            rag,
            "demo.pdf",
            "doc-1",
            [{"type": "text", "text": "hi"}],
            1.0,
        )
    )

    assert doc_status.upserts == []