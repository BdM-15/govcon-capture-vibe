import asyncio
from pathlib import Path

import pytest

from src.server.native_ingestion import (
    process_document_with_native_ingestion,
    resolve_govcon_parser_directives,
)


class _DocStatus:
    def __init__(self):
        self.upserts: list[dict] = []

    async def upsert(self, payload: dict) -> None:
        self.upserts.append(payload)


class _NativeLightRAG:
    def __init__(self, *, workspace: str = "alpha", fail_process: bool = False):
        self.workspace = workspace
        self.fail_process = fail_process
        self.doc_status = _DocStatus()
        self.enqueues: list[dict] = []
        self.process_calls = 0

    async def apipeline_enqueue_documents(self, *args, **kwargs):
        self.enqueues.append({"args": args, "kwargs": kwargs})
        return kwargs.get("track_id") or "track-1"

    async def apipeline_process_enqueue_documents(self):
        self.process_calls += 1
        if self.fail_process:
            raise RuntimeError("parser failed")


class _Rag:
    def __init__(self, lightrag: _NativeLightRAG):
        self.lightrag = lightrag


class _NativeCallback:
    def __init__(self):
        self.completed: list[dict] = []
        self.errors: list[dict] = []

    def on_document_complete(self, **kwargs) -> None:
        self.completed.append(kwargs)

    def on_document_error(self, **kwargs) -> None:
        self.errors.append(kwargs)


def test_process_document_with_native_ingestion_enqueues_pending_parse_document(tmp_path: Path) -> None:
    source = tmp_path / "demo.pdf"
    source.write_bytes(b"%PDF")
    lightrag = _NativeLightRAG(workspace="alpha")

    result = asyncio.run(
        process_document_with_native_ingestion(
            str(source),
            source.name,
            _Rag(lightrag),
            llm_func=object(),
            track_id="upload-demo",
        )
    )

    enqueue = lightrag.enqueues[0]
    assert enqueue["args"] == ("",)
    assert enqueue["kwargs"]["file_paths"] == str(source)
    assert enqueue["kwargs"]["docs_format"] == "pending_parse"
    assert enqueue["kwargs"]["parse_engine"] == "mineru"
    assert enqueue["kwargs"]["process_options"] == "ite"
    assert enqueue["kwargs"]["track_id"] == "upload-demo"
    assert lightrag.process_calls == 1
    assert result == {
        "status": "success",
        "relationships_inferred": 0,
        "method": "native_lightrag_pipeline",
        "message": "Document queued and processed by LightRAG native pipeline.",
        "track_id": "upload-demo",
        "workspace": "alpha",
    }


def test_native_ingestion_success_notifies_batch_callback(tmp_path: Path) -> None:
    source = tmp_path / "demo.pdf"
    source.write_bytes(b"%PDF")
    lightrag = _NativeLightRAG(workspace="alpha")
    callback = _NativeCallback()

    asyncio.run(
        process_document_with_native_ingestion(
            str(source),
            source.name,
            _Rag(lightrag),
            llm_func=object(),
            track_id="upload-demo",
            callback=callback,
        )
    )

    assert len(callback.completed) == 1
    assert callback.completed[0]["file_path"] == str(source)
    assert callback.completed[0]["doc_id"].startswith("doc-")
    assert callback.completed[0]["duration_seconds"] >= 0
    assert callback.errors == []


def test_resolve_govcon_parser_directives_keeps_text_bearing_tables_in_text_chunks(monkeypatch) -> None:
    monkeypatch.setenv("LIGHTRAG_PARSER", "pdf:mineru-ite,docx:native-ite,xls*:mineru-t")

    assert resolve_govcon_parser_directives("attachment.docx") == ("native", "ie")
    assert resolve_govcon_parser_directives("pricing.xlsx") == ("mineru", "")
    assert resolve_govcon_parser_directives("diagram.pdf") == ("mineru", "ite")


def test_native_ingestion_failure_records_recoverable_failed_status(tmp_path: Path) -> None:
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"%PDF")
    lightrag = _NativeLightRAG(workspace="alpha", fail_process=True)

    with pytest.raises(RuntimeError, match="parser failed"):
        asyncio.run(
            process_document_with_native_ingestion(
                str(source),
                source.name,
                _Rag(lightrag),
                llm_func=object(),
                track_id="upload-broken",
            )
        )

    assert lightrag.enqueues
    failed_payload = lightrag.doc_status.upserts[0]
    failed_doc = next(iter(failed_payload.values()))
    assert failed_doc["file_path"] == "broken.pdf"
    assert failed_doc["status"] == "failed"
    assert failed_doc["error_msg"] == "parser failed"


def test_native_ingestion_failure_notifies_batch_callback(tmp_path: Path) -> None:
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"%PDF")
    lightrag = _NativeLightRAG(workspace="alpha", fail_process=True)
    callback = _NativeCallback()

    with pytest.raises(RuntimeError, match="parser failed"):
        asyncio.run(
            process_document_with_native_ingestion(
                str(source),
                source.name,
                _Rag(lightrag),
                llm_func=object(),
                track_id="upload-broken",
                callback=callback,
            )
        )

    assert callback.completed == []
    assert len(callback.errors) == 1
    assert callback.errors[0]["file_path"] == str(source)
    assert callback.errors[0]["doc_id"].startswith("doc-")
    assert callback.errors[0]["error"] == "parser failed"


def test_native_ingestion_uses_active_lightrag_workspace_instance(tmp_path: Path) -> None:
    source = tmp_path / "shared.pdf"
    source.write_bytes(b"%PDF")
    alpha = _NativeLightRAG(workspace="alpha")
    beta = _NativeLightRAG(workspace="beta")

    result_alpha = asyncio.run(
        process_document_with_native_ingestion(
            str(source), source.name, _Rag(alpha), llm_func=None, track_id="alpha-track"
        )
    )
    result_beta = asyncio.run(
        process_document_with_native_ingestion(
            str(source), source.name, _Rag(beta), llm_func=None, track_id="beta-track"
        )
    )

    assert result_alpha["workspace"] == "alpha"
    assert result_beta["workspace"] == "beta"
    assert alpha.enqueues[0]["kwargs"]["track_id"] == "alpha-track"
    assert beta.enqueues[0]["kwargs"]["track_id"] == "beta-track"