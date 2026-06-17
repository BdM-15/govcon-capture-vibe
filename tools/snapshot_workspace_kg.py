"""Snapshot workspace KG quality metrics (Phase 0 epic + MinerU regression).

Usage:
    .venv\\Scripts\\python.exe tools/snapshot_workspace_kg.py --workspace mcpp_rfp_t2 --output artifacts/mcpp_rfp_t2_snapshot.json
    .venv\\Scripts\\python.exe tools/snapshot_workspace_kg.py --workspace mcpp_rfp_t2 --compare-with mcpp_rfp
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import logging

from src.ontology.schema import VALID_RELATIONSHIP_TYPES, normalize_relationship_type

logging.getLogger("src.ontology.schema").setLevel(logging.ERROR)

STRUCTURAL_ENTITY_TYPES = (
    "document",
    "document_section",
    "evaluation_factor",
    "proposal_instruction",
    "work_scope_item",
)

EXTRACTION_TIME_REL_TYPES = VALID_RELATIONSHIP_TYPES - {
    "REQUIRES",
    "ENABLED_BY",
    "RESPONSIBLE_FOR",
}


def _load_json(path: Path) -> Any:
    with open(path, encoding="utf-8-sig") as handle:
        return json.load(handle)


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and "data" in payload:
        payload = payload["data"]
    if isinstance(payload, dict):
        payload = list(payload.values())
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _workspace_path(workspace: str) -> Path:
    candidate = Path(workspace)
    if candidate.is_dir():
        return candidate
    return PROJECT_ROOT / "rag_storage" / workspace


def _parse_relationship_first_token(record: dict[str, Any]) -> str:
    keywords = str(record.get("keywords") or "").strip()
    if keywords:
        return keywords.split(",")[0].strip().upper()

    content = str(record.get("content") or "").strip()
    if not content:
        return "UNKNOWN"
    first_line = content.split("\n", 1)[0]
    before_tab = first_line.split("\t", 1)[0].strip()
    if not before_tab:
        return "UNKNOWN"
    return before_tab.split()[0].upper()


def _entity_description(record: dict[str, Any]) -> str:
    if record.get("description"):
        return str(record["description"])
    content = str(record.get("content") or "")
    if "\n" in content:
        return content.split("\n", 1)[1].strip()
    return content.strip()


def _parse_processing_log(workspace_path: Path) -> dict[str, Any]:
    log_path = workspace_path / f"{workspace_path.name}_processing.log"
    if not log_path.exists():
        return {}

    text = log_path.read_text(encoding="utf-8", errors="replace")
    blocks = text.split("📊 Entity Type Distribution")
    tail = blocks[-1] if blocks else ""
    rel_marker = "📊 Relationship Type Distribution"
    if rel_marker in tail:
        tail = tail.split(rel_marker, 1)[0]
    entity_type_distribution: dict[str, int] = {}
    for match in re.finditer(
        r"^\d{4}-\d{2}-\d{2} .*?\|\s+(\S+)\s+:\s+(\d+)\s*$",
        tail,
        flags=re.MULTILINE,
    ):
        entity_type_distribution[match.group(1)] = int(match.group(2))

    stats: dict[str, Any] = {
        "entity_type_distribution_neo4j": entity_type_distribution,
    }

    final_entities = re.findall(r"Final Neo4j Entities:\s+(\d+)", text)
    final_relationships = re.findall(r"Final Neo4j Relationships:\s+(\d+)", text)
    if final_entities:
        stats["final_neo4j_entities"] = int(final_entities[-1])
    if final_relationships:
        stats["final_neo4j_relationships"] = int(final_relationships[-1])

    orphan_match = re.findall(r"Found (\d+) truly orphaned entities in Neo4j", text)
    if orphan_match:
        stats["orphan_count_neo4j_last_pass"] = int(orphan_match[-1])

    infer_lm = re.findall(r"→ L↔M Links: (\d+) relationships", text)
    if infer_lm:
        stats["infer_lm_links_added"] = int(infer_lm[-1])

    resolve_orphans = re.findall(
        r"-> Orphan Resolution: (\d+) relationships \(from (\d+) orphans\)",
        text,
    )
    if resolve_orphans:
        added, orphan_pool = resolve_orphans[-1]
        stats["resolve_orphans_added"] = int(added)
        stats["resolve_orphans_pool"] = int(orphan_pool)

    pp_added = re.findall(r"Post-Processing Added Rels:\s+(\d+)", text)
    if pp_added:
        stats["post_processing_added_rels"] = int(pp_added[-1])

    return stats


def _try_neo4j_orphan_count(workspace_name: str) -> int | None:
    try:
        from src.core import get_settings
        from src.inference.neo4j_graph_io import Neo4jGraphIO

        settings = get_settings()
        if not settings.neo4j_password:
            return None
        io = Neo4jGraphIO(
            uri=settings.neo4j_uri,
            username=settings.neo4j_username,
            password=settings.neo4j_password,
            database=settings.neo4j_database,
            workspace=workspace_name,
        )
        return len(io.get_orphaned_entity_ids())
    except Exception:
        return None


def _count_doc_status(workspace_path: Path) -> dict[str, Any]:
    status_path = workspace_path / "kv_store_doc_status.json"
    if not status_path.exists():
        return {"doc_count": 0, "by_status": {}, "by_suffix": {}}
    records = _records(_load_json(status_path))
    by_status: Counter[str] = Counter()
    by_suffix: Counter[str] = Counter()
    for record in records:
        file_path = str(record.get("file_path") or record.get("content_summary") or "")
        suffix = Path(file_path).suffix.lower() or "unknown"
        status = str(record.get("status") or "unknown").lower()
        by_status[status] += 1
        by_suffix[suffix] += 1
    return {
        "doc_count": len(records),
        "by_status": dict(by_status),
        "by_suffix": dict(by_suffix),
    }


def _entities_per_chunk(entities: list[dict[str, Any]], chunk_count: int) -> dict[str, Any]:
    by_chunk: Counter[str] = Counter()
    for entity in entities:
        source_id = str(entity.get("source_id") or "unknown")
        by_chunk[source_id] += 1
    counts = list(by_chunk.values()) if by_chunk else [0]
    return {
        "entities_per_chunk_mean": round(sum(counts) / max(chunk_count, 1), 2),
        "entities_per_chunk_median": sorted(counts)[len(counts) // 2],
        "entities_per_chunk_p90": sorted(counts)[int(len(counts) * 0.9)] if counts else 0,
        "chunks_with_entities": len(by_chunk),
    }


def _relationship_keyword_stats(relationships: list[dict[str, Any]]) -> dict[str, Any]:
    first_tokens: Counter[str] = Counter()
    canonical: Counter[str] = Counter()
    rogue: Counter[str] = Counter()

    for rel in relationships:
        raw = _parse_relationship_first_token(rel)
        first_tokens[raw] += 1
        normalized = normalize_relationship_type(raw, fallback="RELATED_TO")
        canonical[normalized] += 1
        if raw not in EXTRACTION_TIME_REL_TYPES and raw != normalized:
            rogue[raw] += 1

    total = sum(first_tokens.values()) or 1
    rogue_share = round(sum(rogue.values()) / total, 4)
    guides_vdb_count = canonical.get("GUIDES", 0)

    return {
        "relationship_keywords_first_token": dict(first_tokens.most_common(30)),
        "relationship_keywords_canonical": dict(canonical.most_common(30)),
        "rogue_first_token_counts": dict(rogue.most_common(20)),
        "rogue_first_token_share": rogue_share,
        "guides_vdb_count": guides_vdb_count,
    }


def _orphan_rate_vdb(entities: list[dict[str, Any]], relationships: list[dict[str, Any]]) -> dict[str, Any]:
    names = {
        str(entity.get("entity_name") or "").lower()
        for entity in entities
        if entity.get("entity_name")
    }
    connected: set[str] = set()
    for rel in relationships:
        for key in ("src_id", "tgt_id"):
            value = rel.get(key)
            if value:
                connected.add(str(value).lower())
    orphans = names - connected
    rate = round(len(orphans) / len(names), 4) if names else 0.0
    return {
        "orphan_rate_vdb": rate,
        "orphaned_entities_vdb": len(orphans),
        "total_entities_vdb": len(names),
    }


def _entity_name_index(entities: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for entity in entities:
        name = str(entity.get("entity_name") or "").strip()
        if not name:
            continue
        key = name.lower()
        index[key] = {
            "entity_name": name,
            "description_chars": len(_entity_description(entity)),
            "source_id": entity.get("source_id"),
            "file_path": entity.get("file_path"),
        }
    return index


def _compare_workspaces(
    baseline_index: dict[str, dict[str, Any]],
    candidate_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    baseline_names = set(baseline_index)
    candidate_names = set(candidate_index)
    shared = baseline_names & candidate_names
    only_baseline = baseline_names - candidate_names
    only_candidate = candidate_names - baseline_names

    description_drift = 0
    for name in shared:
        base_len = baseline_index[name]["description_chars"]
        cand_len = candidate_index[name]["description_chars"]
        if base_len and cand_len:
            ratio = abs(cand_len - base_len) / max(base_len, cand_len)
            if ratio > 0.35:
                description_drift += 1

    return {
        "shared_entity_names": len(shared),
        "shared_entity_share_of_baseline": round(len(shared) / max(len(baseline_names), 1), 4),
        "shared_entity_share_of_candidate": round(len(shared) / max(len(candidate_names), 1), 4),
        "only_in_baseline": len(only_baseline),
        "only_in_candidate": len(only_candidate),
        "net_new_entity_share": round(len(only_candidate) / max(len(candidate_names), 1), 4),
        "shared_entities_with_description_drift_gt_35pct": description_drift,
        "sample_only_in_candidate": sorted(only_candidate)[:15],
        "sample_only_in_baseline": sorted(only_baseline)[:15],
    }


def build_workspace_snapshot(
    workspace: str,
    *,
    compare_with: str | None = None,
) -> dict[str, Any]:
    workspace_path = _workspace_path(workspace)
    if not workspace_path.exists():
        raise FileNotFoundError(f"Workspace not found: {workspace_path}")

    entities = _records(_load_json(workspace_path / "vdb_entities.json"))
    relationships = _records(_load_json(workspace_path / "vdb_relationships.json"))

    chunks_path = workspace_path / "kv_store_text_chunks.json"
    chunk_count = len(_records(_load_json(chunks_path))) if chunks_path.exists() else 0

    log_stats = _parse_processing_log(workspace_path)
    entity_type_distribution = log_stats.get("entity_type_distribution_neo4j") or {}
    if not entity_type_distribution:
        entity_type_distribution = Counter(
            str(entity.get("entity_type") or "unknown").lower() for entity in entities
        )
        entity_type_distribution = dict(entity_type_distribution)

    total_entities = len(entities)
    concept_unknown = (
        entity_type_distribution.get("concept", 0)
        + entity_type_distribution.get("unknown", 0)
    )
    concept_unknown_share = round(concept_unknown / max(total_entities, 1), 4)

    structural_context = {
        key: entity_type_distribution.get(key, 0) for key in STRUCTURAL_ENTITY_TYPES
    }

    orphan_vdb = _orphan_rate_vdb(entities, relationships)
    rel_stats = _relationship_keyword_stats(relationships)
    doc_status = _count_doc_status(workspace_path)
    yield_stats = _entities_per_chunk(entities, chunk_count)

    neo4j_orphans = _try_neo4j_orphan_count(workspace_path.name)
    orphan_count_neo4j = neo4j_orphans
    if orphan_count_neo4j is None:
        orphan_count_neo4j = log_stats.get("orphan_count_neo4j_last_pass")

    snapshot: dict[str, Any] = {
        "workspace": workspace_path.name,
        "workspace_path": str(workspace_path),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "chunk_count": chunk_count,
        "doc_count": doc_status["doc_count"],
        "doc_status": doc_status,
        "total_entities_vdb": total_entities,
        "total_relationships_vdb": len(relationships),
        "entities_per_chunk": yield_stats,
        "orphan_rate_vdb": orphan_vdb["orphan_rate_vdb"],
        "orphaned_entities_vdb": orphan_vdb["orphaned_entities_vdb"],
        "orphan_count_neo4j": orphan_count_neo4j,
        "entity_type_distribution": entity_type_distribution,
        "concept_unknown_share": concept_unknown_share,
        "structural_context": structural_context,
        **rel_stats,
        "post_processor_last_stats": {
            key: log_stats[key]
            for key in (
                "final_neo4j_entities",
                "final_neo4j_relationships",
                "infer_lm_links_added",
                "resolve_orphans_added",
                "resolve_orphans_pool",
                "post_processing_added_rels",
            )
            if key in log_stats
        },
        "appendix_counts_only": {
            "total_entities_vdb": total_entities,
            "total_relationships_vdb": len(relationships),
            "final_neo4j_entities": log_stats.get("final_neo4j_entities"),
            "final_neo4j_relationships": log_stats.get("final_neo4j_relationships"),
        },
    }

    entity_index = _entity_name_index(entities)
    snapshot["entity_name_uniqueness"] = {
        "unique_names": len(entity_index),
        "duplicate_name_collisions": total_entities - len(entity_index),
    }

    if compare_with:
        baseline_path = _workspace_path(compare_with)
        baseline_entities = _records(_load_json(baseline_path / "vdb_entities.json"))
        baseline_index = _entity_name_index(baseline_entities)
        comparison = _compare_workspaces(baseline_index, entity_index)
        baseline_chunks = len(_records(_load_json(baseline_path / "kv_store_text_chunks.json")))
        comparison["chunk_delta"] = chunk_count - baseline_chunks
        comparison["chunk_ratio"] = round(chunk_count / max(baseline_chunks, 1), 3)
        comparison["entity_delta"] = total_entities - len(baseline_entities)
        comparison["entity_ratio"] = round(total_entities / max(len(baseline_entities), 1), 3)
        comparison["relationship_delta"] = len(relationships) - len(
            _records(_load_json(baseline_path / "vdb_relationships.json"))
        )
        comparison["explosion_attribution"] = _explosion_attribution(
            chunk_ratio=comparison["chunk_ratio"],
            entity_ratio=comparison["entity_ratio"],
            net_new_share=comparison["net_new_entity_share"],
            shared_share=comparison["shared_entity_share_of_candidate"],
        )
        snapshot["comparison_with"] = compare_with
        snapshot["comparison"] = comparison

    return snapshot


def _explosion_attribution(
    *,
    chunk_ratio: float,
    entity_ratio: float,
    net_new_share: float,
    shared_share: float,
) -> dict[str, Any]:
    """Heuristic: separate structural drivers from redundant re-extraction."""
    per_chunk_yield_ratio = round(entity_ratio / max(chunk_ratio, 0.001), 3)
    structural_driver = chunk_ratio > 1.15 and per_chunk_yield_ratio < 1.15
    redundancy_signal = net_new_share < 0.55 and shared_share > 0.4
    yield_amplification = per_chunk_yield_ratio > 1.1

    verdict_parts = []
    if structural_driver:
        verdict_parts.append("more_chunks drives most of the count delta")
    if yield_amplification:
        verdict_parts.append("higher entities-per-chunk suggests richer (or noisier) per-chunk extraction")
    if redundancy_signal:
        verdict_parts.append("high name overlap with baseline — not purely net-new concepts")
    if not verdict_parts:
        verdict_parts.append("mixed drivers — review structural_context and rogue keyword share")

    return {
        "chunk_ratio": chunk_ratio,
        "entity_ratio": entity_ratio,
        "per_chunk_yield_ratio": per_chunk_yield_ratio,
        "structural_chunk_driver": structural_driver,
        "per_chunk_yield_amplification": yield_amplification,
        "overlap_redundancy_signal": redundancy_signal,
        "summary": "; ".join(verdict_parts),
    }


def _print_summary(snapshot: dict[str, Any]) -> None:
    print(f"\n{'=' * 72}")
    print(f"  KG SNAPSHOT: {snapshot['workspace']}")
    print(f"{'=' * 72}")
    print(f"  Chunks: {snapshot['chunk_count']}  |  Docs: {snapshot['doc_count']}")
    print(
        f"  Entities (VDB): {snapshot['total_entities_vdb']}  |  "
        f"Relationships (VDB): {snapshot['total_relationships_vdb']}"
    )
    print(
        f"  Orphan rate (VDB): {snapshot['orphan_rate_vdb']:.1%}  |  "
        f"Neo4j orphans: {snapshot.get('orphan_count_neo4j', 'n/a')}"
    )
    print(
        f"  concept+unknown share: {snapshot['concept_unknown_share']:.1%}  |  "
        f"rogue keyword share: {snapshot['rogue_first_token_share']:.1%}"
    )
    print(f"  entities/chunk (mean): {snapshot['entities_per_chunk']['entities_per_chunk_mean']}")
    structural = snapshot["structural_context"]
    print(
        "  structural: "
        f"eval_factor={structural.get('evaluation_factor', 0)} "
        f"proposal_instruction={structural.get('proposal_instruction', 0)} "
        f"work_scope={structural.get('work_scope_item', 0)}"
    )

    if "comparison" in snapshot:
        comp = snapshot["comparison"]
        attr = comp.get("explosion_attribution", {})
        print(f"\n  COMPARISON vs {snapshot['comparison_with']}:")
        print(
            f"    chunks {comp['chunk_ratio']:.2f}x | entities {comp['entity_ratio']:.2f}x | "
            f"per-chunk yield {attr.get('per_chunk_yield_ratio', 'n/a')}"
        )
        print(
            f"    shared names: {comp['shared_entity_names']} "
            f"({comp['shared_entity_share_of_candidate']:.0%} of candidate)"
        )
        print(f"    net-new names: {comp['only_in_candidate']} ({comp['net_new_entity_share']:.0%})")
        print(f"    attribution: {attr.get('summary', 'n/a')}")

    pp = snapshot.get("post_processor_last_stats") or {}
    if pp:
        print(
            f"\n  Post-processor: infer_lm={pp.get('infer_lm_links_added', 'n/a')} "
            f"resolve_orphans={pp.get('resolve_orphans_added', 'n/a')} "
            f"added_rels={pp.get('post_processing_added_rels', 'n/a')}"
        )
    print(f"{'=' * 72}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Snapshot workspace KG quality metrics.")
    parser.add_argument("--workspace", required=True, help="Workspace name or rag_storage path")
    parser.add_argument("--output", type=Path, help="Write JSON snapshot to this path")
    parser.add_argument("--compare-with", help="Baseline workspace for explosion overlap analysis")
    parser.add_argument("--json", action="store_true", help="Print full JSON to stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    snapshot = build_workspace_snapshot(args.workspace, compare_with=args.compare_with)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")

    if args.json:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    else:
        _print_summary(snapshot)
        if args.output:
            print(f"Wrote {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())