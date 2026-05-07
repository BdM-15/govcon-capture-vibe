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


_PRODUCT_PROFILES: dict[str, dict[str, object]] = {
    "competitive-intel": {
        "base": "competitive_intel",
        "label": "Competitive Intel",
        "xlsx_sources": ["competitive_intel_obligation.json", "competitive_intel.json"],
    },
    "compliance-auditor": {
        "base": "compliance_audit",
        "label": "Compliance Audit",
        "xlsx_sources": ["compliance_audit.json"],
    },
    "proposal-generator": {
        "base": "proposal_draft",
        "label": "Proposal Draft",
        "xlsx_sources": ["proposal_draft.json"],
    },
    "price-to-win": {
        "base": "price_to_win",
        "label": "Price To Win",
        "xlsx_sources": ["price_to_win.json", "ptw_ffp.json", "ptw_lh.json", "ptw_cr.json"],
    },
    "oci-sweeper": {
        "base": "oci_sweep",
        "label": "OCI Sweep",
        "xlsx_sources": ["oci_sweep.json"],
    },
    "ot-prototype-strategist": {
        "base": "ot_prototype_strategy",
        "label": "OT Prototype Strategy",
        "xlsx_sources": ["ot_prototype_strategy.json", "ot_strategy.json"],
    },
    "rfp-reverse-engineer": {
        "base": "rfp_reverse_engineering",
        "label": "RFP Reverse Engineering",
        "xlsx_sources": ["rfp_reverse_engineering.json", "rfp_reverse_engineer.json"],
    },
    "subcontractor-sow-builder": {
        "base": "subcontractor_sow",
        "label": "Subcontractor SOW",
        "xlsx_sources": ["subcontractor_sow.json"],
    },
    "workload-analyzer": {
        "base": "workload_analysis",
        "label": "Workload Analysis",
        "xlsx_sources": ["workload_analysis.json", "workload_handoff.json"],
    },
    "data-analyzer": {
        "base": "data_analysis",
        "label": "Data Analysis",
        "xlsx_sources": ["data_analysis.json"],
    },
    "grill-me-govcon": {"base": "govcon_grill", "label": "GovCon Grill"},
    "grill-me-bid-strategy": {"base": "bid_strategy_grill", "label": "Bid Strategy Grill"},
    "grill-me-capture": {"base": "capture_grill", "label": "Capture Grill"},
    "grill-me-proposal": {"base": "proposal_grill", "label": "Proposal Grill"},
    "grill-me-ptw": {"base": "ptw_grill", "label": "PTW Grill"},
}


def _display_title(skill: Skill) -> str:
    return " ".join(part.capitalize() for part in skill.name.replace("_", "-").split("-"))


def _profile(skill: Skill) -> dict[str, object]:
    profile = dict(_PRODUCT_PROFILES.get(skill.name) or {})
    profile.setdefault("base", skill.name.replace("-", "_"))
    profile.setdefault("label", _display_title(skill))
    return profile


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
        return {"md", "json", "docx", "xlsx"}
    if isinstance(raw, str):
        values = [part.strip().lower() for part in raw.split(",")]
    elif isinstance(raw, list):
        values = [str(part).strip().lower() for part in raw]
    else:
        return {"md", "json"}
    formats = {value for value in values if value in {"html", "md", "json", "docx", "xlsx"}}
    return formats or {"md", "json", "docx", "xlsx"}


def _metadata_xlsx_sources(skill: Skill) -> list[str]:
    raw = (skill.frontmatter.metadata or {}).get("auto_emit_xlsx_source")
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _safe_artifact_path(artifacts_dir: Path, rel: str) -> Path | None:
    candidate = (artifacts_dir / rel).resolve()
    artifacts_root = artifacts_dir.resolve()
    if candidate == artifacts_root:
        return None
    try:
        candidate.relative_to(artifacts_root)
    except ValueError:
        return None
    return candidate


def _xlsx_source_paths(skill: Skill, artifacts_dir: Path, profile: dict[str, object]) -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    configured = _metadata_xlsx_sources(skill)
    profiled = [str(item) for item in profile.get("xlsx_sources", []) if str(item).strip()]
    discovered = [path.name for path in sorted(artifacts_dir.glob("*.json")) if path.name != "report.json"]
    for rel in configured + profiled + discovered:
        candidate = _safe_artifact_path(artifacts_dir, rel)
        if candidate is None or not candidate.is_file() or candidate.suffix.lower() != ".json":
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        out.append(candidate)
    return out


def _safe_output_stem(stem: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in stem).strip("._-")
    return cleaned or "artifact"


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

        profile = _profile(skill)
        base = _safe_output_stem(str(profile["base"]))
        title = str(profile["label"])

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

        def _run_script(prog_path: Path, args: list[str], out_name: str) -> bool:
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
                return False
            (tool_outputs_dir / f"{out_name}.stdout.txt").write_text(proc.stdout or "", encoding="utf-8")
            (tool_outputs_dir / f"{out_name}.stderr.txt").write_text(proc.stderr or "", encoding="utf-8")
            return proc.returncode == 0

        docx_script = renderers_dir / "render_docx.py"
        if "docx" in formats and docx_script.is_file():
            out_docx = artifacts_dir / f"{base}_brief.docx"
            args = [
                "--input",
                str(report_md),
                "--output",
                str(out_docx),
                "--metadata",
                f"title={title} Brief",
            ]
            ref = skill_dir / "assets" / "reference.docx"
            if ref.is_file():
                args.extend(["--reference", str(ref)])
            _run_script(docx_script, args, "render_docx")
            if out_docx.is_file():
                labels[out_docx.name] = f"{title} Brief"

        xlsx_script = renderers_dir / "render_xlsx.py"
        if "xlsx" in formats and xlsx_script.is_file():
            for xlsx_source in _xlsx_source_paths(skill, artifacts_dir, profile):
                stem = _safe_output_stem(xlsx_source.stem)
                out_xlsx = artifacts_dir / f"{stem}.xlsx"
                if out_xlsx == xlsx_source:
                    continue
                args = [
                    "--input",
                    str(xlsx_source),
                    "--output",
                    str(out_xlsx),
                    "--title",
                    f"{title} Workbook",
                ]
                _run_script(xlsx_script, args, f"render_xlsx_{stem}")
                if out_xlsx.is_file():
                    labels[out_xlsx.name] = f"{title} Workbook"
        _set_display_names(Path(run_dir), labels)
    except Exception as exc:  # noqa: BLE001
        logger.warning("auto_emit_artifacts error: %s", exc)
