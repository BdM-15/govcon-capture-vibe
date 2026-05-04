"""Support helpers for inference algorithm orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AlgorithmRunSpec:
    """Metadata for one orchestrated algorithm run."""

    name: str
    result: list[dict[str, Any]] | Exception | None


def collect_algorithm_relationships(
    algorithm_runs: list[AlgorithmRunSpec],
    *,
    logger=None,
) -> list[dict[str, Any]]:
    """Fold algorithm outputs into one relationship list with stable logging."""
    all_relationships: list[dict[str, Any]] = []

    for algorithm_run in algorithm_runs:
        result = algorithm_run.result
        if isinstance(result, Exception):
            if logger is not None:
                logger.error(f"  ❌ {algorithm_run.name} failed: {result}")
            continue

        if result:
            all_relationships.extend(result)
            if logger is not None:
                logger.info(f"  ✅ {algorithm_run.name}: {len(result)} relationships")
            continue

        if logger is not None:
            logger.info(f"  ⏭️  {algorithm_run.name}: skipped (no applicable entities)")

    return all_relationships