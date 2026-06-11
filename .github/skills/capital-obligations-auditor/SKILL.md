---
name: capital-obligations-auditor
description: Forensic upfront-capital and obligation auditor for the active Theseus workspace. USE WHEN the user asks about seed capital, working capital, inventory ownership, disposition obligations, lease vs buy, transition property, or "what capital does this contract require?". Searches clause, requirement, deliverable, contract_line_item, and PWS/SOW chunks. Produces obligation tables and financing-risk ratings for price-to-win handoff. DO NOT USE FOR full BOE build (use price-to-win) or payment-term timing alone (use payment-terms-auditor).
license: MIT
metadata:
  personas_primary: cost_estimator
  personas_secondary: [capture_manager, contracts_manager]
  shipley_phases: [capture, strategy, proposal_development]
  capability: analyze
  runtime: tools
  category: forensic
  version: 1.0.0
  status: active
---

# Capital Obligations Auditor

Forensic slice focused on **upfront capital, inventory, disposition, and long-lead obligations**. Work multi-turn against the workspace KG.

## Workflow

### 1. Slice capital-relevant entities

```json
{
  "types": [
    "clause",
    "requirement",
    "deliverable",
    "contract_line_item",
    "compliance_artifact",
    "document"
  ],
  "limit": 150,
  "max_chunks": 5,
  "max_relationships": 10
}
```

### 2. Retrieve verbatim obligation language

`kg_chunks` queries:

- `"capital equipment inventory ownership disposition transition"`
- `"lease purchase upfront investment working capital"`
- `"property accountability government furnished contractor acquired"`

### 3. Optional graph trace

```cypher
MATCH (r:requirement)-[rel]->(d:deliverable)
RETURN r.entity_id AS req, type(rel) AS rel_type, d.entity_id AS deliverable
LIMIT 500
```

### 4. Read output contract

`read_file` → `references/forensic_output_contract.md` and `assets/report_template.md`.

### 5. Build findings

For each obligation:

- Quote who owns/acquires/disposes of property or inventory
- Quantify exposure when numbers appear in source text
- Severity H/M/L
- Proposal implication (financing narrative, transition plan, BOE line items) only if supported

### 6. Emit artifacts

- `artifacts/report.md`
- `artifacts/report.json` (optional `capital_obligations_audit.json` for workbook emission)