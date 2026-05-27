"""Native LightRAG ingestion regression gate reporting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_KNOWN_ANSWER_CHECKS = [
    {
        "id": "lm_traceability",
        "query": "How do Section L instructions map to Section M evaluation factors?",
        "expected_terms": ["section l", "section m", "factor 1"],
    },
    {
        "id": "multimodal_workload_table",
        "query": "What workload evidence appears in multimodal tables?",
        "expected_terms": ["workload table", "mobilization"],
    },
]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and "data" in payload:
        payload = payload["data"]
    if isinstance(payload, dict):
        payload = list(payload.values())
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _text_fields(record: dict[str, Any]) -> str:
    parts = []
    for key in (
        "content",
        "description",
        "entity_name",
        "src_id",
        "tgt_id",
        "keywords",
        "file_path",
        "full_doc_id",
    ):
        value = record.get(key)
        if value is not None:
            parts.append(str(value))
    return "\n".join(parts)


def _count_by_key(records: list[dict[str, Any]], *keys: str, uppercase: bool = False) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = None
        for key in keys:
            value = record.get(key)
            if value:
                break
        if not value:
            value = "unknown"
        values = [part.strip() for part in str(value).split(",") if part.strip()]
        for item in values or ["unknown"]:
            normalized = item.upper() if uppercase else item.lower()
            counts[normalized] = counts.get(normalized, 0) + 1
    return dict(sorted(counts.items()))


def _multimodal_evidence(corpus_records: list[dict[str, Any]]) -> dict[str, int]:
    evidence = {"tables": 0, "images": 0, "equations": 0}
    for record in corpus_records:
        text = _text_fields(record).lower()
        content_type = str(record.get("content_type") or record.get("type") or "").lower()
        entity_type = str(record.get("entity_type") or "").lower()
        if "[table]" in text or content_type == "table" or entity_type == "table":
            evidence["tables"] += 1
        if "[image]" in text or content_type == "image" or entity_type == "image":
            evidence["images"] += 1
        if "[equation]" in text or content_type in {"equation", "formula"} or entity_type in {"equation", "formula"}:
            evidence["equations"] += 1
    return evidence


def _evaluate_known_answers(
    checks: list[dict[str, Any]],
    corpus_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    corpus = "\n".join(_text_fields(record) for record in corpus_records).lower()
    results = []
    for check in checks:
        expected_terms = [str(term).lower() for term in check.get("expected_terms", [])]
        missing_terms = [term for term in expected_terms if term not in corpus]
        results.append(
            {
                "id": check.get("id", "known_answer"),
                "query": check.get("query", ""),
                "expected_terms": expected_terms,
                "missing_terms": missing_terms,
                "passed": not missing_terms,
            }
        )
    return results


def _fixture_records() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    entities = [
        {
            "entity_name": "Section L Technical Instructions",
            "entity_type": "proposal_instruction",
            "description": "Section L requires offerors to address Factor 1 technical approach.",
        },
        {
            "entity_name": "Factor 1 Technical Approach",
            "entity_type": "evaluation_factor",
            "description": "Section M Factor 1 evaluates technical approach and mobilization risk.",
        },
        {
            "entity_name": "Mobilization Requirement",
            "entity_type": "requirement",
            "description": "Contractor shall mobilize within 30 days.",
        },
        {
            "entity_name": "Monthly Status Report",
            "entity_type": "deliverable",
            "description": "CDRL A001 monthly status report.",
        },
    ]
    relationships = [
        {
            "src_id": "Section L Technical Instructions",
            "tgt_id": "Factor 1 Technical Approach",
            "keywords": "EVALUATED_BY",
            "description": "Section L instruction is evaluated under Section M Factor 1.",
        },
        {
            "src_id": "Mobilization Requirement",
            "tgt_id": "Monthly Status Report",
            "keywords": "PRODUCES",
            "description": "Mobilization status is reported in the CDRL.",
        },
    ]
    chunks = [
        {
            "content": "[TABLE] Workload table: mobilization staffing and monthly reporting by location [/TABLE]"
        },
        {
            "content": "Section L proposal instruction maps to Section M Factor 1 Technical Approach."
        },
    ]
    return entities, relationships, chunks


def _workspace_records(workspace_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    entity_path = workspace_path / "vdb_entities.json"
    relationship_path = workspace_path / "vdb_relationships.json"
    chunks_path = workspace_path / "kv_store_text_chunks.json"
    entities = _records(_load_json(entity_path)) if entity_path.exists() else []
    relationships = _records(_load_json(relationship_path)) if relationship_path.exists() else []
    chunks = _records(_load_json(chunks_path)) if chunks_path.exists() else []
    return entities, relationships, chunks


def _workspace_doc_status(workspace_path: Path) -> list[dict[str, Any]]:
    status_path = workspace_path / "kv_store_doc_status.json"
    if not status_path.exists():
        return []
    return _records(_load_json(status_path))


def _document_status_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    duplicate_records = [
        record for record in records if _is_duplicate_status_record(record)
    ]
    source_records = [
        record for record in records if not _is_duplicate_status_record(record)
    ]
    effective_records = _latest_doc_status_by_file(source_records)
    by_status = _count_by_key(effective_records, "status")
    suffix_status: dict[str, dict[str, int]] = {}
    failed_records = []
    for record in effective_records:
        file_path = str(record.get("file_path") or record.get("content_summary") or "")
        suffix = Path(file_path).suffix.lower() or "unknown"
        status = str(record.get("status") or "unknown").lower()
        suffix_counts = suffix_status.setdefault(suffix, {})
        suffix_counts[status] = suffix_counts.get(status, 0) + 1
        if status == "failed":
            failed_records.append(
                {
                    "file_path": record.get("file_path") or file_path,
                    "error_msg": record.get("error_msg") or record.get("error") or "",
                }
            )
    return {
        "counts_by_status": by_status,
        "counts_by_suffix_status": dict(sorted(suffix_status.items())),
        "failed_records": failed_records,
        "raw_record_count": len(records),
        "duplicate_record_count": len(duplicate_records),
        "effective_record_count": len(effective_records),
    }


def _is_duplicate_status_record(record: dict[str, Any]) -> bool:
    metadata = (
        record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    )
    summary = str(record.get("content_summary") or "")
    return bool(metadata.get("is_duplicate")) or summary.startswith("[DUPLICATE:")


def _latest_doc_status_by_file(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        file_path = str(
            record.get("file_path")
            or record.get("content_summary")
            or f"record-{index}"
        )
        candidate_sort_key = (
            str(record.get("updated_at") or record.get("created_at") or ""),
            index,
        )
        current = latest.get(file_path)
        current_sort_key = current.get("_sort_key") if current else None
        if current is None or candidate_sort_key >= current_sort_key:
            latest[file_path] = {**record, "_sort_key": candidate_sort_key}
    return [
        {key: value for key, value in record.items() if key != "_sort_key"}
        for record in latest.values()
    ]


def _contract_checks() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    capabilities: dict[str, Any] = {}
    checks: list[dict[str, Any]] = []

    try:
        from lightrag import LightRAG
        from lightrag.parser.routing import resolve_file_parser_directives

        from prompts.multimodal.govcon_multimodal_prompts import GOVCON_NATIVE_MULTIMODAL_PROMPTS
        from src.server.native_lightrag_runtime import native_pipeline_available

        capabilities["native_pipeline_available"] = native_pipeline_available()
        capabilities["enqueue_method_available"] = hasattr(LightRAG, "apipeline_enqueue_documents")
        capabilities["process_method_available"] = hasattr(LightRAG, "apipeline_process_enqueue_documents")

        parser_engine, process_options = resolve_file_parser_directives(
            "smoke.pdf",
            parser_rules="pdf:mineru-ite,docx:native-ite,xlsx:legacy",
            require_external_endpoint=False,
        )
        capabilities["parser_pdf"] = {"engine": parser_engine, "options": process_options}

        prompt_keys = set(GOVCON_NATIVE_MULTIMODAL_PROMPTS)
        prompts = list(GOVCON_NATIVE_MULTIMODAL_PROMPTS.values())
        native_prompt_contract = prompt_keys == {"image_analysis", "table_analysis", "equation_analysis"} and all(
            '"name"' in prompt
            and '"description"' in prompt
            and "entity_info" not in prompt
            and "detailed_description" not in prompt
            for prompt in prompts
        )
        strict_schema_boundary = all(
            "entity_info" not in prompt
            and "detailed_description" not in prompt
            and '"entities"' not in prompt
            and '"relationships"' not in prompt
            for prompt in prompts
        )

        checks.extend(
            [
                {
                    "id": "native_pipeline_available",
                    "passed": bool(capabilities["native_pipeline_available"]),
                    "detail": "lightrag.pipeline import spec is present",
                },
                {
                    "id": "native_enqueue_process_methods",
                    "passed": bool(
                        capabilities["enqueue_method_available"]
                        and capabilities["process_method_available"]
                    ),
                    "detail": "LightRAG exposes native enqueue/process APIs",
                },
                {
                    "id": "parser_routing_resolves_pdf",
                    "passed": parser_engine == "mineru" and process_options == "ite",
                    "detail": f"pdf resolved to {parser_engine}:{process_options}",
                },
                {
                    "id": "native_multimodal_prompt_contract",
                    "passed": native_prompt_contract,
                    "detail": "native prompts use LightRAG JSON object contract",
                },
                {
                    "id": "strict_schema_multimodal_boundary",
                    "passed": strict_schema_boundary,
                    "detail": "native multimodal prompts do not request extraction schema output",
                },
            ]
        )
    except Exception as exc:  # noqa: BLE001
        capabilities["error"] = str(exc)
        checks.append({"id": "native_gate_imports", "passed": False, "detail": str(exc)})

    return capabilities, checks


def build_native_ingestion_regression_report(
    *,
    workspace_path: Path | str | None = None,
    use_fixture: bool = False,
    known_answer_checks: list[dict[str, Any]] | None = None,
    require_multimodal: bool = False,
    require_processed_suffixes: list[str] | None = None,
    fail_on_failed_docs: bool = False,
) -> dict[str, Any]:
    """Build a native ingestion regression report without external services by default."""

    if workspace_path is None:
        use_fixture = True
    if use_fixture:
        entities, relationships, chunks = _fixture_records()
        source = "fixture"
        checks = known_answer_checks or DEFAULT_KNOWN_ANSWER_CHECKS
        require_multimodal = True
    else:
        path = Path(workspace_path)  # type: ignore[arg-type]
        entities, relationships, chunks = _workspace_records(path)
        doc_status_records = _workspace_doc_status(path)
        source = str(path)
        checks = known_answer_checks or []
    if use_fixture:
        doc_status_records = []

    corpus_records = [*entities, *relationships, *chunks]
    entity_counts = _count_by_key(entities, "entity_type")
    relationship_counts = _count_by_key(relationships, "rel_type", "relation_type", "keywords", uppercase=True)
    multimodal = _multimodal_evidence(corpus_records)
    known_answers = _evaluate_known_answers(checks, corpus_records)
    document_status = _document_status_summary(doc_status_records)
    capabilities, contract_checks = _contract_checks()

    gate_checks = [
        {
            "id": "workspace_has_entities",
            "passed": bool(entity_counts),
            "detail": f"{sum(entity_counts.values())} entities counted",
        },
        {
            "id": "workspace_has_relationships",
            "passed": bool(relationship_counts),
            "detail": f"{sum(relationship_counts.values())} relationships counted",
        },
    ]
    if require_multimodal:
        gate_checks.append(
            {
                "id": "multimodal_table_evidence_present",
                "passed": multimodal["tables"] > 0,
                "detail": f"{multimodal['tables']} table evidence records counted",
            }
        )
    if fail_on_failed_docs:
        failed_count = len(document_status["failed_records"])
        gate_checks.append(
            {
                "id": "document_status_has_no_failed_records",
                "passed": failed_count == 0,
                "detail": f"{failed_count} failed document records counted",
            }
        )
    for suffix in require_processed_suffixes or []:
        normalized_suffix = suffix if suffix.startswith(".") else f".{suffix}"
        suffix_counts = document_status["counts_by_suffix_status"].get(normalized_suffix.lower(), {})
        processed_count = suffix_counts.get("processed", 0)
        gate_checks.append(
            {
                "id": f"processed_suffix_{normalized_suffix.lower().lstrip('.')}",
                "passed": processed_count > 0,
                "detail": f"{processed_count} processed {normalized_suffix.lower()} document records counted",
            }
        )

    passed = all(item["passed"] for item in [*contract_checks, *gate_checks, *known_answers])
    return {
        "passed": passed,
        "capabilities": capabilities,
        "contract_checks": contract_checks,
        "gate_checks": gate_checks,
        "workspace": {
            "source": source,
            "entity_counts_by_type": entity_counts,
            "relationship_counts_by_type": relationship_counts,
            "multimodal_evidence": multimodal,
            "known_answer_checks": known_answers,
            "document_status": document_status,
        },
    }


def write_report_json(report: dict[str, Any], output_path: Path | str) -> None:
    Path(output_path).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def format_report_text(report: dict[str, Any]) -> str:
    status = "PASS" if report.get("passed") else "FAIL"
    workspace = report["workspace"]
    lines = [
        f"Native ingestion regression gate: {status}",
        f"Source: {workspace['source']}",
        "",
        "Contract checks:",
    ]
    for check in report["contract_checks"]:
        marker = "PASS" if check["passed"] else "FAIL"
        lines.append(f"  - {marker} {check['id']}: {check['detail']}")
    lines.append("")
    lines.append("Entity counts by type:")
    for key, value in workspace["entity_counts_by_type"].items():
        lines.append(f"  - {key}: {value}")
    lines.append("Relationship counts by type:")
    for key, value in workspace["relationship_counts_by_type"].items():
        lines.append(f"  - {key}: {value}")
    lines.append("Multimodal evidence:")
    for key, value in workspace["multimodal_evidence"].items():
        lines.append(f"  - {key}: {value}")
    if workspace["known_answer_checks"]:
        lines.append("Known-answer checks:")
        for check in workspace["known_answer_checks"]:
            marker = "PASS" if check["passed"] else "FAIL"
            missing = ", ".join(check["missing_terms"]) or "none"
            lines.append(f"  - {marker} {check['id']}: missing={missing}")
    return "\n".join(lines) + "\n"