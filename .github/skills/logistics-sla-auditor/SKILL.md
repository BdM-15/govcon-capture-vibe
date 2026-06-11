---
name: logistics-sla-auditor
description: Forensic logistics and SLA auditor for the active Theseus workspace. USE WHEN the user asks about shipping destinations, on-time delivery (OTD), fill rate (FR), distribution performance, surge logistics, site access constraints, or "what are the logistics SLAs?". Searches performance_standard, requirement, work_scope_item, deliverable, and PWS/SOW chunks. Produces destination/metric tables and performance-risk ratings. DO NOT USE FOR geographic site inventory alone (use Capture Chat scope primer) or workload spreadsheet analysis (use workload-analyzer).
license: MIT
metadata:
  personas_primary: program_manager
  personas_secondary: [technical_sme, capture_manager]
  shipley_phases: [capture, strategy, proposal_development]
  capability: analyze
  runtime: tools
  category: forensic
  version: 1.0.0
  status: active
---

# Logistics SLA Auditor

Forensic slice focused on **shipping, distribution, and performance metrics** (OTD, FR, surge, access). Work multi-turn against the workspace KG.

## Workflow

### 1. Slice logistics-relevant entities

```json
{
  "types": [
    "performance_standard",
    "requirement",
    "work_scope_item",
    "deliverable",
    "task_area",
    "document"
  ],
  "limit": 150,
  "max_chunks": 5,
  "max_relationships": 10
}
```

### 2. Retrieve verbatim SLA language

`kg_chunks` queries:

- `"on-time delivery OTD fill rate FR shipping destination"`
- `"surge distribution warehouse logistics performance standard"`
- `"site access CONUS OCONUS transportation SLA"`

### 3. Optional graph trace

```cypher
MATCH (p:performance_standard)-[r]->(n)
RETURN p.entity_id AS metric, type(r) AS rel, labels(n)[0] AS tgt_type, n.entity_id AS tgt
LIMIT 500
```

### 4. Read output contract

`read_file` → `references/forensic_output_contract.md` and `assets/report_template.md`.

### 5. Build findings

For each destination lane or metric:

- Quote threshold and measurement method verbatim
- Note geographic concentration or single-point risks when cited
- Severity H/M/L
- Proposal implication (network design, staffing, spares) only if supported

### 6. Emit artifacts

- `artifacts/report.md`
- `artifacts/report.json` (optional flat array `logistics_sla_audit.json` for workbook emission)