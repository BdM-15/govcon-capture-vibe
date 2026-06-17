"""Qualitative document-tree audit (epic rubric, n=20)."""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.snapshot_workspace_kg import _load_json, _parse_processing_log, _records, _workspace_path

STRUCTURAL_TYPES = ("document", "document_section", "evaluation_factor", "work_scope_item")
UP_EDGE_TYPES = {"CHILD_OF", "REFERENCES", "RELATED_TO"}
SEED = 20260616


def _rel_token(record: dict[str, Any]) -> str:
    keywords = str(record.get("keywords") or "").strip()
    if keywords:
        return keywords.split(",")[0].strip().upper()
    content = str(record.get("content") or "").split("\n", 1)[0]
    before_tab = content.split("\t", 1)[0].strip()
    return (before_tab.split()[0] if before_tab else "UNKNOWN").upper()


def _build_graph(relationships: list[dict[str, Any]]) -> dict[str, list[tuple[str, str]]]:
    parents: dict[str, list[tuple[str, str]]] = defaultdict(list)
    children: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for rel in relationships:
        src = str(rel.get("src_id") or "")
        tgt = str(rel.get("tgt_id") or "")
        if not src or not tgt:
            continue
        token = _rel_token(rel)
        if token in {"CHILD_OF", "CONTAINS"} or "CHILD" in token:
            parents[src].append((tgt, token))
            children[tgt].append((src, token))
        elif token in UP_EDGE_TYPES:
            parents[src].append((tgt, token))
            children[tgt].append((src, token))
    return {"parents": parents, "children": children}


def _entity_types_from_log(workspace_path: Path) -> dict[str, str]:
    distribution = _parse_processing_log(workspace_path).get("entity_type_distribution_neo4j") or {}
    return distribution  # type name -> count only; need per-entity from Neo4j


def _entity_types_neo4j(workspace: str) -> dict[str, str]:
    try:
        from src.core import get_settings
        from src.inference.neo4j_graph_io import Neo4jGraphIO

        settings = get_settings()
        if not settings.neo4j_password:
            return {}
        io = Neo4jGraphIO(
            uri=settings.neo4j_uri,
            username=settings.neo4j_username,
            password=settings.neo4j_password,
            database=settings.neo4j_database,
            workspace=workspace,
        )
        query = f"""
        MATCH (n:`{workspace}`)
        RETURN n.entity_id AS name, n.entity_type AS type
        """
        from src.inference.neo4j_graph_io import run_projected_query

        rows = run_projected_query(io.driver, io.database, query, lambda r: r.data())
        return {
            str(row["name"]): str(row.get("type") or "unknown").lower()
            for row in rows
            if row.get("name")
        }
    except Exception:
        return {}


def _ancestors(name: str, parents: dict[str, list[tuple[str, str]]], limit: int = 8) -> list[str]:
    chain = [name]
    current = name
    seen = {name}
    for _ in range(limit):
        ups = parents.get(current, [])
        if not ups:
            break
        parent = ups[0][0]
        if parent in seen:
            break
        chain.append(parent)
        seen.add(parent)
        current = parent
    return chain


def _chunk_snippet(workspace_path: Path, chunk_id: str) -> str:
    chunks_path = workspace_path / "kv_store_text_chunks.json"
    if not chunks_path.exists():
        return ""
    payload = _load_json(chunks_path)
    if isinstance(payload, dict):
        record = payload.get(chunk_id, {})
        if isinstance(record, dict):
            return str(record.get("content") or "")[:500]
    return ""


def _entity_chunk_map(entities: list[dict[str, Any]]) -> dict[str, str]:
    return {
        str(e.get("entity_name")): str(e.get("source_id") or "")
        for e in entities
        if e.get("entity_name")
    }


def _score_sample(
    name: str,
    etype: str,
    parents: dict[str, list[tuple[str, str]]],
    type_by_name: dict[str, str],
    chunk_text: str,
) -> tuple[int, str]:
    chain = _ancestors(name, parents)
    chain_types = [type_by_name.get(node, "unknown") for node in chain]

    if etype in {"evaluation_factor", "proposal_instruction"} and not any(
        t in {"document", "document_section", "proposal_volume"} for t in chain_types[1:]
    ):
        if not parents.get(name):
            return 0, "no upstream parent edge"
        return 1, f"weak tree: chain types {chain_types}"

    if etype == "work_scope_item":
        if not parents.get(name):
            return 0, "work_scope_item has no parent"
        if "document_section" not in chain_types and "document" not in chain_types:
            return 1, f"parent chain lacks section/doc: {chain[:4]}"

    if etype == "document_section":
        if "document" not in chain_types:
            if not parents.get(name):
                return 1, "top-level section (no document parent)"
            return 1, f"no document ancestor in {chain[:4]}"

    if etype == "document":
        return 2, "root document node"

    name_in_chunk = name.lower()[:40] in chunk_text.lower() if chunk_text else True
    if not name_in_chunk and chunk_text:
        return 1, "name not found verbatim in source chunk snippet"

    if len(chain) >= 2:
        return 2, f"chain ok: {' -> '.join(chain[:4])}"
    if parents.get(name):
        return 1, f"short chain: {' -> '.join(chain)}"
    return 0, "isolated node"


def run_tree_audit(workspace: str) -> dict[str, Any]:
    workspace_path = _workspace_path(workspace)
    entities = _records(_load_json(workspace_path / "vdb_entities.json"))
    relationships = _records(_load_json(workspace_path / "vdb_relationships.json"))
    graph = _build_graph(relationships)
    parents = graph["parents"]

    type_by_name = _entity_types_neo4j(workspace_path.name)
    if not type_by_name:
        for entity in entities:
            name = str(entity.get("entity_name") or "")
            etype = str(entity.get("entity_type") or "").lower()
            if name and etype and etype != "unknown":
                type_by_name[name] = etype
    if not type_by_name:
        raise RuntimeError(
            "Entity types missing — run tools/sync_vdb_entity_metadata.py <workspace> or set NEO4J_PASSWORD"
        )

    by_type: dict[str, list[str]] = defaultdict(list)
    for name, etype in type_by_name.items():
        if etype in STRUCTURAL_TYPES:
            by_type[etype].append(name)

    rng = random.Random(SEED)
    samples: list[dict[str, Any]] = []
    for etype in STRUCTURAL_TYPES:
        pool = sorted(by_type.get(etype, []))
        if not pool:
            continue
        picks = (
            pool
            if len(pool) <= 5
            else rng.sample(pool, 5)
        )
        chunk_map = _entity_chunk_map(entities)
        for name in picks:
            chunk_id = chunk_map.get(name, "")
            chunk_text = _chunk_snippet(workspace_path, chunk_id) if chunk_id else ""
            score, reason = _score_sample(name, etype, parents, type_by_name, chunk_text)
            samples.append(
                {
                    "entity_name": name,
                    "entity_type": etype,
                    "score": score,
                    "reason": reason,
                    "ancestor_chain": _ancestors(name, parents),
                    "source_chunk": chunk_id,
                }
            )

    scores = [s["score"] for s in samples]
    scored_2 = scores.count(2)
    scored_1 = scores.count(1)
    scored_0 = scores.count(0)
    total = len(scores) or 1
    pass_threshold = scored_2 / total >= 0.70
    factor_zeros = [
        s for s in samples
        if s["entity_type"] in {"evaluation_factor", "proposal_instruction"} and s["score"] == 0
    ]
    passed = pass_threshold and not factor_zeros

    return {
        "workspace": workspace_path.name,
        "sample_seed": SEED,
        "sample_count": len(samples),
        "scored_2": scored_2,
        "scored_1": scored_1,
        "scored_0": scored_0,
        "pass_rate_scored_2": round(scored_2 / total, 3),
        "pass": passed,
        "failures": [
            {"entity_name": s["entity_name"], "entity_type": s["entity_type"], "reason": s["reason"]}
            for s in samples
            if s["score"] == 0
        ],
        "samples": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_tree_audit(args.workspace)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "samples"}, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())