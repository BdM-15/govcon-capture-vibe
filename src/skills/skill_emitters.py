"""Best-effort artifact emitters for skill runs."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

from src.skills.skill_models import Skill

logger = logging.getLogger(__name__)


def auto_emit_artifacts(skill: Skill, run_dir: Path, repo_root: Path | None = None) -> None:
    """Render optional DOCX/XLSX artifacts for a completed skill run."""
    try:
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
        json_payload = {"summary": [{"text": response_text.strip()[:1000]}]}
        report_json.write_text(json.dumps(json_payload, ensure_ascii=False), encoding="utf-8")

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
        if docx_script.is_file():
            out_docx = artifacts_dir / f"{skill.name}_report.docx"
            args = ["--input", str(report_md), "--output", str(out_docx)]
            ref = skill_dir / "assets" / "reference.docx"
            if ref.is_file():
                args.extend(["--reference", str(ref)])
            _run_script(docx_script, args, "render_docx")

        xlsx_script = renderers_dir / "render_xlsx.py"
        if xlsx_script.is_file():
            out_xlsx = artifacts_dir / f"{skill.name}_report.xlsx"
            args = ["--input", str(report_json), "--output", str(out_xlsx), "--title", "Skill Report"]
            _run_script(xlsx_script, args, "render_xlsx")
    except Exception as exc:  # noqa: BLE001
        logger.warning("auto_emit_artifacts error: %s", exc)