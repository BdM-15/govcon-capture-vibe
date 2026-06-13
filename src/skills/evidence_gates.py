"""Evidence sufficiency gates: saturation, coverage, citation grounding."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Optional

_CHUNK_CITE_RE = re.compile(r"\[chunk-[^\]]+\]", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(
    r"^(tbd|todo|n/?a|none|placeholder|pending|unknown|\.\.\.)$",
    re.IGNORECASE,
)

SATURATION_STRIKES_REQUIRED = 1


def is_placeholder_text(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    return bool(_PLACEHOLDER_RE.match(text))


def count_workspace_entities_by_type(
    workspace_dir: Path,
    entity_types: list[str],
) -> dict[str, int]:
    """Count entities in vdb_entities.json grouped by type."""
    path = Path(workspace_dir) / "vdb_entities.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    records: list[dict[str, Any]] = []
    if isinstance(raw, dict) and isinstance(raw.get("data"), list):
        records = [r for r in raw["data"] if isinstance(r, dict)]
    elif isinstance(raw, list):
        records = [r for r in raw if isinstance(r, dict)]

    wanted = {t.lower() for t in entity_types}
    counts: dict[str, int] = {}
    for record in records:
        entity_type = str(record.get("entity_type") or "").lower()
        if entity_type not in wanted:
            continue
        counts[entity_type] = counts.get(entity_type, 0) + 1
    return counts


def check_coverage_contract(
    *,
    workspace_dir: Path,
    coverage_contract: Mapping[str, Any],
    artifact: Mapping[str, Any],
) -> list[str]:
    """Deterministic coverage: required KG entities reflected in artifact or claim_gaps."""
    issues: list[str] = []
    if not coverage_contract:
        return issues

    required_types = [
        str(t).strip().lower()
        for t in (coverage_contract.get("required_entity_types") or [])
        if str(t).strip()
    ]
    rule = str(coverage_contract.get("rule") or "").strip().lower()
    artifact_path = str(coverage_contract.get("artifact_path") or "").strip()

    if not required_types:
        return issues

    inventory = count_workspace_entities_by_type(Path(workspace_dir), required_types)
    gaps = artifact.get("claim_gaps") or []
    gap_text = " ".join(str(g) for g in gaps).lower() if isinstance(gaps, list) else ""

    if rule == "one_row_per_entity":
        rows_key = str(coverage_contract.get("rows_key") or "eval_crosswalk")
        rows = artifact.get(rows_key) or []
        if not isinstance(rows, list):
            issues.append(f"{artifact_path or rows_key}: expected array at {rows_key}")
            return issues

        factor_labels = {
            str(row.get("evaluation_factor") or row.get("factor") or "").strip().lower()
            for row in rows
            if isinstance(row, dict) and str(row.get("evaluation_factor") or row.get("factor") or "").strip()
        }
        expected = sum(inventory.values())
        if expected > 0 and len(factor_labels) < expected:
            missing_estimate = expected - len(factor_labels)
            if "eval" not in gap_text and "factor" not in gap_text:
                issues.append(
                    f"coverage: workspace has ~{expected} {', '.join(required_types)} entities "
                    f"but {rows_key} has {len(factor_labels)} rows (~{missing_estimate} missing); "
                    "add rows or claim_gaps[]"
                )

    return issues


def check_citations_in_scratchpad(
    artifact_text: str,
    scratchpad_text: str,
) -> list[str]:
    """Flag chunk citations in artifact that do not appear in scratchpad."""
    issues: list[str] = []
    cites = _CHUNK_CITE_RE.findall(artifact_text or "")
    if not cites:
        return issues
    scratchpad_lc = (scratchpad_text or "").lower()
    orphan = [cite for cite in cites if cite.lower().replace("[chunk-", "") not in scratchpad_lc]
    if len(orphan) > len(cites) // 2 and len(cites) >= 3:
        issues.append(
            f"grounding: {len(orphan)} of {len(cites)} chunk citations not found in scratchpad"
        )
    return issues


def run_deterministic_audit(
    *,
    run_dir: Path,
    workspace_dir: Path,
    coverage_contract: Mapping[str, Any] | None = None,
    artifact_paths: Optional[list[Path]] = None,
) -> dict[str, Any]:
    """Tier-0 Python audit — ungameable schema/coverage/citation checks."""
    issues: list[str] = []
    run_path = Path(run_dir)
    artifacts_dir = run_path / "artifacts"
    paths = artifact_paths or []
    if not paths and artifacts_dir.is_dir():
        paths = sorted(artifacts_dir.glob("*.json")) + sorted(artifacts_dir.glob("*.md"))

    scratchpad_path = artifacts_dir / "research_scratchpad.md"
    scratchpad_text = ""
    if scratchpad_path.is_file():
        try:
            scratchpad_text = scratchpad_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass

    for path in paths:
        if not path.is_file():
            issues.append(f"missing artifact: {path.name}")
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            issues.append(f"unreadable artifact: {path.name}")
            continue

        if path.suffix == ".json":
            try:
                loaded = json.loads(text)
            except json.JSONDecodeError:
                issues.append(f"invalid JSON: {path.name}")
                continue
            if isinstance(loaded, dict) and coverage_contract:
                contract_artifact = str(coverage_contract.get("artifact_path") or "").strip()
                if contract_artifact and path.name != Path(contract_artifact).name:
                    pass
                else:
                    issues.extend(
                        check_coverage_contract(
                            workspace_dir=workspace_dir,
                            coverage_contract=coverage_contract,
                            artifact=loaded,
                        )
                    )
        issues.extend(check_citations_in_scratchpad(text, scratchpad_text))

    return {
        "tier": 0,
        "pass": not issues,
        "issues": issues,
    }