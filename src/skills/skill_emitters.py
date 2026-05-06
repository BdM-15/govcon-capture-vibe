"""Best-effort artifact emitters for skill runs."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

from src.skills.run_metadata import read_artifact_manifest, write_artifact_manifest
from src.skills.skill_models import Skill

logger = logging.getLogger(__name__)


def _display_title(skill: Skill) -> str:
    return " ".join(part.capitalize() for part in skill.name.replace("_", "-").split("-"))


def _set_display_names(run_dir: Path, labels: dict[str, str]) -> None:
    manifest = read_artifact_manifest(run_dir)
    for artifact, display_name in labels.items():
        entry = dict(manifest.get(artifact) or {})
        entry["display_name"] = display_name
        manifest[artifact] = entry
    write_artifact_manifest(run_dir, manifest)


def _auto_emit_formats(skill: Skill) -> set[str]:
    raw = (skill.frontmatter.metadata or {}).get("auto_emit_formats")
    if raw is None:
        return {"md", "json"}
    if isinstance(raw, str):
        values = [part.strip().lower() for part in raw.split(",")]
    elif isinstance(raw, list):
        values = [str(part).strip().lower() for part in raw]
    else:
        return {"md", "json"}
    formats = {value for value in values if value in {"md", "json", "docx", "xlsx"}}
    return formats or {"md", "json"}


def _xlsx_source_path(skill: Skill, artifacts_dir: Path) -> Path | None:
    raw = (skill.frontmatter.metadata or {}).get("auto_emit_xlsx_source")
    if not isinstance(raw, str) or not raw.strip():
        return None
    candidate = (artifacts_dir / raw.strip()).resolve()
    artifacts_root = artifacts_dir.resolve()
    if candidate == artifacts_root or not candidate.is_relative_to(artifacts_root):
        return None
    return candidate


def auto_emit_artifacts(skill: Skill, run_dir: Path, repo_root: Path | None = None) -> None:
    """Render generic Studio artifacts for a completed skill run."""
    try:
        formats = _auto_emit_formats(skill)
        skill_dir = Path(skill.path)
        artifacts_dir = Path(run_dir) / "artifacts"
        tool_outputs_dir = Path(run_dir) / "tool_outputs"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        tool_outputs_dir.mkdir(parents=True, exist_ok=True)

        response_path = Path(run_dir) / "response.md"
        if not response_path.exists():
            return

        report_md = artifacts_dir / "report.md"
        response_text = response_path.read_text(encoding="utf-8")
        report_md.write_text(response_text, encoding="utf-8")

        report_json = artifacts_dir / "report.json"
        json_payload = {
            "summary": [
                {
                    "skill": skill.name,
                    "text": response_text.strip()[:5000],
                }
            ]
        }
        report_json.write_text(json.dumps(json_payload, ensure_ascii=False), encoding="utf-8")

        title = _display_title(skill)
        labels = {
            "report.md": f"{title} Final Response",
            "report.json": f"{title} Final Response Data",
        }

        if not ({"docx", "xlsx"} & formats):
            _set_display_names(Path(run_dir), labels)
            return

        if repo_root is None:
            repo_root = Path(__file__).resolve().parents[2]
        renderers_dir = repo_root / ".github" / "skills" / "renderers" / "scripts"

        def _run_script(prog_path: Path, args: list[str], out_name: str) -> None:
            try:
                proc = subprocess.run(
                    [sys.executable, str(prog_path)] + args,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=120,
                )
            except Exception as exc:  # noqa: BLE001
                (tool_outputs_dir / f"{out_name}.stderr.txt").write_text(str(exc), encoding="utf-8")
                return
            (tool_outputs_dir / f"{out_name}.stdout.txt").write_text(proc.stdout or "", encoding="utf-8")
            (tool_outputs_dir / f"{out_name}.stderr.txt").write_text(proc.stderr or "", encoding="utf-8")

        docx_script = renderers_dir / "render_docx.py"
        if "docx" in formats and docx_script.is_file():
            out_docx = artifacts_dir / f"{skill.name}_report.docx"
            args = ["--input", str(report_md), "--output", str(out_docx)]
            ref = skill_dir / "assets" / "reference.docx"
            if ref.is_file():
                args.extend(["--reference", str(ref)])
            _run_script(docx_script, args, "render_docx")
            if out_docx.is_file():
                labels[out_docx.name] = f"{title} Final Response DOCX"

        xlsx_script = renderers_dir / "render_xlsx.py"
        if "xlsx" in formats and xlsx_script.is_file():
            xlsx_source = _xlsx_source_path(skill, artifacts_dir)
            if xlsx_source is None or not xlsx_source.is_file():
                (tool_outputs_dir / "render_xlsx.stderr.txt").write_text(
                    "auto_emit_xlsx_source must point to a JSON table artifact before XLSX auto-emission runs.",
                    encoding="utf-8",
                )
                _set_display_names(Path(run_dir), labels)
                return
            out_xlsx = artifacts_dir / f"{skill.name}_report.xlsx"
            args = ["--input", str(xlsx_source), "--output", str(out_xlsx), "--title", "Skill Report"]
            _run_script(xlsx_script, args, "render_xlsx")
            if out_xlsx.is_file():
                labels[out_xlsx.name] = f"{title} Final Response Workbook"
        _set_display_names(Path(run_dir), labels)
    except Exception as exc:  # noqa: BLE001
        logger.warning("auto_emit_artifacts error: %s", exc)
