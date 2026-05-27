# Native Ingestion Regression Gate

This gate is the repeatable smoke path for changes to native LightRAG ingestion, parser routing, multimodal prompts, strict extraction schema handling, and LightRAG version pins.

## Default CI Smoke

Run the fixture mode when no GPU, no MinerU service, and no external LLM calls are available:

```powershell
.\.venv\Scripts\python.exe tools/native_ingestion_regression_gate.py --fixture --json
```

Fixture mode validates:

- LightRAG native pipeline capability is importable.
- `apipeline_enqueue_documents` and `apipeline_process_enqueue_documents` exist.
- `LIGHTRAG_PARSER`-style rules resolve a PDF to `mineru` with image/table/equation processing.
- Native multimodal prompts keep LightRAG's JSON object contract and stay outside the strict GovCon extraction schema.
- Regression output includes entity counts by type, relationship counts by type, multimodal table evidence, and known-answer term checks.

## Workspace Mode

Run workspace mode after processing a representative RFP through the native parser pipeline:

```powershell
.\.venv\Scripts\python.exe tools/native_ingestion_regression_gate.py --workspace rag_storage/<workspace> --known-answer-file tools/native_known_answers.example.json --require-multimodal --output run-dir/artifacts/native-ingestion-gate.json
```

For a parser bake-off workspace that must prove Office ingestion, require the relevant suffixes and fail on any failed doc-status records:

```powershell
.\.venv\Scripts\python.exe tools/native_ingestion_regression_gate.py --workspace rag_storage/<workspace> --known-answer-file tools/native_known_answers.example.json --require-multimodal --require-processed-suffix .xlsx --fail-on-failed-docs --output run-dir/artifacts/native-ingestion-gate.json
```

Workspace mode reads the LightRAG artifacts under `rag_storage/<workspace>` and reports:

- `entity_counts_by_type` from `vdb_entities.json`.
- `relationship_counts_by_type` from `vdb_relationships.json`.
- `multimodal_evidence` from chunks/entities/relationships.
- `known_answer_checks` from a JSON file with `id`, `query`, and `expected_terms` fields.
- `document_status` from `kv_store_doc_status.json`, including processed/failed counts by suffix.

For XLSX workbooks, route to LightRAG's stock file-upload extraction helper with legacy raw ingestion (`xlsx:legacy`) because the local MinerU API does not support XLSX. Keep `--require-processed-suffix .xlsx --fail-on-failed-docs` in parser bake-offs where spreadsheet extraction is part of the quality bar.

The command exits non-zero if native capability checks fail, if the workspace has no entities/relationships, if `--require-multimodal` is set and no table evidence is found, if any known-answer expected term is missing, if `--require-processed-suffix` has no processed doc-status record for that suffix, or if `--fail-on-failed-docs` sees failed doc-status records.

## Full Local MinerU + VLM Checklist

Use this checklist before changing parser routing defaults, multimodal prompts, strict-schema boundaries, or the LightRAG pin.

1. Confirm `.env` has the intended `LIGHTRAG_PARSER`, `VLM_PROCESS_ENABLE`, `MINERU_API_MODE`, and MinerU endpoint/token settings.
2. Start the local MinerU service when `MINERU_API_MODE=local`, or confirm the official MinerU token works when using `official` mode.
3. Process at least one representative final RFP workspace through Capture Workbench upload or `/scan-rfp`.
4. Run the workspace-mode command above with a bid-specific known-answer file.
5. Inspect `run-dir/artifacts/native-ingestion-gate.json` for entity/relationship deltas, multimodal evidence, and known-answer failures.
6. If the gate fails after a prompt or parser change, reprocess the workspace before judging quality; stale KG/VDB artifacts reflect the previous settings.

## Future Agent Rule

Future agents should run the fixture gate before editing native ingestion code, `prompts/multimodal/`, `src/server/llm_routing.py`, `src/server/native_lightrag_runtime.py`, or LightRAG dependency pins. This expectation is mirrored in [.github/copilot-instructions.md](../.github/copilot-instructions.md).
