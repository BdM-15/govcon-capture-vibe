# Differentiation Exploration — Pain, Themes, Methods, Innovation

> Extend the Mission Readiness Frame with **exploratory but grounded** capture intelligence: non-obvious pains, theme opportunities with rationale, what methods the customer already uses, and where we can differentiate — including via `company_capabilities` in the KG.

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

## Layer C — `company_capabilities` cross-walk (KG ontology)

The workspace may include ontology entities (`technology`, `past_performance_reference`, `strategic_theme`, `program`) from `company_capabilities`.

### Workflow

1. `kg_entities` — pull capability-related types (see SKILL.md step 1).
2. For each `innovation_opportunity` or `win_theme_candidate`, search for **supporting** capability entities:
   - Match on: system names, mission domain (sustainment, prepositioning, BOS), technology keywords in PWS.
3. Emit `company_capability_matches[]`:

```json
{
  "id": "CCM-001",
  "capability_entity": "Intelligent Asset Management (IAM)",
  "match_basis": "PWS mandates PMCS throughput; IAM supports predictive maintenance",
  "linked_to": ["WT-001", "IO-002"],
  "proof_strength": "strong|moderate|weak|gap",
  "entity_id": "...",
  "source_chunk_ids": ["..."]
}
```

- `proof_strength: gap` when we have no ontology proof — say so; do not fabricate deployments.
- Prefer `SUPPORTED_BY` relationships in KG when present (`kg_query` optional).

### Chain handoff

`company_capability_matches[]` feeds `proposal-generator` / future win-theme-spine skill — this skill only **maps** opportunities to proof inventory.

## Educational tone in `brief.md`

Remain **insightful and educational** (explain *why* a signal matters to a capture lead learning the domain) while **grounded** (citations on every fact). Separate:

- **What the document says** (Class A)
- **What we infer and why** (Class B with visible markers)
- **What we could offer** (Class B + capability match, with `fit_to_scope` honesty)