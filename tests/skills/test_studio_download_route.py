"""148 — Contract tests for the Studio artifact download route.

Locks the mime-type contract: the download endpoint
``GET /api/ui/skills/{name}/runs/{run_id}/artifacts/{filename}`` MUST
return the same mime type the listing endpoint advertises (per
``_STUDIO_EXTRA_MIME`` in ``src/skills/manager.py``). Without this, the
Studio drawer can label a row ``text/markdown`` while the download
serves ``application/text`` (or whatever Windows' registry happens to
hold), which breaks the inline preview + browser download UX.

Both routes are exercised against a temp workspace via FastAPI's
``TestClient`` — no live server, no port collision.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.skills.manager import _STUDIO_EXTRA_MIME, resolve_artifact_mime


@pytest.fixture()
def client_factory(monkeypatch: pytest.MonkeyPatch):
    """Build a TestClient bound to an arbitrary workspace dir per test."""
    from src.server import ui_routes

    def _build(workspace: Path) -> TestClient:
        monkeypatch.setattr(ui_routes, "_workspace_dir", lambda: workspace)
        app = FastAPI()

        async def _stub_query(*_a, **_kw):  # pragma: no cover
            return ""

        ui_routes.register_ui(app, query_func=_stub_query)
        return TestClient(app)

    return _build


def _seed_artifact(
    workspace: Path,
    *,
    skill: str,
    run_id: str,
    filename: str,
    content: bytes,
) -> Path:
    run_dir = workspace / "skill_runs" / skill / run_id
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.md").write_text(
        f"---\nrun_id: {run_id}\nskill: {skill}\nworkspace: ws\n"
        f"created_at: 2026-04-30T12:00:00\nelapsed_ms: 1\n"
        f"entities_used: []\nresponse_chars: 1\n---\n\n# Skill Run\n",
        encoding="utf-8",
    )
    (run_dir / "response.md").write_text("ok", encoding="utf-8")
    target = artifacts / filename
    target.write_bytes(content)
    return target


# ---------------------------------------------------------------------------
# resolve_artifact_mime — pure helper coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("draft.docx", _STUDIO_EXTRA_MIME["docx"]),
        ("compliance.xlsx", _STUDIO_EXTRA_MIME["xlsx"]),
        ("slides.pptx", _STUDIO_EXTRA_MIME["pptx"]),
        ("final.html", "text/html"),
        ("pws.md", "text/markdown"),
        ("envelope.json", "application/json"),
        ("brief.pdf", "application/pdf"),
        ("demo.gif", "image/gif"),
        ("clip.mp4", "video/mp4"),
    ],
)
def test_resolve_artifact_mime_explicit_map(filename: str, expected: str) -> None:
    """Explicit map wins over stdlib guess (Windows mislabels .md / office formats)."""
    assert resolve_artifact_mime(filename) == expected


def test_resolve_artifact_mime_unknown_extension_falls_back() -> None:
    """Unknown extension falls back to octet-stream, never raises."""
    assert resolve_artifact_mime("mystery.zzz") == "application/octet-stream"


def test_resolve_artifact_mime_no_extension_falls_back() -> None:
    """Filenames with no dot get octet-stream, no IndexError."""
    assert resolve_artifact_mime("README") == "application/octet-stream"


# ---------------------------------------------------------------------------
# Download route — contract against listing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ext,content,expected_mime",
    [
        ("html", b"<h1>PWS</h1>", "text/html"),
        (
            "docx",
            b"PK\x03\x04fake-docx-payload",
            _STUDIO_EXTRA_MIME["docx"],
        ),
        (
            "xlsx",
            b"PK\x03\x04fake-xlsx-payload",
            _STUDIO_EXTRA_MIME["xlsx"],
        ),
    ],
)
def test_download_serves_correct_mime_per_format(
    tmp_path: Path,
    client_factory,
    ext: str,
    content: bytes,
    expected_mime: str,
) -> None:
    """The download Content-Type MUST match the listing-advertised mime.

    Regression for the bug 148 surfaced: pre-fix, ``.md`` downloaded as
    ``application/text`` (an invalid mime Windows' registry returned)
    while the listing advertised ``text/markdown``. The two MUST agree.
    """
    skill = "renderers"
    run_id = "20260430_120000_test_run"
    filename = f"deliverable.{ext}"
    _seed_artifact(
        tmp_path,
        skill=skill,
        run_id=run_id,
        filename=filename,
        content=content,
    )

    client = client_factory(tmp_path)

    # Listing advertises this mime
    listing = client.get("/api/ui/studio").json()
    rows = [
        r for r in listing["deliverables"]
        if r["filename"] == filename and r["skill"] == skill
    ]
    assert len(rows) == 1, listing
    advertised = rows[0]["mime"]
    assert advertised == expected_mime

    # Download MUST serve the same mime + correct disposition + correct bytes
    resp = client.get(
        f"/api/ui/skills/{skill}/runs/{run_id}/artifacts/{filename}"
    )
    assert resp.status_code == 200
    served = resp.headers["content-type"].split(";")[0].strip().lower()
    assert served == expected_mime.lower(), (
        f"Listing said {expected_mime!r} but download served {served!r}"
    )
    cd = resp.headers.get("content-disposition", "")
    assert "attachment" in cd.lower()
    assert filename in cd
    assert resp.content == content


def test_download_unknown_artifact_404(tmp_path: Path, client_factory) -> None:
    client = client_factory(tmp_path)
    resp = client.get(
        "/api/ui/skills/renderers/runs/no_such_run/artifacts/missing.md"
    )
    assert resp.status_code == 404


def test_studio_delete_selected_artifacts_removes_files(
    tmp_path: Path,
    client_factory,
) -> None:
    skill = "competitive-intel"
    run_id = "20260430_120000_test_run"
    html_path = _seed_artifact(
        tmp_path,
        skill=skill,
        run_id=run_id,
        filename="final.html",
        content=b"<h1>final</h1>",
    )
    source_path = _seed_artifact(
        tmp_path,
        skill=skill,
        run_id=run_id,
        filename="report.json",
        content=b"{}",
    )
    client = client_factory(tmp_path)

    response = client.request(
        "DELETE",
        "/api/ui/studio/artifacts",
        json={
            "artifacts": [
                {"skill": skill, "run_id": run_id, "filename": "final.html"},
                {"skill": skill, "run_id": run_id, "filename": "missing.html"},
            ]
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["deleted_count"] == 1
    assert payload["missing_count"] == 1
    assert not html_path.exists()
    assert source_path.exists()
    assert client.get("/api/ui/studio").json()["deliverables"] == []


def test_studio_zip_selected_artifacts_downloads_archive(
    tmp_path: Path,
    client_factory,
) -> None:
    skill = "competitive-intel"
    run_id = "20260430_120000_test_run"
    _seed_artifact(
        tmp_path,
        skill=skill,
        run_id=run_id,
        filename="brief.docx",
        content=b"PK\x03\x04brief",
    )
    _seed_artifact(
        tmp_path,
        skill=skill,
        run_id=run_id,
        filename="workbook.xlsx",
        content=b"PK\x03\x04workbook",
    )
    client = client_factory(tmp_path)

    response = client.post(
        "/api/ui/studio/artifacts.zip",
        json={
            "artifacts": [
                {"skill": skill, "run_id": run_id, "filename": "brief.docx"},
                {"skill": skill, "run_id": run_id, "filename": "workbook.xlsx"},
                {"skill": skill, "run_id": run_id, "filename": "missing.xlsx"},
            ]
        },
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].split(";")[0] == "application/zip"
    assert response.headers["x-theseus-zip-count"] == "2"
    assert response.headers["x-theseus-zip-missing"] == "1"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        assert f"{skill}/{run_id}/brief.docx" in names
        assert f"{skill}/{run_id}/workbook.xlsx" in names
        manifest = json.loads(archive.read("manifest.json"))
    assert len(manifest["included"]) == 2
    assert len(manifest["missing"]) == 1
