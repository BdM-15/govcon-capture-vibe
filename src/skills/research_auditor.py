"""Lightweight independent auditor for research harness skill runs."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Mapping, Optional

from src.skills.evidence_gates import run_deterministic_audit

logger = logging.getLogger(__name__)


def write_audit_report(run_dir: Path, verdict: dict[str, Any]) -> Path:
    """Persist audit verdict (generator cannot write this file)."""
    path = Path(run_dir) / "artifacts" / "audit_report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


async def audit_skill_run(
    *,
    run_dir: Path,
    workspace_dir: Path,
    coverage_contract: Mapping[str, Any] | None = None,
    artifact_paths: Optional[list[Path]] = None,
    llm_audit_fn: Optional[Any] = None,
    skill_task: str = "",
    scratchpad_excerpt: str = "",
) -> dict[str, Any]:
    """Run Tier-0 deterministic audit; optional Tier-1 LLM sufficiency when wired."""
    tier0 = run_deterministic_audit(
        run_dir=run_dir,
        workspace_dir=workspace_dir,
        coverage_contract=coverage_contract,
        artifact_paths=artifact_paths,
    )
    issues = list(tier0.get("issues") or [])
    tiers_run = [0]

    if llm_audit_fn is not None and tier0.get("pass"):
        try:
            tier1 = await llm_audit_fn(
                skill_task=skill_task,
                scratchpad_excerpt=scratchpad_excerpt[:80_000],
            )
            tiers_run.append(1)
            if isinstance(tier1, dict):
                if not tier1.get("pass", True):
                    issues.extend(list(tier1.get("issues") or []))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tier-1 audit failed: %s", exc)
            issues.append(f"tier1_audit_error: {exc}")

    verdict = {
        "pass": not issues,
        "issues": issues,
        "tiers_run": tiers_run,
        "tier0": tier0,
    }
    write_audit_report(run_dir, verdict)
    return verdict