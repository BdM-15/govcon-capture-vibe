import asyncio
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile

from src.server import upload_staging


class FakeSettings:
    workspace = "active"


def _upload(name: str, content: bytes) -> UploadFile:
    return UploadFile(filename=name, file=BytesIO(content))


def test_sanitize_upload_filename_strips_separators_and_dot_prefix() -> None:
    assert upload_staging.sanitize_upload_filename("../bad\\name.pdf") == "_bad_name.pdf"


def test_save_upload_to_workspace_reuses_identical_content(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(upload_staging, "get_settings", lambda: FakeSettings())

    first = _upload("demo.pdf", b"same")
    second = _upload("demo.pdf", b"same")

    path1 = asyncio.run(upload_staging.save_upload_to_workspace(first))
    path2 = asyncio.run(upload_staging.save_upload_to_workspace(second))

    assert path1 == path2
    assert path1.name == "demo.pdf"


def test_save_upload_to_workspace_renames_on_collision(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(upload_staging, "get_settings", lambda: FakeSettings())

    class FrozenDatetime:
        @classmethod
        def now(cls):
            class Value:
                def strftime(self, fmt: str) -> str:
                    return "20260504_123456"

            return Value()

    monkeypatch.setattr(upload_staging, "datetime", FrozenDatetime)

    first = _upload("demo.pdf", b"one")
    second = _upload("demo.pdf", b"two")

    path1 = asyncio.run(upload_staging.save_upload_to_workspace(first))
    path2 = asyncio.run(upload_staging.save_upload_to_workspace(second))

    assert path1.name == "demo.pdf"
    assert path2.name == "demo_20260504_123456.pdf"
    assert path2.read_bytes() == b"two"


def test_resolve_scan_folder_uses_requested_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(upload_staging, "get_settings", lambda: FakeSettings())

    folder = upload_staging.resolve_scan_folder("other")

    assert folder == Path("inputs") / "other"
    assert folder.is_dir()


def test_list_scannable_files_filters_supported_suffixes(tmp_path: Path) -> None:
    (tmp_path / "a.pdf").write_text("a", encoding="utf-8")
    (tmp_path / "b.PDF").write_text("b", encoding="utf-8")
    (tmp_path / "c.txt").write_text("c", encoding="utf-8")
    (tmp_path / "ignore.json").write_text("{}", encoding="utf-8")

    files = upload_staging.list_scannable_files(tmp_path)

    assert [path.name for path in files] == ["a.pdf", "b.PDF", "c.txt"]