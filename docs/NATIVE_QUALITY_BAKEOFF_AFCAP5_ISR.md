# Native Quality Bake-Off: AFCAP5 ISR

Status: agent evidence captured; human sign-off pending.

Issue: #172. Date: 2026-05-27. Workspace: `afcap5_isr`.

## Scope

This bake-off uses the smaller AFCAP5 Israel BOS-I workspace under `rag_storage/afcap5_isr`. This is the preferred test target for #172 because it is representative enough to cover solicitation, PWS, cost/staffing tables, and site-specific workload evidence without the noise and runtime of the much larger MCPP II package.

Source files under `inputs/afcap5_isr`:

- `26R0013 - FOPR Israel BOS-I.pdf`
- `Attachment 1 - PWS Israel BOS-I 6Apr26.pdf`
- `Attachment 2 - CLIN Cost Estimate dated 9 April 2026.xlsx`
- `Attachment 5 - FOPR Staffing Matrix Template.xlsx`

## Configuration Tested

```dotenv
LIGHTRAG_PARSER=pdf:mineru-ite,doc:mineru-ite,docx:native-ite,ppt*:mineru-ite,xls*:mineru-t
VLM_PROCESS_ENABLE=true
MINERU_API_MODE=local
MINERU_LOCAL_BACKEND=pipeline
MINERU_LOCAL_PARSE_METHOD=auto
CHUNK_SIZE=4096
CHUNK_OVERLAP_SIZE=600
MAX_GLEANING=0
```

## Regression Gate Result

Command:

```powershell
.\.venv\Scripts\python.exe tools/native_ingestion_regression_gate.py --workspace rag_storage/afcap5_isr --known-answer-file tools/native_known_answers.afcap5_isr.json --require-multimodal --output run-dir/artifacts/native-ingestion-gate-afcap5_isr.json --json
```

Result: PASS.

| Check | Result |
| --- | --- |
| Native pipeline import available | Pass |
| `apipeline_enqueue_documents` / `apipeline_process_enqueue_documents` available | Pass |
| PDF parser routing resolves to `mineru:ite` | Pass |
| Native multimodal prompt contract | Pass |
| Strict extraction schema does not leak into multimodal prompts | Pass |
| Workspace entity records | 1,164 |
| Workspace relationship keyword records | 1,726 |
| Multimodal evidence | 13 table records, 2 image records, 0 equation records |
| AFCAP5 known-answer term checks | Pass: Israel BOS-I sites, QCP/performance thresholds, staffing/workload/cost |

Top extracted entity types:

| Entity type | Count |
| --- | ---: |
| `requirement` | 348 |
| `concept` | 162 |
| `regulatory_reference` | 133 |
| `performance_standard` | 84 |
| `document` | 69 |
| `deliverable` | 56 |
| `document_section` | 49 |
| `organization` | 40 |
| `technology` | 36 |
| `work_scope_item` | 23 |
| `workload_metric` | 23 |
| `labor_category` | 19 |
| `government_furnished_item` | 16 |
| `evaluation_factor` | 13 |
| `strategic_theme` | 12 |

Top canonical relationship keywords present:

| Relationship type | Count |
| --- | ---: |
| `CHILD_OF` | 293 |
| `REFERENCES` | 180 |
| `RELATED_TO` | 56 |
| `MEASURED_BY` | 52 |
| `SUBMITTED_TO` | 44 |
| `GOVERNED_BY` | 38 |
| `APPLIES_TO` | 37 |
| `TRACKED_BY` | 31 |
| `QUANTIFIES` | 29 |
| `SATISFIED_BY` | 28 |
| `CONSTRAINED_BY` | 24 |
| `DEFINES` | 24 |

Relationship caveat: raw VDB relationship keywords are 51.3% canonical by exact ontology match. Non-canonical labels still appear, led by `PWS HIERARCHY`, `BELONGS_TO`, `CONTAINED_IN`, `PART_OF`, `STRUCTURAL CONTAINMENT`, `CONTAINS`, `THRESHOLD`, and `WORKLOAD DRIVER`. Retrieval remained useful in the observed queries, but #173 should preserve or strengthen relationship normalization tests before removing the legacy compatibility surface.

## Processing Status And Speed

Current document status for `afcap5_isr`: 3 processed, 1 failed.

| File | Status | Chunks | Duration |
| --- | --- | ---: | ---: |
| `26R0013 - FOPR Israel BOS-I.pdf` | processed | 2 | 1.2 min |
| `Attachment 1 - PWS Israel BOS-I 6Apr26.pdf` | processed | 18 | 4.2 min |
| `Attachment 5 - FOPR Staffing Matrix Template.xlsx` | processed | 1 | 0.4 min |
| `Attachment 2 - CLIN Cost Estimate dated 9 April 2026.xlsx` | failed | 0 | n/a |

Processed document durations total 5.8 document-minutes across 21 chunks, averaging 1.9 minutes per processed document.

Failed record: `Attachment 2 - CLIN Cost Estimate dated 9 April 2026.xlsx` has no captured error message in doc status. This is the main human review item for parity. Because the staffing matrix and PWS workload evidence were processed and query-visible, AFCAP5 ISR is still useful as a compact regression target, but the failed cost workbook should be re-run or explicitly accepted as out of scope before #173.

## Known-Answer Query Evaluation

Queries were run against `afcap5_isr` with Neo4j reachable using `tools/compare_workspaces.py` and identical A/B workspace labels only to reuse the existing report writer.

| Query | Mode | Length | Time | Evidence grounding | Shipley usefulness |
| --- | --- | ---: | ---: | --- | --- |
| Which bases and site-specific BOS-I requirements drive this AFCAP5 ISR task order? | `hybrid` | 2,203 chars | 1.8s | Identifies Hatzor Air Base, Nevatim Air Base, Site 53/61 annexes, TOMP/CDRL A002 tie | Strong: flags dual-site OCONUS execution, host-nation coordination, surge risk |
| What quality control and performance thresholds matter most in the PWS? | `hybrid` | 3,598 chars | 0.8s | Cites QCP, Subfactor 1.4, CDRL A014, 95%/99%/zero-discrepancy thresholds | Strong: frames QCP as Acceptable/Unacceptable gate and Pink Team traceability item |
| What staffing or workload evidence should inform the basis of estimate? | `mix` | 3,506 chars | 1.8s | Cites Appendix F, Annexes F-1 through F-10, H.2 exercise workload, Attachment 5 staffing matrix | Strong: ties workload to BOE, cost realism, assumptions, surge staffing |

Observed query quality is good: responses are concise, grounded in the AFCAP5 source files, and useful for capture/proposal decisions rather than generic summarization.

## Multimodal Sidecar Inspection

Table evidence is present and query-relevant. Samples include solicitation/FOPR tables, PWS service summary and QCP-related tables, site/workload sections, and the staffing matrix template. The workload query correctly surfaced Hatzor/Nevatim site evidence, Appendix F annexes, exercise support assumptions, performance thresholds, and Attachment 5 staffing matrix requirements.

Image evidence exists but sampled image entity descriptions were empty for placeholder-style records such as `GFP Attachment Template.xlsx Placeholder (image)` and `Microsoft Word Document Icon - Sample 7-Day Menu Cycle Placeholder (image)`. This looks low-risk because those are placeholder/icon artifacts rather than substantive diagrams, but human review should confirm no meaningful org chart or map image needs richer VLM text.

Equation evidence is absent, which appears plausible for this package.

OCR note: sampled chunks contain mojibake around the inserted `[GOVCON_DOC: ...]` banner text, but the retrieved RFP/PWS content still supported the known-answer queries.

## Recommendation

Use AFCAP5 ISR as the compact native quality regression target for #172, not MCPP II.

Keep the current native default for the next parity run:

- `pdf:mineru-ite` for the FOPR and PWS PDFs.
- `xls*:mineru-t` for the staffing/cost workbooks, with focused follow-up on the failed cost workbook.
- `CHUNK_SIZE=4096`, `CHUNK_OVERLAP_SIZE=600`, `MAX_GLEANING=0`.
- `VLM_PROCESS_ENABLE=true` with local MinerU `pipeline` backend.

Do not start #173 solely from this agent evidence. Human sign-off should first resolve or explicitly accept these findings:

1. Whether `Attachment 2 - CLIN Cost Estimate dated 9 April 2026.xlsx` must be reprocessed successfully before parity sign-off.
2. Whether empty placeholder image descriptions are acceptable for AFCAP5 ISR.
3. Whether non-canonical raw relationship labels in `vdb_relationships.json` are expected, need normalization, or need a #173 regression test.

Human sign-off line: pending.