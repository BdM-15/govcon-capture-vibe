# Forensic output contract

Every forensic skill emits **both**:

1. `artifacts/report.md` — human-readable report (sections below)
2. `artifacts/report.json` — machine-readable envelope for Studio / downstream skills

## Required sections (report.md)

1. **Executive summary** — one grounded paragraph; name top three logistics risks
2. **Verbatim extracts** — quote exact RFP language with section/page refs and `[chunk-…]` citations
3. **Summary table(s)** — destinations, SLAs, metrics (OTD, FR, surge, etc.)
4. **Risk and performance implications** — H/M/L with cited basis only
5. **Proposal implications** — staffing, network, or performance narrative actions supported by documents only

## JSON envelope (report.json)

```json
{
  "skill": "<skill-name>",
  "workspace": "<workspace>",
  "focus": "<forensic focus>",
  "executive_summary": "...",
  "findings": [
    {
      "id": "F1",
      "title": "...",
      "severity": "high|medium|low|info",
      "entity_ids": [],
      "chunk_ids": [],
      "verbatim": "...",
      "implication": "..."
    }
  ],
  "tables": [],
  "gaps": []
}
```

## Discipline

- No invention — every finding cites at least one `chunk_id` or `entity_id` from tool output
- Format-agnostic — do not fail because UCF section labels are absent
- Mark `GAP: insufficient retrieval coverage` when the focus topic is absent from evidence