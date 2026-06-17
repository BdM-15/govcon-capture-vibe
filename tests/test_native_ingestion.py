import asyncio
from pathlib import Path

import pytest

from src.core.config import reset_settings
from src.server.native_ingestion import (
    process_document_with_native_ingestion,
    resolve_govcon_parser_directives,
)


class _DocStatus:
    def __init__(self, records: dict | None = None):
        self._data = records or {}
        self.upserts: list[dict] = []
        self.deletes: list[list[str]] = []
        self.index_done_calls = 0

    async def upsert(self, payload: dict) -> None:
        self.upserts.append(payload)
        self._data.update(payload)

    async def delete(self, doc_ids: list[str]) -> None:
        self.deletes.append(doc_ids)
        for doc_id in doc_ids:
            self._data.pop(doc_id, None)

    async def index_done_callback(self) -> None:
        self.index_done_calls += 1

    async def get_docs_by_track_id(self, track_id: str) -> dict:
        return {
            doc_id: record
            for doc_id, record in self._data.items()
            if record.get("track_id") == track_id
        }


class _NativeLightRAG:
    def __init__(
        self,
        *,
        workspace: str = "alpha",
        fail_process: bool = False,
        doc_status: _DocStatus | None = None,
        process_status_records: dict | None = None,
    ):
        self.workspace = workspace
        self.fail_process = fail_process
        self.doc_status = doc_status or _DocStatus()
        self.process_status_records = process_status_records or {}
        self.enqueues: list[dict] = []
        self.process_calls = 0

    async def apipeline_enqueue_documents(self, *args, **kwargs):
        self.enqueues.append({"args": args, "kwargs": kwargs})
        return kwargs.get("track_id") or "track-1"

    async def apipeline_process_enqueue_documents(self):
        self.process_calls += 1
        self.doc_status._data.update(self.process_status_records)
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
    assert enqueue["kwargs"]["process_options"] in {"ite", "iteP"}
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
    monkeypatch.setenv(
        "LIGHTRAG_PARSER",
        "pdf:mineru-iteP,docx:mineru-iteP,xlsx:mineru-iteP",
    )
    reset_settings()

    assert resolve_govcon_parser_directives("attachment.docx") == ("mineru", "ieP")
    assert resolve_govcon_parser_directives("pricing.xlsx") == ("mineru", "ieP")
    assert resolve_govcon_parser_directives("diagram.pdf") == ("mineru", "iteP")


def test_native_ingestion_converts_office_to_pdf_before_mineru_enqueue(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "sow.docx"
    source.write_bytes(b"fake-docx")
    pdf_path = tmp_path / "cache" / "deadbeef" / "sow.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"%PDF")

    monkeypatch.setenv("WORKSPACE", "alpha")
    monkeypatch.setenv("WORKING_DIR", str(tmp_path / "rag_storage"))
    monkeypatch.setenv(
        "LIGHTRAG_PARSER",
        "pdf:mineru-iteP,docx:mineru-iteP,xlsx:mineru-iteP",
    )
    reset_settings()
    monkeypatch.chdir(tmp_path)

    def fake_convert(path, *, cache_root, libreoffice_path, timeout_seconds):
        from src.server.office_to_pdf import OfficePdfConversion

        return OfficePdfConversion(
            enqueue_path=pdf_path,
            original_name="sow.docx",
            converted=True,
            cache_dir=pdf_path.parent,
        )

    monkeypatch.setattr(
        "src.server.native_ingestion.convert_office_to_pdf",
        fake_convert,
    )

    lightrag = _NativeLightRAG(workspace="alpha")
    asyncio.run(
        process_document_with_native_ingestion(
            str(source),
            source.name,
            _Rag(lightrag),
            llm_func=object(),
            track_id="upload-docx",
        )
    )

    staged_pdf = tmp_path / "inputs" / "alpha" / "sow.pdf"
    enqueue = lightrag.enqueues[0]
    assert enqueue["kwargs"]["file_paths"] == str(staged_pdf.resolve())
    assert staged_pdf.is_file()
    assert enqueue["kwargs"]["parse_engine"] == "mineru"
    assert enqueue["kwargs"]["process_options"] == "iteP"


def test_native_ingestion_sends_xlsx_direct_to_mineru_without_pdf_convert(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "pricing.xlsx"
    source.write_bytes(b"fake-xlsx")

    monkeypatch.setenv("WORKSPACE", "alpha")
    monkeypatch.setenv("WORKING_DIR", str(tmp_path / "rag_storage"))
    monkeypatch.setenv(
        "LIGHTRAG_PARSER",
        "pdf:mineru-iteP,docx:mineru-iteP,xlsx:mineru-iteP",
    )
    reset_settings()

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("xlsx must not use LibreOffice PDF conversion")

    monkeypatch.setattr(
        "src.server.native_ingestion.convert_office_to_pdf",
        fail_if_called,
    )

    lightrag = _NativeLightRAG(workspace="alpha")
    asyncio.run(
        process_document_with_native_ingestion(
            str(source),
            source.name,
            _Rag(lightrag),
            llm_func=object(),
            track_id="upload-xlsx",
        )
    )

    enqueue = lightrag.enqueues[0]
    assert enqueue["kwargs"]["file_paths"] == str(source)
    assert enqueue["kwargs"]["parse_engine"] == "mineru"
    assert enqueue["kwargs"]["process_options"] == "ieP"


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


def test_native_ingestion_retry_clears_failed_status_records_before_enqueue(tmp_path: Path) -> None:
    source = tmp_path / "cost.pdf"
    source.write_bytes(b"%PDF")
    doc_status = _DocStatus(
        {
            "failed-old": {
                "file_path": "cost.pdf",
                "status": "failed",
                "error_msg": "mineru failed",
            },
            "dup-old": {
                "file_path": "cost.pdf",
                "status": "failed",
                "content_summary": "[DUPLICATE:filename] Original document: failed-old",
                "metadata": {"is_duplicate": True},
            },
            "other-doc": {"file_path": "solicitation.pdf", "status": "processed"},
        }
    )
    lightrag = _NativeLightRAG(workspace="alpha", doc_status=doc_status)

    asyncio.run(
        process_document_with_native_ingestion(
            str(source),
            source.name,
            _Rag(lightrag),
            llm_func=object(),
            track_id="retry-cost",
        )
    )

    assert doc_status.deletes == [["failed-old", "dup-old"]]
    assert doc_status.index_done_calls == 1
    assert set(doc_status._data) == {"other-doc"}
    assert lightrag.enqueues[0]["kwargs"]["track_id"] == "retry-cost"


def test_native_ingestion_surfaces_failed_track_status_after_processing(tmp_path: Path) -> None:
    source = tmp_path / "cost.pdf"
    source.write_bytes(b"%PDF")
    lightrag = _NativeLightRAG(
        workspace="alpha",
        process_status_records={
            "doc-failed": {
                "file_path": "cost.pdf",
                "status": "failed",
                "track_id": "upload-cost",
                "error_msg": "All connection attempts failed",
            }
        },
    )

    with pytest.raises(RuntimeError, match="All connection attempts failed"):
        asyncio.run(
            process_document_with_native_ingestion(
                str(source),
                source.name,
                _Rag(lightrag),
                llm_func=object(),
                track_id="upload-cost",
            )
        )

    failed_payload = lightrag.doc_status.upserts[0]
    failed_doc = next(iter(failed_payload.values()))
    assert failed_doc["file_path"] == "cost.pdf"
    assert failed_doc["status"] == "failed"
    assert "All connection attempts failed" in failed_doc["error_msg"]


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