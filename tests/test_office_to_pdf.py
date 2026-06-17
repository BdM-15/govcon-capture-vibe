from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.server.office_to_pdf import (
    convert_office_to_pdf,
    is_office_source,
    office_pdf_cache_root,
    resolve_libreoffice_executable,
    stage_office_pdf_for_mineru,
)


def test_is_office_source_recognizes_word_suffixes_only() -> None:
    assert is_office_source("sow.docx")
    assert is_office_source("legacy.DOC")
    assert not is_office_source("slides.PPTX")
    assert not is_office_source("pricing.xlsx")
    assert not is_office_source("brief.pdf")


def test_office_pdf_cache_root_under_workspace() -> None:
    root = office_pdf_cache_root("rag_storage", "mcpp_rfp_t1")
    assert root == Path("rag_storage") / "mcpp_rfp_t1" / ".office_pdf_cache"


def test_convert_office_to_pdf_uses_cache_on_repeat(tmp_path: Path) -> None:
    source = tmp_path / "sample.docx"
    source.write_bytes(b"fake-docx-bytes")
    cache_root = tmp_path / "cache"
    calls: list[list[str]] = []

    def fake_runner(cmd, **kwargs):
        calls.append(cmd)
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        pdf = outdir / "sample.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Result()

    first = convert_office_to_pdf(
        source,
        cache_root=cache_root,
        libreoffice_path=__file__,
        run_subprocess=fake_runner,
    )
    second = convert_office_to_pdf(
        source,
        cache_root=cache_root,
        libreoffice_path=__file__,
        run_subprocess=fake_runner,
    )

    assert first.converted is True
    assert second.converted is True
    assert first.enqueue_path == second.enqueue_path
    assert len(calls) == 1
    meta = json.loads((first.cache_dir / "source.meta.json").read_text(encoding="utf-8"))
    assert meta["source_name"] == "sample.docx"


def test_convert_office_to_pdf_passthrough_for_pdf(tmp_path: Path) -> None:
    source = tmp_path / "brief.pdf"
    source.write_bytes(b"%PDF")
    result = convert_office_to_pdf(source, cache_root=tmp_path / "cache")
    assert result.converted is False
    assert result.enqueue_path == source.resolve()


def test_resolve_libreoffice_executable_honors_explicit_path(tmp_path: Path) -> None:
    soffice = tmp_path / "soffice.exe"
    soffice.write_bytes(b"stub")
    assert resolve_libreoffice_executable(str(soffice)) == str(soffice)


def test_resolve_libreoffice_executable_missing_explicit_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="LIBREOFFICE_PATH"):
        resolve_libreoffice_executable(str(tmp_path / "missing.exe"))


def test_stage_office_pdf_for_mineru_copies_into_workspace_inputs(
    tmp_path: Path, monkeypatch
) -> None:
    cache_pdf = tmp_path / "cache" / "sow.pdf"
    cache_pdf.parent.mkdir(parents=True)
    cache_pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.chdir(tmp_path)

    staged = stage_office_pdf_for_mineru(cache_pdf, workspace="mcpp_rfp_t2")

    assert staged == (tmp_path / "inputs" / "mcpp_rfp_t2" / "sow.pdf").resolve()
    assert staged.read_bytes() == b"%PDF-1.4"