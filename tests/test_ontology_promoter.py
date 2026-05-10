import asyncio
from pathlib import Path
from typing import Any

import pytest

from src.core.global_store import GlobalStore
from src.core.ontology_promoter import OntologyPromoter


def _note(body: str) -> str:
    return (
        "---\n"
        "date: 2026-05-09\n"
        "source: capture\n"
        "status: evergreen\n"
        "tags: [meta, ontology]\n"
        "---\n\n"
        f"{body}\n"
    )


class _LightRAG:
    def __init__(self) -> None:
        self.deleted: list[tuple[str, bool]] = []

    async def adelete_by_doc_id(self, doc_id: str, *, delete_llm_cache: bool = False) -> dict[str, Any]:
        self.deleted.append((doc_id, delete_llm_cache))
        return {"status": "deleted", "doc_id": doc_id}


class _Rag:
    def __init__(self) -> None:
        self.lightrag = _LightRAG()
        self.llm_model_func = "llm-func"


def test_ontology_promoter_promotes_and_ingests_note(tmp_path: Path) -> None:
    store = GlobalStore(root=tmp_path / "global")
    store.write("notes/2026-05-09-fit.md", _note("Fit score seed"))
    workspace_root = tmp_path / "rag_storage"
    rag = _Rag()
    calls: list[tuple[str, str, Any, Any]] = []

    async def process_document(file_path: str, file_name: str, rag_instance: Any, llm_func: Any) -> dict[str, Any]:
        calls.append((file_path, file_name, rag_instance, llm_func))
        return {"status": "success", "doc_id": "doc-new"}

    promoter = OntologyPromoter(
        store=store,
        workspace_root=workspace_root,
        rag_instance=rag,
        process_document_func=process_document,
        active_workspace="afcap6_drfp_171",
    )

    result = asyncio.run(
        promoter.refresh("notes/2026-05-09-fit.md", workspace="afcap6_drfp_171")
    )

    assert result["status"] == "processed"
    assert result["doc_id"] == "doc-new"
    assert calls[0][1] == "2026-05-09-fit.md"
    assert calls[0][2] is rag
    assert calls[0][3] == "llm-func"
    assert rag.lightrag.deleted == []

    manifest_record = store.list_promotions(
        workspace="afcap6_drfp_171",
        workspace_root=workspace_root,
    )[0]
    assert manifest_record["ingestion_status"] == "processed"
    assert manifest_record["doc_id"] == "doc-new"


def test_ontology_promoter_deletes_previous_doc_before_reingest(tmp_path: Path) -> None:
    store = GlobalStore(root=tmp_path / "global")
    store.write("notes/2026-05-09-fit.md", _note("Fit score seed"))
    workspace_root = tmp_path / "rag_storage"
    store.promote("notes/2026-05-09-fit.md", workspace="afcap6_drfp_171", workspace_root=workspace_root)
    store.update_promotion_ingestion(
        "notes/2026-05-09-fit.md",
        workspace="afcap6_drfp_171",
        workspace_root=workspace_root,
        ingestion_status="processed",
        doc_id="doc-old",
    )
    rag = _Rag()

    async def process_document(file_path: str, file_name: str, rag_instance: Any, llm_func: Any) -> dict[str, Any]:
        return {"status": "success", "doc_id": "doc-new"}

    promoter = OntologyPromoter(
        store=store,
        workspace_root=workspace_root,
        rag_instance=rag,
        process_document_func=process_document,
        active_workspace="afcap6_drfp_171",
    )

    result = asyncio.run(
        promoter.refresh(
            "notes/2026-05-09-fit.md",
            workspace="afcap6_drfp_171",
            delete_existing=True,
            delete_llm_cache=True,
        )
    )

    assert rag.lightrag.deleted == [("doc-old", True)]
    assert result["deleted_doc_id"] == "doc-old"
    assert result["delete_result"] == {"status": "deleted", "doc_id": "doc-old"}


def test_ontology_promoter_rejects_inactive_workspace(tmp_path: Path) -> None:
    store = GlobalStore(root=tmp_path / "global")
    store.write("notes/2026-05-09-fit.md", _note("Fit score seed"))

    async def process_document(file_path: str, file_name: str, rag_instance: Any, llm_func: Any) -> dict[str, Any]:
        return {"status": "success"}

    promoter = OntologyPromoter(
        store=store,
        workspace_root=tmp_path / "rag_storage",
        rag_instance=_Rag(),
        process_document_func=process_document,
        active_workspace="active_ws",
    )

    with pytest.raises(ValueError, match="target workspace to be active"):
        asyncio.run(promoter.refresh("notes/2026-05-09-fit.md", workspace="other_ws"))