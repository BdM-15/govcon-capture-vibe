"""Best-effort artifact emitters for skill runs."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.skills.run_metadata import read_artifact_manifest, write_artifact_manifest
from src.skills.skill_models import Skill

logger = logging.getLogger(__name__)

_RENDER_STATUS_KEYS = (
    "render_status",
    "render_message",
    "render_targets",
    "render_logs",
    "render_log_excerpt",
)


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


def _clear_render_status(run_dir: Path, artifact: str) -> None:
    manifest = read_artifact_manifest(run_dir)
    entry = dict(manifest.get(artifact) or {})
    changed = False
    for key in _RENDER_STATUS_KEYS:
        if key in entry:
            entry.pop(key, None)
            changed = True
    if not changed:
        return
    if entry:
        manifest[artifact] = entry
    else:
        manifest.pop(artifact, None)
    write_artifact_manifest(run_dir, manifest)


def _mark_render_failed(
    run_dir: Path,
    artifact: str,
    *,
    message: str,
    targets: list[str],
    logs: list[str],
    excerpt: str,
) -> None:
    manifest = read_artifact_manifest(run_dir)
    entry = dict(manifest.get(artifact) or {})
    entry["render_status"] = "failed"
    if message:
        entry["render_message"] = message
    if targets:
        entry["render_targets"] = targets
    if logs:
        entry["render_logs"] = logs
    if excerpt:
        entry["render_log_excerpt"] = excerpt
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


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _money(value: Any) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "n/a"
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    if amount >= 1_000_000_000:
        return f"{sign}${amount / 1_000_000_000:,.2f}B"
    if amount >= 1_000_000:
        return f"{sign}${amount / 1_000_000:,.2f}M"
    if amount >= 1_000:
        return f"{sign}${amount / 1_000:,.1f}K"
    return f"{sign}${amount:,.0f}"


def _months(value: Any) -> str:
    try:
        return f"{float(value):.1f} months"
    except (TypeError, ValueError):
        return "n/a"


def _load_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _block_by_id(payload: dict[str, Any], block_id: str) -> dict[str, Any]:
    blocks = _as_list(_as_dict(payload.get("insights")).get("blocks"))
    for block in blocks:
        block_dict = _as_dict(block)
        if block_dict.get("id") == block_id:
            return block_dict
    return {}


def _competitive_intel_brief_markdown(payload: dict[str, Any], title: str) -> str:
    insights = _as_dict(payload.get("insights"))
    obligations = _as_dict(payload.get("obligations"))
    rate = _as_dict(obligations.get("rate_analysis"))
    ptw = _as_dict(payload.get("ptw_seed"))
    resolved = _as_dict(payload.get("resolved"))
    hierarchy = _as_dict(payload.get("hierarchy"))
    vehicle = _as_dict(payload.get("vehicle_context"))
    competitor = _as_dict(payload.get("competitor_discovery"))
    burn = _as_dict(_block_by_id(payload, "burn_posture").get("evidence"))
    award = _block_by_id(payload, "award_story")
    award_evidence = _as_dict(award.get("evidence"))
    periods = _as_list(award_evidence.get("period_of_performance_segments"))
    transactions = [item for item in _as_list(obligations.get("by_transaction")) if isinstance(item, dict)]
    option_mods = [item for item in transactions if item.get("action_type") == "G"]
    negative_mods = sorted(
        [item for item in transactions if float(item.get("amount_usd") or 0) < 0],
        key=lambda item: float(item.get("amount_usd") or 0),
    )
    latest = max(transactions, key=lambda item: str(item.get("action_date") or ""), default={})

    headline = str(insights.get("headline") or "No headline available.")
    piid = str(payload.get("input_contract_number") or resolved.get("piid") or award_evidence.get("piid") or "Unknown")
    scenario = str(resolved.get("scenario") or payload.get("scope") or "unknown")

    lines: list[str] = [
        f"# {title} Brief",
        "",
        "## Executive Snapshot",
        headline,
        "",
        f"- Contract: {piid}",
        f"- Scenario: {scenario.replace('_', ' ')}",
    ]
    parent_award_id = hierarchy.get("parent_award_id") or vehicle.get("parent_award_id")
    if parent_award_id:
        lines.append(f"- Parent vehicle: {parent_award_id}")

    lines.extend(
        [
            "",
            "## Burn Posture",
            f"- Gross obligations: {_money(burn.get('gross_obligated_usd') or obligations.get('total_obligated_usd'))}",
            f"- Net obligations: {_money(burn.get('net_obligated_usd') or obligations.get('net_obligated_usd'))}",
            f"- Monthly burn: {_money(burn.get('monthly_burn_usd') or rate.get('monthly_burn_usd'))}",
            f"- Annualized burn: {_money(burn.get('annual_burn_usd') or rate.get('annual_burn_usd'))}",
            f"- Daily burn: {_money(burn.get('daily_burn_usd') or rate.get('daily_burn_usd'))}",
            f"- PTW baseline: {_money(burn.get('recommended_ptw_baseline_usd') or ptw.get('recommended_baseline_usd'))}",
            f"- Forecast expiration: {burn.get('pop_end_potential') or rate.get('forecast_expiration_date') or 'n/a'}",
            "",
            "## Award Story",
            str(award.get("summary") or "No award-story summary available.").replace(" -> ", " to "),
            "",
        ]
    )
    for period in periods:
        period_dict = _as_dict(period)
        label = str(period_dict.get("label") or period_dict.get("raw_label") or "Period")
        start = period_dict.get("pop_start_date") or period_dict.get("estimated_start") or "n/a"
        end = period_dict.get("pop_end_date") or period_dict.get("estimated_end") or "n/a"
        lines.append(
            "- "
            f"{label}: {start} to {end}; "
            f"{_money(period_dict.get('obligated_usd'))} obligated; "
            f"{_money(period_dict.get('monthly_rate_usd'))}/month; "
            f"{_months(period_dict.get('months'))}."
        )

    lines.extend(["", "## Influential Points"])
    if option_mods:
        mods = ", ".join(str(item.get("modification_number") or item.get("action_date")) for item in option_mods)
        lines.append(f"- Option exercise pattern: {mods} carry the base/option-year funding story.")
    if negative_mods:
        mod = negative_mods[0]
        lines.append(
            "- Deobligation posture: "
            f"{mod.get('modification_number') or 'unknown mod'} on {mod.get('action_date') or 'unknown date'} "
            f"moved {_money(mod.get('amount_usd'))}."
        )
    if latest:
        lines.append(
            "- Latest action: "
            f"{latest.get('modification_number') or 'initial award'} on {latest.get('action_date') or 'unknown date'} "
            f"for {_money(latest.get('amount_usd'))}; "
            f"{latest.get('modification_description') or 'no description'}"
        )
    if vehicle:
        lines.append(
            "- Parent vehicle scale: "
            f"{vehicle.get('child_order_count') or 0} child orders; "
            f"{_money(vehicle.get('net_obligated_usd'))} net obligations."
        )
    if competitor:
        awardee_count = int(competitor.get("parent_vehicle_awardee_count") or 0)
        order_holder_count = int(competitor.get("order_holder_count") or 0)
        awardee_word = "awardee" if awardee_count == 1 else "awardees"
        holder_word = "holder" if order_holder_count == 1 else "holders"
        lines.append(
            "- Competitive context: "
            f"{competitor.get('completeness_status') or 'unknown'} roster confidence; "
            f"{awardee_count} parent {awardee_word}; "
            f"{order_holder_count} order {holder_word}."
        )
    warnings = _as_list(payload.get("warnings"))
    if warnings:
        lines.extend(f"- Warning: {warning}" for warning in warnings)
    else:
        lines.append("- Warnings: none reported by the collector.")
    return "\n".join(lines).strip() + "\n"


def _brief_source_path(
    skill: Skill,
    artifacts_dir: Path,
    profile: dict[str, object],
    base: str,
    title: str,
) -> Path | None:
    if skill.name != "competitive-intel":
        return None
    for source in _xlsx_source_paths(skill, artifacts_dir, profile):
        payload = _load_json(source)
        if isinstance(payload, dict) and payload.get("obligations"):
            out = artifacts_dir / f"{base}_brief.md"
            out.write_text(_competitive_intel_brief_markdown(payload, title), encoding="utf-8")
            return out
    return None


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

        def _run_script(prog_path: Path, args: list[str], out_name: str) -> dict[str, Any]:
            stdout_name = f"{out_name}.stdout.txt"
            stderr_name = f"{out_name}.stderr.txt"
            try:
                proc = subprocess.run(
                    [sys.executable, str(prog_path)] + args,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=120,
                )
            except Exception as exc:  # noqa: BLE001
                (tool_outputs_dir / stdout_name).write_text("", encoding="utf-8")
                (tool_outputs_dir / stderr_name).write_text(str(exc), encoding="utf-8")
                return {
                    "ok": False,
                    "message": str(exc),
                    "log_files": [stdout_name, stderr_name],
                    "excerpt": str(exc),
                }
            (tool_outputs_dir / stdout_name).write_text(proc.stdout or "", encoding="utf-8")
            (tool_outputs_dir / stderr_name).write_text(proc.stderr or "", encoding="utf-8")
            message = (proc.stderr or proc.stdout or "").strip()
            if not message and proc.returncode != 0:
                message = f"Renderer exited with code {proc.returncode}"
            return {
                "ok": proc.returncode == 0,
                "message": message,
                "log_files": [stdout_name, stderr_name],
                "excerpt": (proc.stderr or proc.stdout or "").strip()[:1200],
            }

        docx_script = renderers_dir / "render_docx.py"
        if "docx" in formats and docx_script.is_file():
            docx_input = _brief_source_path(skill, artifacts_dir, profile, base, title) or report_md
            if docx_input != report_md:
                labels[docx_input.name] = f"{title} Brief Source"
            out_docx = artifacts_dir / f"{base}_brief.docx"
            args = [
                "--input",
                str(docx_input),
                "--output",
                str(out_docx),
                "--metadata",
                f"title={title} Brief",
            ]
            ref = skill_dir / "assets" / "reference.docx"
            if ref.is_file():
                args.extend(["--reference", str(ref)])
            result = _run_script(docx_script, args, "render_docx")
            if out_docx.is_file():
                labels[out_docx.name] = f"{title} Brief"
                _clear_render_status(Path(run_dir), docx_input.name)
            else:
                _mark_render_failed(
                    Path(run_dir),
                    docx_input.name,
                    message=result["message"] or f"No Studio deliverable emitted for {out_docx.name}",
                    targets=[out_docx.name],
                    logs=list(result["log_files"]),
                    excerpt=str(result["excerpt"] or ""),
                )

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
                result = _run_script(xlsx_script, args, f"render_xlsx_{stem}")
                if out_xlsx.is_file():
                    labels[out_xlsx.name] = f"{title} Workbook"
                    _clear_render_status(Path(run_dir), xlsx_source.name)
                else:
                    _mark_render_failed(
                        Path(run_dir),
                        xlsx_source.name,
                        message=result["message"] or f"No Studio deliverable emitted for {out_xlsx.name}",
                        targets=[out_xlsx.name],
                        logs=list(result["log_files"]),
                        excerpt=str(result["excerpt"] or ""),
                    )
        _set_display_names(Path(run_dir), labels)
    except Exception as exc:  # noqa: BLE001
        logger.warning("auto_emit_artifacts error: %s", exc)
