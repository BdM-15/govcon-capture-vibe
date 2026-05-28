import asyncio

from src.server import document_processing


class _DocStatus:
    def __init__(self):
        self.upserts: list[dict] = []

    async def upsert(self, payload):
        self.upserts.append(payload)


class _LightRAG:
    def __init__(self, doc_status):
        self.doc_status = doc_status


class _Rag:
    def __init__(self, doc_status):
        self.lightrag = _LightRAG(doc_status)


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