import asyncio
from types import SimpleNamespace

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


class _CallbackManager:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def dispatch(self, event_name, **payload):
        self.events.append((event_name, payload))


class _ProcessingRag(_Rag):
    def __init__(self, content_list):
        super().__init__(_DocStatus(existing={"status": "processed"}))
        self.content_list = content_list
        self.callback_manager = _CallbackManager()
        self.inserted_content: list[dict] | None = None

    async def parse_document(self, **kwargs):
        return self.content_list, "doc-1"

    async def insert_content_list(self, *, content_list, file_path, doc_id):
        self.inserted_content = content_list


class _ProcessingCallback:
    async def get_stats(self):
        return {"processing": 0, "completed": 1}


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


def test_rebalance_modal_content_blocks_converts_textual_table_to_text() -> None:
    rebalanced, stats = document_processing.rebalance_modal_content_blocks(
        [
            {
                "type": "table",
                "table_caption": ["Volume page limits"],
                "table_body": "<table><tr><td>Volume</td><td>Page Limits</td></tr><tr><td>II</td><td>140</td></tr></table>",
                "page_idx": 1,
            }
        ]
    )

    assert stats.tables_converted == 1
    assert stats.multimodal_kept == 0
    assert rebalanced[0]["type"] == "text"
    assert rebalanced[0]["original_type"] == "table"
    assert rebalanced[0]["modal_rebalanced"] is True
    assert "Caption: Volume page limits" in rebalanced[0]["text"]
    assert "Volume | Page Limits" in rebalanced[0]["text"]
    assert "II | 140" in rebalanced[0]["text"]


def test_rebalance_modal_content_blocks_keeps_image_only_table_modal() -> None:
    rebalanced, stats = document_processing.rebalance_modal_content_blocks(
        [{"type": "table", "img_path": "table.jpg"}]
    )

    assert stats.tables_converted == 0
    assert stats.multimodal_kept == 1
    assert rebalanced == [{"type": "table", "img_path": "table.jpg"}]


def test_rebalance_modal_content_blocks_converts_lists_and_discards_seals() -> None:
    rebalanced, stats = document_processing.rebalance_modal_content_blocks(
        [
            {"type": "list", "list_items": ["7.1 Utilities", "7.1.1 Electrical"]},
            {"type": "seal", "text": "H L M"},
        ]
    )

    assert stats.lists_converted == 1
    assert stats.seals_discarded == 1
    assert len(rebalanced) == 1
    assert rebalanced[0]["type"] == "text"
    assert "7.1 Utilities" in rebalanced[0]["text"]


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


def test_process_document_rebalances_content_before_insert(monkeypatch) -> None:
    monkeypatch.setattr(
        document_processing,
        "get_settings",
        lambda: SimpleNamespace(mineru_backend="pipeline", llm_timeout=180),
    )
    rag = _ProcessingRag(
        [
            {"type": "text", "text": "Section L instructions"},
            {"type": "table", "table_body": "<table><tr><td>Volume</td><td>Pages</td></tr></table>"},
            {"type": "seal", "text": "H L M"},
        ]
    )

    result = asyncio.run(
        document_processing.process_document_with_semantic_inference(
            "C:/tmp/demo.pdf",
            "demo.pdf",
            rag,
            llm_func=None,
            callback=_ProcessingCallback(),
        )
    )

    assert result["status"] == "success"
    assert rag.inserted_content is not None
    assert [block["type"] for block in rag.inserted_content] == ["text", "text"]
    assert rag.inserted_content[1]["original_type"] == "table"
    assert all(block.get("type") != "seal" for block in rag.inserted_content)


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