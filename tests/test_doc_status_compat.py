import asyncio

from lightrag.base import DocStatus

from src.server import doc_status_compat


class _DocStatusStore:
    def __init__(self):
        self.upsert_calls = []

    async def upsert(self, data):
        self.upsert_calls.append(data)
        return data

    async def get_by_id(self, doc_id):
        return {
            "status": "processed",
            "multimodal_content": ["drop"],
            "file_path": "demo.pdf",
        }

    async def get_docs_paginated(self, *args, **kwargs):
        return ([
            (
                "doc-1",
                {
                    "status": "processed",
                    "scheme_name": "drop",
                    "file_path": "demo.pdf",
                },
            )
        ], 1)


class _LightRAG:
    def __init__(self):
        self.doc_status = _DocStatusStore()


def test_normalize_doc_status_maps_raganything_values() -> None:
    assert doc_status_compat.normalize_doc_status("handling", "doc-1") == DocStatus.PROCESSING.value
    assert doc_status_compat.normalize_doc_status("parsing", "doc-1") == DocStatus.PROCESSING.value
    assert doc_status_compat.normalize_doc_status("ready", "doc-1") == DocStatus.PENDING.value
    assert doc_status_compat.normalize_doc_status("processed", "doc-1") == DocStatus.PROCESSED.value


def test_apply_doc_status_compatibility_shim_filters_and_localizes(monkeypatch) -> None:
    monkeypatch.setattr(doc_status_compat, "to_local_iso", lambda value: f"local:{value}")
    lightrag = _LightRAG()

    doc_status_compat.apply_doc_status_compatibility_shim(lightrag)

    asyncio.run(
        lightrag.doc_status.upsert(
            {
                "doc-1": {
                    "status": "handling",
                    "multimodal_processed": True,
                    "scheme_name": "x",
                    "created_at": "utc1",
                    "updated_at": "utc2",
                }
            }
        )
    )

    payload = lightrag.doc_status.upsert_calls[0]["doc-1"]
    assert payload["status"] == DocStatus.PROCESSING.value
    assert payload["created_at"] == "local:utc1"
    assert payload["updated_at"] == "local:utc2"
    assert "multimodal_processed" not in payload
    assert "scheme_name" not in payload


def test_apply_doc_status_compatibility_shim_filters_read_paths() -> None:
    lightrag = _LightRAG()
    doc_status_compat.apply_doc_status_compatibility_shim(lightrag)

    doc = asyncio.run(lightrag.doc_status.get_by_id("doc-1"))
    page = asyncio.run(lightrag.doc_status.get_docs_paginated())

    assert doc == {"status": "processed", "file_path": "demo.pdf"}
    assert page == (([("doc-1", {"status": "processed", "file_path": "demo.pdf"})], 1),)


def test_apply_doc_status_compatibility_shim_is_idempotent() -> None:
    lightrag = _LightRAG()

    doc_status_compat.apply_doc_status_compatibility_shim(lightrag)
    first_upsert = lightrag.doc_status.upsert
    doc_status_compat.apply_doc_status_compatibility_shim(lightrag)

    assert lightrag.doc_status.upsert is first_upsert