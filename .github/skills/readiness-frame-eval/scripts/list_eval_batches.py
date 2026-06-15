#!/usr/bin/env python3
"""List material eval factors grouped into retrieval batches (deterministic)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BATCH_SIZE = 8


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() or (parent / "app.py").is_file():
            return parent
    raise SystemExit("could not locate repo root from script path")


def _workspace_dir(name: str) -> Path:
    root = _repo_root()
    candidate = root / "rag_storage" / name.strip()
    if not candidate.is_dir():
        raise SystemExit(f"workspace not found: {candidate}")
    return candidate


def _load_material_factors(workspace_dir: Path) -> list[str]:
    sys.path.insert(0, str(_repo_root()))
    from src.skills.evidence_gates import load_material_eval_entities

    names: list[str] = []
    seen: set[str] = set()
    for entity in load_material_eval_entities(workspace_dir):
        label = str(entity.get("name") or "").strip()
        if not label:
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(label)
    names.sort(key=lambda value: value.lower())
    return names


def _chunk(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _plan_surface_queries(skill_dir: Path) -> dict[str, str]:
    plan_path = skill_dir / "references" / "plan_surfaces.json"
    if not plan_path.is_file():
        return {}
    try:
        surfaces = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    queries: dict[str, str] = {}
    for surface in surfaces:
        if not isinstance(surface, dict):
            continue
        surface_id = str(surface.get("id") or "").strip()
        query = str(surface.get("suggested_query") or "").strip()
        if surface_id and query:
            queries[surface_id] = query
    return queries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", help="Workspace name (e.g. mcpp_rfp)")
    parser.add_argument(
        "--out",
        help="Optional path to write eval_batch_manifest.json",
    )
    parser.add_argument("--batch-size", type=int, default=_BATCH_SIZE)
    args = parser.parse_args()

    workspace_dir = _workspace_dir(args.workspace)
    factors = _load_material_factors(workspace_dir)
    batches = _chunk(factors, max(1, int(args.batch_size)))
    skill_dir = Path(__file__).resolve().parents[1]
    plan_queries = _plan_surface_queries(skill_dir)

    manifest = {
        "workspace": args.workspace.strip(),
        "material_factor_count": len(factors),
        "batch_size": args.batch_size,
        "batch_count": len(batches),
        "retrieval_note": (
            "Factor inventory only. For kg_chunks, read artifacts/retrieval_plan.json and use "
            "next_step.suggested_query — one call per assistant turn. Do not invent long "
            "multi-batch queries; they trigger duplicate plan guards."
        ),
        "batches": [
            {
                "batch_id": f"eval_batch_{index + 1}",
                "factors": batch,
                "plan_surface_query": plan_queries.get(f"eval_batch_{index + 1}", ""),
            }
            for index, batch in enumerate(batches)
        ],
    }

    text = json.dumps(manifest, ensure_ascii=False, indent=2)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())