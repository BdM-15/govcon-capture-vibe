from pathlib import Path

from src.skills.context_artifacts import (
    ContextArtifactRef,
    format_context_artifacts_prompt_block,
    resolve_context_artifacts,
    to_input_artifacts_payload,
)
from src.skills.runs import SkillRunStore


def _seed_artifact(
    workspace_root: Path,
    *,
    skill: str,
    run_id: str,
    filename: str,
    content: str,
) -> Path:
    artifacts_dir = (
        workspace_root / "skill_runs" / skill / run_id / "artifacts"
    )
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    path = artifacts_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


def test_resolve_context_artifacts_inlines_text_excerpt(tmp_path: Path) -> None:
    _seed_artifact(
        tmp_path,
        skill="mission-readiness-framer",
        run_id="20260611_151031_mcpp",
        filename="readiness-frame.md",
        content="# Frame\n\nKBR incumbent context.",
    )
    store = SkillRunStore()

    resolved, errors = resolve_context_artifacts(
        tmp_path,
        [
            ContextArtifactRef(
                skill="mission-readiness-framer",
                run_id="20260611_151031_mcpp",
                filename="readiness-frame.md",
            )
        ],
        get_artifact_path=store.get_artifact_path,
    )

    assert errors == []
    assert len(resolved) == 1
    assert "KBR incumbent context." in resolved[0].excerpt
    assert resolved[0].path.endswith("readiness-frame.md")


def test_resolve_context_artifacts_rejects_missing_files(tmp_path: Path) -> None:
    store = SkillRunStore()

    resolved, errors = resolve_context_artifacts(
        tmp_path,
        [
            ContextArtifactRef(
                skill="huashu-design",
                run_id="20260611_000000",
                filename="missing.md",
            )
        ],
        get_artifact_path=store.get_artifact_path,
    )

    assert resolved == []
    assert errors == ["Artifact not found: huashu-design/20260611_000000/missing.md"]


def test_format_context_artifacts_prompt_block_includes_handoff_json(
    tmp_path: Path,
) -> None:
    path = _seed_artifact(
        tmp_path,
        skill="mission-readiness-framer",
        run_id="20260611_151031_mcpp",
        filename="readiness-frame.md",
        content="handoff body",
    )
    store = SkillRunStore()
    resolved, _ = resolve_context_artifacts(
        tmp_path,
        [
            ContextArtifactRef(
                skill="mission-readiness-framer",
                run_id="20260611_151031_mcpp",
                filename="readiness-frame.md",
            )
        ],
        get_artifact_path=store.get_artifact_path,
    )

    block = format_context_artifacts_prompt_block(resolved)
    payload = to_input_artifacts_payload(resolved)

    assert "## Attached Studio Artifacts" in block
    assert "handoff body" in block
    assert "## Theseus Artifact Handoff" in block
    assert payload[0]["path"] == str(path.resolve())
    assert payload[0]["step_id"] == "context"