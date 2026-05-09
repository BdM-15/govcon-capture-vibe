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
    assert result == {
        "source": "inbox/2026-05-09-promote.md",
        "workspace": "afcap6_drfp_171",
        "target": str(expected),
    }
    assert expected.read_text(encoding="utf-8") == content


def test_global_store_rejects_path_escape(tmp_path: Path) -> None:
    store = GlobalStore(root=tmp_path / "global")

    with pytest.raises(ValueError, match="Path escapes global root"):
        store.read("../secrets.txt")