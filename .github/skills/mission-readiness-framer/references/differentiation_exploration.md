# Differentiation Exploration — Pain, Themes, Methods, Innovation

> Extend the Mission Readiness Frame with **exploratory but grounded** capture intelligence: non-obvious pains, theme opportunities with rationale, what methods the customer already uses, and where a bidder could differentiate — **customer-grounded ideation only**.

## Layer A — Comprehensive pain & theme opportunity mining

**Intent:** Surface win-theme fuel the customer never stated plainly — without inventing.

### Pain visibility classes

| `visibility` | Meaning | Detection |
| ------------ | ------- | --------- |
| `explicit` | Customer says it directly | Background confession, "previous contractor…", audit finding |
| `latent` | Implied by repetition, QASP teeth, or omission | Dense inspection on one task; zero-tolerance language; missing transition on recompete |
| `structural` | Built into workload design | 24/7 without surge multiplier; manual CDRL routing; dual-system data entry |

Every `customer_pain_points[]` entry MUST include:

- `rationale` — 2–4 sentences: **signal → why it matters to readiness → what a strong offer does**
- `visibility` — `explicit` | `latent` | `structural`
- `challenge_type` — `performance` | `transition` | `data_integrity` | `staffing` | `compliance` | `cost` | `security` | `other`

### Non-obvious pain heuristics (tea leaves → pain)

- **Threshold obsession** (AQL, zero discrepancies) → prior visibility or accountability failure
- **Named system locks** (OMMS-NG, QMSS, WAWF) → data/integration pain or audit scar tissue
- **Repeated "shall" on reporting cadence** → customer burned by late or wrong CDRLs
- **Mission-essential / crisis language** without staffing detail → fear of surge gap
- **Eval factor asks for "innovative" or "efficient"** without defining it → openness to method change (pair with innovation_opportunities)

### Theme opportunity discipline

`win_theme_candidates[]` are not slogans. Each needs a **rationale chain** the capture lead can defend:

1. **Customer signal** (cited chunk)
2. **Readiness consequence** if unaddressed
3. **Theme angle** (one line)
4. **Proof we must show** (past perf, metric, methodology)
5. **Differentiation hypothesis** — why this separates us (honest if weak: mark `confidence: low`)

Use Class B framing for step 5 when judgment-based: `Our read:`, `Likely discriminator if…`

## Layer B — Current methods & innovation opportunities

**Intent:** Understand what the customer **already instruments** in the PWS, then find **quality↑ / cost↓ / both** improvements — methods and technology.

### `current_methods[]` — what is in place (per PWS/SOW)

For each material task cluster, document what the package implies today:

| Field | Content |
| ----- | ------- |
| `task_cluster` | PWS section / task area |
| `method_description` | Manual, system-named, process, or tool cited in scope |
| `systems_named[]` | OMMS-NG, QMSS, WAWF, etc. |
| `maturity_signal` | `mandated` | `referenced` | `incumbent_implied` |
| `source_chunk_ids[]` | Citations |

Do not assume SaaS or AI unless the document names it. "As required" / "as appropriate" → `maturity_signal: referenced`, low confidence.

### `innovation_opportunities[]` — differentiation without buzzword bingo

**Innovation** = any approach that **increases quality, reduces cost, or both** — not only new technology.

| `opportunity_type` | Examples |
| ------------------ | -------- |
| `process` | Tiered staffing, follow-the-sun, automated CDRL routing |
| `data_analytics` | Predictive maintenance, anomaly detection on inspection data |
| `automation` | RPA on repetitive reporting, workflow orchestration |
| `technology` | Named platform upgrade, digital twin, AI-assisted QC — only if PWS scope supports it |
| `organizational` | Surge bench, cross-trained teams, single integrated QCP |

Each entry MUST include:

- `quality_impact` — how readiness or performance improves (cited or Class B)
- `cost_impact` — `reduce` | `neutral` | `invest_to_save` with one-line basis
- `differentiation_angle` — why competitors may not offer this on this contract
- `readiness_link` — ties to Mission Readiness Frame
- `fit_to_scope` — `in_scope` | `stretch` | `requires_qa` — honest scope boundary
- `source_chunk_ids[]` — PWS/QASP/eval language that opens the door

**Anti-pattern:** Generic "use AI" with no task anchor. Tie every opportunity to a **cited** requirement or performance anxiety.

### Value without waste / bloat

Every `innovation_opportunities[]` entry should pass a **lean-delivery test**:

- Does this reduce manual burden the PWS already imposes? (`cost_impact: reduce`)
- Does it tighten a readiness outcome the customer already measures? (`quality_impact`)
- Would it add scope, licenses, or headcount the customer did not ask for? → `fit_to_scope: stretch` or `requires_qa`

**Our read:** differentiation in the AI era is often **fewer failure modes and less rework**, not more widgets. Prefer process clarity, automation of reporting burden, and measurable quality gains over novelty.

## Layer C — User-directed capability overlay (explicit invoke only)

When the user names a **vendor, platform, or URL** and asks whether it addresses pains or adds value:

| Step | Action |
| ---- | ------ |
| 1 | `web_fetch` every URL; supplement with `web_search` if thin |
| 2 | Extract **platform_capabilities** with Class A summaries from web evidence |
| 3 | Map capabilities to relevant `customer_pain_points[]` with honest `applicability` |
| 4 | Extend `innovation_opportunities[]` with dual anchors: PWS chunk + capability where applicable |
| 5 | Brief section `## Capability overlay (user-directed)` — substantive table + risks + proof checklist |

**Anti-pattern:** Two closing sentences tagged onto the brief. **Pattern:** Capture-manager-ready overlay the BD lead can sanity-check before proposal-generator.

Mark external claims with `evidence_url` or `external_provenance: web`. Do not claim past performance or contract wins for the vendor unless the user provided them.

## Educational tone in `brief.md`

Remain **insightful and educational** (explain *why* a signal matters to a capture lead learning the domain) while **grounded** (citations on every fact). Separate:

- **What the document says** (Class A)
- **What we infer and why** (Class B with visible markers)
- **Where a bidder might differentiate** (Class B, customer-grounded, with `fit_to_scope` honesty)