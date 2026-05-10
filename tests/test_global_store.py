import json
from pathlib import Path

import pytest

from src.core.global_store import GlobalStore


def _note(*, body: str, workspace: str | None = None) -> str:
    workspace_line = f"workspace: {workspace}\n" if workspace else ""
    return (
        "---\n"
        "date: 2026-05-09\n"
        "source: capture\n"
        "status: inbox\n"
        f"{workspace_line}"
        "tags: [afcap6, pricing]\n"
        "---\n\n"
        f"{body}\n"
    )


def test_global_store_write_read_and_list(tmp_path: Path) -> None:
    store = GlobalStore(root=tmp_path / "global")
    content = _note(body="Incumbent wrap-rate note", workspace="afcap6_drfp_171")

    written = store.write("inbox/2026-05-09-wrap-rate.md", content)

    assert written == (tmp_path / "global" / "inbox" / "2026-05-09-wrap-rate.md")
    assert store.read("inbox/2026-05-09-wrap-rate.md") == content

    entries = store.list("inbox")

    assert [entry["path"] for entry in entries] == ["inbox/2026-05-09-wrap-rate.md"]
    assert entries[0]["frontmatter"]["workspace"] == "afcap6_drfp_171"
    assert entries[0]["preview"] == "Incumbent wrap-rate note"


def test_global_store_search_matches_body_and_path(tmp_path: Path) -> None:
    store = GlobalStore(root=tmp_path / "global")
    store.write(
        "inbox/2026-05-09-oci.md",
        _note(body="OCI concern tied to site-list handoff"),
    )
    store.write(
        "notes/2026-05-09-pricing.md",
        _note(body="Pricing note about unrelated topic"),
    )

    results = store.search("oci")

    assert [entry["path"] for entry in results] == ["inbox/2026-05-09-oci.md"]


def test_global_store_promote_copies_note_into_workspace_sources(tmp_path: Path) -> None:
    store = GlobalStore(root=tmp_path / "global")
    workspace_root = tmp_path / "rag_storage"
    content = _note(body="Promote me", workspace="afcap6_drfp_171")
    store.write("inbox/2026-05-09-promote.md", content)

    result = store.promote(
        "inbox/2026-05-09-promote.md",
        workspace="afcap6_drfp_171",
        workspace_root=workspace_root,
    )

    expected = workspace_root / "afcap6_drfp_171" / "sources" / "2026-05-09-promote.md"
    assert result["source"] == "inbox/2026-05-09-promote.md"
    assert result["workspace"] == "afcap6_drfp_171"
    assert result["target"] == str(expected)
    assert result["target_relative"] == "sources/2026-05-09-promote.md"
    assert result["ingestion_status"] == "pending"
    assert expected.read_text(encoding="utf-8") == content

    manifest = json.loads(
        (workspace_root / "afcap6_drfp_171" / "sources" / ".ariadne_promotions.json").read_text(
            encoding="utf-8",
        ),
    )
    assert manifest["version"] == 1
    assert manifest["promotions"][0]["source"] == "inbox/2026-05-09-promote.md"
    assert manifest["promotions"][0]["target"] == "sources/2026-05-09-promote.md"
    assert manifest["promotions"][0]["active"] is True


def test_global_store_promote_is_idempotent_and_listable(tmp_path: Path) -> None:
    store = GlobalStore(root=tmp_path / "global")
    workspace_root = tmp_path / "rag_storage"
    content = _note(body="Promote me", workspace="afcap6_drfp_171")
    store.write("notes/2026-05-09-promote.md", content)

    first = store.promote(
        "notes/2026-05-09-promote.md",
        workspace="afcap6_drfp_171",
        workspace_root=workspace_root,
    )
    second = store.promote(
        "notes/2026-05-09-promote.md",
        workspace="afcap6_drfp_171",
        workspace_root=workspace_root,
    )

    promotions = store.list_promotions(
        workspace="afcap6_drfp_171",
        workspace_root=workspace_root,
        active_only=True,
    )
    assert first["promotion_id"] == second["promotion_id"]
    assert len(promotions) == 1
    assert promotions[0]["source"] == "notes/2026-05-09-promote.md"


def test_global_store_unpromote_removes_managed_target(tmp_path: Path) -> None:
    store = GlobalStore(root=tmp_path / "global")
    workspace_root = tmp_path / "rag_storage"
    content = _note(body="Promote me", workspace="afcap6_drfp_171")
    store.write("inbox/2026-05-09-promote.md", content)
    promoted = store.promote(
        "inbox/2026-05-09-promote.md",
        workspace="afcap6_drfp_171",
        workspace_root=workspace_root,
    )

    result = store.unpromote(
        "inbox/2026-05-09-promote.md",
        workspace="afcap6_drfp_171",
        workspace_root=workspace_root,
    )

    assert result["promotion_id"] == promoted["promotion_id"]
    assert result["deleted_target"] is True
    assert not Path(promoted["target"]).exists()
    promotions = store.list_promotions(
        workspace="afcap6_drfp_171",
        workspace_root=workspace_root,
    )
    assert promotions[0]["active"] is False
    assert promotions[0]["revoked_at"]


def test_global_store_update_promotion_ingestion_records_doc_id(tmp_path: Path) -> None:
    store = GlobalStore(root=tmp_path / "global")
    workspace_root = tmp_path / "rag_storage"
    store.write("notes/2026-05-09-promote.md", _note(body="Promote me"))
    store.promote(
        "notes/2026-05-09-promote.md",
        workspace="afcap6_drfp_171",
        workspace_root=workspace_root,
    )

    record = store.update_promotion_ingestion(
        "notes/2026-05-09-promote.md",
        workspace="afcap6_drfp_171",
        workspace_root=workspace_root,
        ingestion_status="processed",
        doc_id="doc-123",
        refresh_result={"status": "success"},
    )

    assert record["ingestion_status"] == "processed"
    assert record["doc_id"] == "doc-123"
    assert record["last_refresh_result"] == {"status": "success"}
    assert record["last_refresh_at"]


def test_global_store_unpromote_refuses_modified_target(tmp_path: Path) -> None:
    store = GlobalStore(root=tmp_path / "global")
    workspace_root = tmp_path / "rag_storage"
    store.write("inbox/2026-05-09-promote.md", _note(body="Promote me"))
    promoted = store.promote(
        "inbox/2026-05-09-promote.md",
        workspace="afcap6_drfp_171",
        workspace_root=workspace_root,
    )
    Path(promoted["target"]).write_text("manual edit\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Promoted target changed"):
        store.unpromote(
            "inbox/2026-05-09-promote.md",
            workspace="afcap6_drfp_171",
            workspace_root=workspace_root,
        )


def test_global_store_rejects_path_escape(tmp_path: Path) -> None:
    store = GlobalStore(root=tmp_path / "global")

    with pytest.raises(ValueError, match="Path escapes global root"):
        store.read("../secrets.txt")