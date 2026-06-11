import asyncio
from pathlib import Path

import pytest

from src.skills.tool_types import ToolContext, ToolError
from src.skills.tool_workspace_artifacts import tool_read_workspace_artifact


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _seed_artifact(workspace_root: Path) -> tuple[str, str, str, Path]:
    skill = "mission-readiness-framer"
    run_id = "20260611_151031_mcpp"
    filename = "readiness-frame.md"
    artifacts_dir = workspace_root / "skill_runs" / skill / run_id / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    path = artifacts_dir / filename
    path.write_text("# Frame\n\nAttached body.", encoding="utf-8")
    return skill, run_id, filename, path


def test_read_workspace_artifact_returns_attached_content(tmp_path: Path) -> None:
    skill, run_id, filename, path = _seed_artifact(tmp_path)
    ctx = ToolContext(
        skill_name="huashu-design",
        skill_dir=tmp_path,
        run_dir=tmp_path / "run",
        workspace_dir=tmp_path,
        workspace_name="demo",
        attached_artifacts=[
            {
                "skill": skill,
                "run_id": run_id,
                "filename": filename,
                "path": str(path.resolve()),
            }
        ],
    )

    result = _run(
        tool_read_workspace_artifact(ctx, skill, run_id, filename)
    )

    assert "Attached body." in result.payload["content"]
    assert result.payload["path"] == str(path.resolve())


def test_read_workspace_artifact_rejects_unattached_refs(tmp_path: Path) -> None:
    skill, run_id, filename, _ = _seed_artifact(tmp_path)
    ctx = ToolContext(
        skill_name="huashu-design",
        skill_dir=tmp_path,
        run_dir=tmp_path / "run",
        workspace_dir=tmp_path,
        workspace_name="demo",
        attached_artifacts=[],
    )

    with pytest.raises(ToolError, match="not attached"):
        _run(tool_read_workspace_artifact(ctx, skill, run_id, filename))