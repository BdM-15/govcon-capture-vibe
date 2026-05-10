"""Promotion refresh bridge from global vault notes into workspace LightRAG."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from src.core.global_store import GlobalStore


ProcessDocumentFunc = Callable[[str, str, Any, Any], Awaitable[dict[str, Any]]]


class OntologyPromoter:
    """Refresh a promoted global note through the active workspace ingest path."""

    def __init__(
        self,
        *,
        store: GlobalStore,
        workspace_root: str | Path,
        rag_instance: Any,
        process_document_func: ProcessDocumentFunc,
        active_workspace: str | None = None,
    ) -> None:
        self.store = store
        self.workspace_root = Path(workspace_root).resolve()
        self.rag_instance = rag_instance
        self.process_document_func = process_document_func
        self.active_workspace = active_workspace

    def _promotion_record(self, promotion_id: str, *, workspace: str) -> dict[str, Any]:
        for record in self.store.list_promotions(
            workspace=workspace,
            workspace_root=self.workspace_root,
            active_only=True,
        ):
            if record.get("id") == promotion_id:
                return record
        raise FileNotFoundError(f"Promotion not found: {promotion_id} -> {workspace}")

    def _ensure_active_workspace(self, workspace: str) -> None:
        if self.active_workspace and workspace != self.active_workspace:
            raise ValueError(
                "Promotion refresh requires the target workspace to be active: "
                f"{workspace} != {self.active_workspace}"
            )

    async def refresh(
        self,
        path: str,
        *,
        workspace: str,
        delete_existing: bool = True,
        delete_llm_cache: bool = False,
    ) -> dict[str, Any]:
        """Promote note, optionally delete previous doc_id, then re-ingest target file."""
        self._ensure_active_workspace(workspace)
        promotion = self.store.promote(
            path,
            workspace=workspace,
            workspace_root=self.workspace_root,
        )
        record = self._promotion_record(promotion["promotion_id"], workspace=workspace)
        previous_doc_id = record.get("doc_id")
        target = Path(promotion["target"])
        delete_result: Any = None

        try:
            self.store.update_promotion_ingestion(
                path,
                workspace=workspace,
                workspace_root=self.workspace_root,
                ingestion_status="refreshing",
            )
            if delete_existing and previous_doc_id:
                delete_result = await self.rag_instance.lightrag.adelete_by_doc_id(
                    str(previous_doc_id),
                    delete_llm_cache=delete_llm_cache,
                )

            process_result = await self.process_document_func(
                str(target),
                target.name,
                self.rag_instance,
                getattr(self.rag_instance, "llm_model_func", None),
            )
            doc_id = process_result.get("doc_id") or previous_doc_id
            manifest_record = self.store.update_promotion_ingestion(
                path,
                workspace=workspace,
                workspace_root=self.workspace_root,
                ingestion_status="processed",
                doc_id=str(doc_id) if doc_id else None,
                refresh_result=process_result,
            )
        except Exception as exc:
            self.store.update_promotion_ingestion(
                path,
                workspace=workspace,
                workspace_root=self.workspace_root,
                ingestion_status="failed",
                error=str(exc),
            )
            raise

        return {
            **promotion,
            "status": "processed",
            "doc_id": doc_id,
            "deleted_doc_id": previous_doc_id if delete_existing else None,
            "delete_result": delete_result,
            "process_result": process_result,
            "record": manifest_record,
        }


__all__ = ["OntologyPromoter", "ProcessDocumentFunc"]