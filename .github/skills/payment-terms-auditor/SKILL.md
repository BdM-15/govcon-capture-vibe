---
name: payment-terms-auditor
description: Forensic payment-terms and cash-flow auditor for the active Theseus workspace. USE WHEN the user asks about NET payment days, progress payments, invoice timing, CLIN-level cash flow, working-capital exposure, or "what are the payment terms by CLIN?". Searches clause, contract_line_item, requirement, deliverable, and PWS/SOW chunks. Produces verbatim extracts, a CLIN cash-flow table, and BOE implications. DO NOT USE FOR full price-to-win modeling (use price-to-win) or general compliance audits (use compliance-auditor).
license: MIT
metadata:
  personas_primary: cost_estimator
  personas_secondary: [contracts_manager, capture_manager]
  shipley_phases: [capture, strategy, proposal_development]
  capability: analyze
  runtime: tools
  category: forensic
  version: 1.0.0
  status: active
---

# Payment Terms Auditor

Forensic slice focused on **payment timing, invoice mechanics, and CLIN-level cash flow**. Work multi-turn against the workspace KG; every row cites evidence.

## Workflow

### 1. Slice payment-relevant entities

```json
{
  "types": [
    "clause",
    "contract_line_item",
    "requirement",
    "deliverable",
    "proposal_instruction",
    "document"
  ],
  "limit": 150,
  "max_chunks": 5,
  "max_relationships": 10
}
```

If `contract_line_item` and `clause` are both empty, halt with `GAP: no CLIN or clause entities — re-extract or broaden retrieval`.

### 2. Retrieve verbatim payment language

Run focused `kg_chunks` queries (hybrid or mix):

- `"NET payment invoice due days progress payment CLIN"`
- `"FAR 52.232 payment withholding acceptance"`
- `"milestone payment fixed price cost reimbursable"`

Capture `chunk_id` for every quote you use.

### 3. Optional graph trace

When Neo4j is available, `kg_query`:

```cypher
MATCH (c:contract_line_item)-[r]->(n)
RETURN c.entity_id AS clin, type(r) AS rel, labels(n)[0] AS tgt_type, n.entity_id AS tgt
LIMIT 500
```

### 4. Read output contract

`read_file` → `references/forensic_output_contract.md` and `assets/report_template.md`.

### 5. Build findings

For each CLIN or payment clause:

- Quote verbatim terms (days, milestones, withholds, acceptance gates)
- Classify contractor cash impact (accelerating vs delaying cash)
- Severity H/M/L with cited basis
- Proposal implication (BOE narrative, financing, escalation) only if supported

### 6. Emit artifacts

`write_file`:

- `artifacts/report.md` — filled template
- `artifacts/report.json` — envelope per output contract

Label the JSON workbook source as `payment_terms_audit.json` if you emit a flat findings array for XLSX rendering.