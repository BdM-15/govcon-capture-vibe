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


def test_ui_static_assets_disable_browser_caching(
    tmp_path: Path,
    client_factory,
) -> None:
    client = client_factory(tmp_path)

    response = client.get("/ui/app/theseus-app-delegates.js")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["expires"] == "0"


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
    assert payload["trashed_count"] == 1
    assert payload["missing_count"] == 1
    assert not html_path.exists()
    assert source_path.exists()
    assert client.get("/api/ui/studio").json()["deliverables"] == []
    trash = client.get("/api/ui/studio/trash").json()
    assert trash["count"] == 1
    assert trash["artifacts"][0]["filename"] == "final.html"


def test_studio_trash_restore_recovers_selected_artifact(
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
    client = client_factory(tmp_path)

    trash_response = client.request(
        "DELETE",
        "/api/ui/studio/artifacts",
        json={
            "artifacts": [
                {"skill": skill, "run_id": run_id, "filename": "final.html"},
            ]
        },
    )
    assert trash_response.status_code == 200, trash_response.text
    trash_id = trash_response.json()["trashed"][0]["trash_id"]

    restore_response = client.post(
        "/api/ui/studio/trash/restore",
        json={"artifacts": [{"trash_id": trash_id}]},
    )

    assert restore_response.status_code == 200, restore_response.text
    payload = restore_response.json()
    assert payload["restored_count"] == 1
    assert payload["conflict_count"] == 0
    assert html_path.exists()
    listing = client.get("/api/ui/studio").json()
    assert any(row["filename"] == "final.html" for row in listing["deliverables"])


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


def test_rerender_skill_run_artifacts_promotes_existing_source_run(
        tmp_path: Path,
        client_factory,
) -> None:
        skill = "competitive-intel"
        run_id = "20260506_235024_provide_me_a_burn_rate_analysis"
        _seed_artifact(
                tmp_path,
                skill=skill,
                run_id=run_id,
                filename="competitive_intel_obligation.json",
                content=(
                        """
                        {
                            "input_contract_number": "FA805122F0001",
                            "resolved": {"scenario": "idiq_order"},
                            "hierarchy": {"parent_award_id": "CONT_IDV_PARENT"},
                            "obligations": {
                                "total_obligated_usd": 44070085.27,
                                "net_obligated_usd": 43659700.13,
                                "rate_analysis": {
                                    "monthly_burn_usd": 698555.2,
                                    "annual_burn_usd": 8382662.42,
                                    "daily_burn_usd": 23297.6
                                },
                                "by_transaction": [
                                    {
                                        "modification_number": "P00005",
                                        "action_type": "G",
                                        "action_date": "2022-11-17",
                                        "amount_usd": 9183672.0
                                    },
                                    {
                                        "modification_number": "P00014",
                                        "action_type": "G",
                                        "action_date": "2025-11-14",
                                        "amount_usd": 8369667.0,
                                        "modification_description": "Exercise option four"
                                    }
                                ]
                            },
                            "insights": {
                                "headline": "Clean burn story.",
                                "blocks": [
                                    {
                                        "id": "burn_posture",
                                        "evidence": {
                                            "recommended_ptw_baseline_usd": 8388921.37,
                                            "pop_end_potential": "2026-12-15"
                                        }
                                    },
                                    {
                                        "id": "award_story",
                                        "summary": "One award story across base and options.",
                                        "evidence": {
                                            "period_of_performance_segments": [
                                                {
                                                    "label": "Base period",
                                                    "pop_start_date": "2021-10-28",
                                                    "pop_end_date": "2022-11-17",
                                                    "months": 13.0,
                                                    "obligated_usd": 9229200.0,
                                                    "monthly_rate_usd": 709938.46
                                                }
                                            ]
                                        }
                                    }
                                ]
                            },
                            "vehicle_context": {
                                "child_order_count": 22,
                                "net_obligated_usd": 390322586.54
                            },
                            "competitor_discovery": {
                                "completeness_status": "high",
                                "parent_vehicle_awardee_count": 8,
                                "order_holder_count": 1
                            },
                            "warnings": []
                        }
                        """.encode("utf-8")
                ),
        )

        client = client_factory(tmp_path)

        response = client.post(
                f"/api/ui/skills/{skill}/runs/{run_id}/artifacts/render"
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["deliverable_count"] >= 1
        assert any(
                row["filename"] == "competitive_intel_brief.docx"
                for row in payload["deliverables"]
        )
        brief = next(
            row
            for row in payload["deliverables"]
            if row["filename"] == "competitive_intel_brief.docx"
        )
        assert brief["display_name"] == "FA805122F0001 Task Order Burn Brief"
        assert (
                tmp_path
                / "skill_runs"
                / skill
                / run_id
                / "artifacts"
                / "competitive_intel_brief.docx"
        ).is_file()

        listing = client.get("/api/ui/studio").json()
        assert any(
                row["skill"] == skill
                and row["run_id"] == run_id
                and row["filename"] == "competitive_intel_brief.docx"
            and row["display_name"] == "FA805122F0001 Task Order Burn Brief"
                for row in listing["deliverables"]
        )


def test_reasoning_route_surfaces_render_failure_metadata(
    tmp_path: Path,
    client_factory,
) -> None:
    skill = "competitive-intel"
    run_id = "20260507_120000_render_failure"
    run_dir = tmp_path / "skill_runs" / skill / run_id
    _seed_artifact(
        tmp_path,
        skill=skill,
        run_id=run_id,
        filename="competitive_intel_obligation.json",
        content=b"{}",
    )
    (run_dir / "artifacts_manifest.json").write_text(
        json.dumps(
            {
                "competitive_intel_obligation.json": {
                    "display_name": "Competitive Intel Source",
                    "render_status": "failed",
                    "render_message": "render_xlsx exited with code 2",
                    "render_targets": ["competitive_intel_obligation.xlsx"],
                    "render_logs": ["render_xlsx_competitive_intel_obligation.stderr.txt"],
                    "render_log_excerpt": "Traceback: workbook generation failed",
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    client = client_factory(tmp_path)

    response = client.get(f"/api/ui/skills/{skill}/runs/{run_id}/reasoning")

    assert response.status_code == 200, response.text
    payload = response.json()
    source = next(
        artifact
        for artifact in payload["artifacts"]
        if artifact["name"] == "competitive_intel_obligation.json"
    )
    assert source["display_name"] == "Competitive Intel Source"
    assert source["render_status"] == "failed"
    assert source["render_message"] == "render_xlsx exited with code 2"
    assert source["render_targets"] == ["competitive_intel_obligation.xlsx"]
    assert source["render_logs"] == ["render_xlsx_competitive_intel_obligation.stderr.txt"]
    assert source["render_log_excerpt"] == "Traceback: workbook generation failed"
