# Readiness Signal Catalog

> The **Mission Readiness Frame** names the readiness outcome the **program office** owns. The contract workload exists to instrument that outcome.

## Explicit readiness language (high confidence)

| Pattern | Typical source sections |
| ------- | ----------------------- |
| "readiness", "mission readiness", "operational readiness" | Background, PWS objectives, agency strategic alignments |
| "fully mission capable", "FMC", "mission capable" | Performance standards, QASP, inspection criteria |
| "availability", "uptime", "operational capability" | PWS performance objectives, SLAs |
| "mission assurance", "assured access", "generation readiness" | Air/sea/land domain task areas |
| "training pipeline", "throughput", "qualification rate" | PWS training / personnel readiness tasks |
| "spares readiness", "fill rate", "supply availability" | Logistics attachments, performance standards |

## Proxy readiness signals (medium confidence — tag `type: proxy`)

| Proxy | What it usually instruments |
| ----- | ----------------------------- |
| Dense QASP with payment consequences | Performance anxiety on readiness slip |
| Zero-defect / AQL thresholds on operational equipment | Availability risk the customer cannot absorb |
| 24/7 / surge coverage without multiplier | Continuity of readiness during spikes |
| Short transition-in windows on recompetes | Fear of readiness gap during turnover |
| "Previous contractor experienced delays/failures…" | Documented readiness failure mode |
| Key personnel locks on niche certifications | Single-point readiness risk |

## Workload enabler mapping

For each major PWS/SOW task cluster, ask:

1. **Which readiness outcome does this task instrument?**
2. **What failure mode does the customer fear if we underperform here?**
3. **Is this workload primary (spine) or hygiene (table stakes)?**

Emit `workload_enablers[]` with a one-line `readiness_link` per enabler.

## Non-DoW packages

When "readiness" is not literal, frame equivalent outcomes:

- **Continuity of operations** (civilian agencies)
- **Audit / compliance posture** (financial, health, security)
- **Service level / citizen-facing availability**

Set `readiness_outcome` using the document's own priority language; mark proxy signals explicitly.

## Anti-patterns

- Do **not** treat the contract type or CLIN structure as the readiness outcome.
- Do **not** confuse **CO evaluation mechanics** with **customer readiness priority** — link them in `implicit_criteria`, not in the frame headline.
- Do **not** write win-theme prose here — only `win_theme_candidates[]` seeds.