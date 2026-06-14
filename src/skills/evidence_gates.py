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

SATURATION_STRIKES_REQUIRED = 2
DEFAULT_COVERAGE_MIN_RATIO = 0.8

_NON_MATERIAL_EVAL_RE = re.compile(
    r"(?:"
    r"rating\s*scale|"
    r"methodology|"
    r"relative\s+importance|"
    r"best\s+value\s+tradeoff|"
    r"past\s+performance\s+factor|"
    r"section\s*m\s*\d*\s*factor\s*weight|"
    r"evaluation\s+methodology|"
    r"ssdd|"
    r"adjectival\s+rating|"
    r"technical approach evaluation factor|"
    r"past performance evaluation factor|"
    r"management approach evaluation factor|"
    r"price\s*/?\s*cost evaluation factor|"
    r"small business participation evaluation factor|"
    r"^(?:not|somewhat|very)\s+relevant\s+rating$|"
    r"^relevant\s+rating$"
    r")",
    re.IGNORECASE,
)

_TABLE_ENTITY_RE = re.compile(r"^tb-[a-z0-9-]+$", re.IGNORECASE)
_BARE_FACTOR_RE = re.compile(r"^factor\s+\d+$", re.IGNORECASE)


def is_placeholder_text(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    return bool(_PLACEHOLDER_RE.match(text))


def is_material_eval_factor(label: Any) -> bool:
    text = str(label or "").strip()
    if not text or text.lower().startswith("entity:"):
        return False
    if _TABLE_ENTITY_RE.match(text):
        return False
    if _BARE_FACTOR_RE.match(text):
        return False
    return not _NON_MATERIAL_EVAL_RE.search(text)


def load_material_eval_entities(workspace_dir: Path) -> list[dict[str, Any]]:
    """Material evaluation_factor/subfactor entities from workspace VDB."""
    inventory = count_workspace_entities_by_type(
        workspace_dir,
        ["evaluation_factor", "subfactor"],
    )
    if not inventory:
        return []

    path = Path(workspace_dir) / "vdb_entities.json"
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    records: list[dict[str, Any]] = []
    if isinstance(raw, dict) and isinstance(raw.get("data"), list):
        records = [r for r in raw["data"] if isinstance(r, dict)]
    elif isinstance(raw, list):
        records = [r for r in raw if isinstance(r, dict)]

    entities: list[dict[str, Any]] = []
    for record in records:
        entity_type = str(record.get("entity_type") or "").strip().lower()
        if entity_type not in {"evaluation_factor", "subfactor"}:
            continue
        name = str(
            record.get("entity_name")
            or record.get("name")
            or record.get("entity_id")
            or ""
        ).strip()
        if not is_material_eval_factor(name):
            continue
        entities.append({"name": name, "entity_type": entity_type})
    return entities


def crosswalk_material_row_labels(crosswalk: list[Any]) -> set[str]:
    labels: set[str] = set()
    for row in crosswalk:
        if not isinstance(row, dict):
            continue
        label = str(row.get("evaluation_factor") or row.get("factor") or "").strip().lower()
        if label and is_material_eval_factor(label):
            labels.add(label)
    return labels


def minimum_required_crosswalk_rows(
    workspace_dir: Path | None,
    *,
    min_coverage_ratio: float = DEFAULT_COVERAGE_MIN_RATIO,
    fallback_min: int = 3,
) -> int:
    if workspace_dir is None:
        return fallback_min
    entities = load_material_eval_entities(workspace_dir)
    if not entities:
        return fallback_min
    return max(1, int(len(entities) * min_coverage_ratio))


def _claim_gaps_document_missing_factors(
    *,
    gaps: list[Any],
    missing_labels: list[str],
) -> int:
    documented = 0
    gap_texts = [str(gap or "").lower() for gap in gaps]
    for label in missing_labels:
        needle = label.lower()
        if any(needle in gap_text for gap_text in gap_texts):
            documented += 1
    return documented


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

        ratio_raw = coverage_contract.get("min_coverage_ratio")
        min_ratio = DEFAULT_COVERAGE_MIN_RATIO
        if isinstance(ratio_raw, (int, float)) and 0 < float(ratio_raw) <= 1:
            min_ratio = float(ratio_raw)

        material_entities = load_material_eval_entities(Path(workspace_dir))
        if material_entities:
            entity_names = [str(item.get("name") or "") for item in material_entities]
            factor_labels = crosswalk_material_row_labels(rows)
            expected = len(material_entities)
            min_required = max(1, int(expected * min_ratio))
            missing_labels = [
                name
                for name in entity_names
                if name.strip() and name.strip().lower() not in factor_labels
            ]
            gaps = artifact.get("claim_gaps") or []
            gap_list = gaps if isinstance(gaps, list) else []
            documented = _claim_gaps_document_missing_factors(
                gaps=gap_list,
                missing_labels=missing_labels,
            )
            effective = len(factor_labels) + documented
            if effective < min_required:
                issues.append(
                    f"coverage: workspace has {expected} material {', '.join(required_types)} "
                    f"entities but {rows_key} has {len(factor_labels)} rows "
                    f"({documented} documented in claim_gaps[]); "
                    f"need >={min_required} rows or named claim_gaps[] per missing factor"
                )
        else:
            factor_labels = {
                str(row.get("evaluation_factor") or row.get("factor") or "").strip().lower()
                for row in rows
                if isinstance(row, dict)
                and str(row.get("evaluation_factor") or row.get("factor") or "").strip()
            }
            expected = sum(inventory.values())
            if expected > 0 and len(factor_labels) < expected:
                min_required = max(1, int(expected * min_ratio))
                if len(factor_labels) < min_required and "eval" not in gap_text and "factor" not in gap_text:
                    missing_estimate = expected - len(factor_labels)
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