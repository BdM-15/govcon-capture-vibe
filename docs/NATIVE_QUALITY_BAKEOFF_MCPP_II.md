# Native Quality Bake-Off: MCPP II

Status: agent evidence captured; human sign-off pending.

Issue: #172. Date: 2026-05-27. Workspace: `mcppII_rfp`.

## Scope

This bake-off uses the representative final MCPP II RFP workspace already present under `rag_storage/mcppII_rfp`. The source package under `inputs/mcppII_rfp` includes the final solicitation, amendments, SOW, CDRL exhibits, cost model workbook, wage determinations, DD Form 254, and notional org structure.

No matching local pre-native baseline workspace exists for this exact final MCPP II package. Historical MCPP comparison reports in `tools/` cover earlier draft workspaces and are useful background only, not an apples-to-apples baseline for this final RFP.

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
.\.venv\Scripts\python.exe tools/native_ingestion_regression_gate.py --workspace rag_storage/mcppII_rfp --known-answer-file tools/native_known_answers.example.json --require-multimodal --output run-dir/artifacts/native-ingestion-gate-mcppII_rfp.json --json
```

Result: PASS.

| Check | Result |
| --- | --- |
| Native pipeline import available | Pass |
| `apipeline_enqueue_documents` / `apipeline_process_enqueue_documents` available | Pass |
| PDF parser routing resolves to `mineru:ite` | Pass |
| Native multimodal prompt contract | Pass |
| Strict extraction schema does not leak into multimodal prompts | Pass |
| Workspace entity records | 9,450 |
| Workspace relationship records | 18,747 |
| Multimodal evidence | 159 table records, 8 image records, 0 equation records |
| Known-answer term checks | Pass: L/M traceability, deliverable catalog, workload table |

Top extracted entity types:

| Entity type | Count |
| --- | ---: |
| `requirement` | 2,914 |
| `equipment` | 1,673 |
| `deliverable` | 808 |
| `document` | 423 |
| `labor_category` | 387 |
| `performance_standard` | 377 |
| `clause` | 345 |
| `pricing_element` | 313 |
| `regulatory_reference` | 249 |
| `concept` | 243 |
| `document_section` | 232 |
| `proposal_instruction` | 191 |

Top canonical relationship keywords present:

| Relationship type | Count |
| --- | ---: |
| `CHILD_OF` | 3,071 |
| `REFERENCES` | 2,462 |
| `GOVERNED_BY` | 954 |
| `RELATED_TO` | 587 |
| `APPLIES_TO` | 459 |
| `PRICED_UNDER` | 395 |
| `MEASURED_BY` | 341 |
| `HAS_EQUIPMENT` | 297 |
| `QUANTIFIES` | 227 |
| `DEFINES` | 227 |

Relationship caveat: raw VDB relationship keywords are 54.7% canonical by exact ontology match. Non-canonical labels still appear, led by `INVENTORY LISTING`, `STRUCTURAL CONTAINMENT`, `TABLE CONTAINS ITEM`, `INVENTORY ITEM`, and `SECTION CONTAINMENT`. This does not block retrieval in the observed queries, but it should be reviewed before #173 removes the legacy compatibility surface, because native-only tests should verify canonical relationship normalization or intentional raw-label preservation.

## Processing Status And Speed

Current document status for `mcppII_rfp`: 18 processed, 12 failed. Processed document durations total 98.5 document-minutes across 289 chunks, averaging 5.5 minutes per processed document. Longest processed files:

| File | Chunks | Duration |
| --- | ---: | ---: |
| `ATCH_J_6_USMC_and_Navy_Organic_Gov_Prop_Facilities.xlsx` | 39 | 22.8 min |
| `ATCH_J_5_Statement_of_Work_SOW_Amend_2.pdf` | 47 | 12.3 min |
| `ATCH_J_5_Statement_of_Work_SOW_Amend_2.docx` | 47 | 9.8 min |
| `Exh_A_10_CDRL_7001_7011_Shipboard.pdf` | 1 | 9.5 min |
| `Solicitation_Amendment___M6700426R00070002.pdf` | 28 | 6.7 min |
| `MCPP_II_Solicitation___M6700426R0007.pdf` | 26 | 6.0 min |

Failed records are the remaining Exhibit A CDRL PDFs (`Exh_A_1` through `Exh_A_9` and `Exh_A_11` through `Exh_A_13`). Their doc-status records do not currently include error messages. Human review should decide whether those PDFs are redundant with the processed CDRL workbook/SOW evidence, or whether they must be reprocessed before parity sign-off.

## Known-Answer Query Evaluation

Queries were run against `mcppII_rfp` with Neo4j reachable using `tools/compare_workspaces.py` and identical A/B workspace labels only to reuse the existing report writer. Reports live under `run-dir/artifacts/`.

| Query | Mode | Length | Time | Evidence grounding | Shipley usefulness |
| --- | --- | ---: | ---: | --- | --- |
| How do Section L instructions map to Section M evaluation factors? | `hybrid` | 3,965 chars | 2.8s | References volume-to-factor mapping, page budgets, strict compliance language | Strong: explains L drives structure, M drives strategy, recommends L/M mapping table |
| Which deliverables or CDRLs are required, and what submission schedules matter most? | `hybrid` | 5,424 chars | 1.9s | Cites SOW, CDRL list workbook, amendment/CLIN structure | Strong: identifies recurring schedule risk, NSP compliance burden, CDRL management discriminator |
| What workload evidence appears in tables or attachments? | `mix` | 2,593 chars | 2.2s | Cites SOW Attachment 10.1, J-4, S-2, J-7, final solicitation | Strong: ties tables to BOE, cost realism, and traceable labor assumptions |

Observed query quality is good: responses are short enough for analyst use, reference actual source files, include capture/proposal implications, and use Shipley framing without losing concrete RFP details.

## Multimodal Sidecar Inspection

Table evidence is useful for workload and pricing. Examples include wage determination tables, CBA wage schedules, DD Form 254 tables, SOW/QMSS text-adjacent tables, equipment inventories, and the cost model workbook. Workload query retrieval correctly surfaced SOW Attachment 10.1, Attachment J-4 equipment inventory, notional watercraft quantities, and Attachment S-2 minimum annual hours.

Image evidence exists but sampled image entity descriptions were empty for items such as Figure 1 organizational communication, Figure 2 contracting authority, and Attachment J-7 placeholder images. This may be acceptable for placeholder/diagram-heavy pages, but human sign-off should inspect whether diagrams that matter to management approach need richer VLM descriptions.

Equation evidence is absent, which appears plausible for this package.

OCR note: sampled table chunks include mojibake in some wage/security form text. It did not break known-answer retrieval, but final bake-off should spot-check whether enough source text is clean for wage, clearance, and security compliance questions.

## Recommendation

Keep the current native default for the next parity run:

- `pdf:mineru-ite` for final solicitation and scanned/exhibit PDFs.
- `doc:mineru-ite` and `docx:native-ite` to preserve text-heavy SOW fidelity while avoiding unnecessary table amplification.
- `xls*:mineru-t` for workbook/table-heavy workload, cost, and CDRL files.
- `CHUNK_SIZE=4096`, `CHUNK_OVERLAP_SIZE=600`, `MAX_GLEANING=0`.
- `VLM_PROCESS_ENABLE=true` with local MinerU `pipeline` backend.

Do not start #173 solely from this agent evidence. Human sign-off should first resolve or explicitly accept these findings:

1. Whether the 12 failed CDRL exhibit PDFs are redundant or must be reprocessed.
2. Whether image-sidecar descriptions are adequate for diagrams, org charts, and cost workbook placeholders.
3. Whether non-canonical raw relationship labels in `vdb_relationships.json` are expected, need normalization, or need a #173 regression test.
4. Whether historical draft MCPP comparison reports are enough baseline context, or a final-package legacy baseline must be restored for apples-to-apples comparison.

Human sign-off line: pending.