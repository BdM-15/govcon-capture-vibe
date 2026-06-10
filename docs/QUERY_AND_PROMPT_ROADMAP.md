# Query & Prompt Roadmap (parked work after #192)

**Status:** Parked follow-on work after #192. Query persona v3.7.0 restores #69 core; depth tiers moved to prompt library. Branch `192-query-prompt-tone`.
**Tracker:** GitHub issue #184  
**Last updated:** 2026-06-10

This document captures agreed direction and parked ideas from the prompt/query dialogue so follow-on branches do not lose context.

---

## 1. Current branch scope (#192)

### Goal

Tiered/conditional query persona: **grounded retrieval + reasoning as SME colleague**, not pure LightRAG and not v3.0 super-consultant.

### Agreed architecture

| Layer | Source | Keep? |
|-------|--------|-------|
| Base persona | pre-v3.0 strategic analyst (#69, `0d2a31f^`) | Yes |
| Guardrails | v3.1–v3.3+ (Phase 4–6 scope, inline `[N]`, UCF/non-UCF entities, ontology vs fact, template placeholders) | Yes |
| Consultant drift | v3.0 mandatory implication-per-fact, Shipley glossary lecture, unprompted pattern dumps | No |
| v3.5.0 over-correction | answer-first analyst, no unsolicited strategy | Revisit — may be too thin |

### Response depth (prompt library, not system persona — v3.7.0)

Depth and format live in **prompt-library starters**, not rigid tiers in the system prompt. v3.7.0 restores #69 core (thoroughness, strategic analysis) with v3.1–v3.3 guardrails.

1. **Lookup / comprehension** — scope primer, site inventory (library prompts).
2. **Elaboration** — topic deep-dive `{topic}`.
3. **Strategic** — win themes, volume blueprint, eval decoder.
4. **Forensic** — forensic domain analysis `{focus}`.

**Parked:** Prompt library CRUD — see dedicated GitHub issue (user workspace overrides).

### Prompt Library (consolidated starters)

Derived from saved workspace examples (MCPP, ATG Global, DLA Tire, Y12). Consolidate ~12–15 entries instead of duplicating hand-jammed variants. See dialogue on branch `192` for draft prompt text.

Categories to add vs current `prompt_library.py`:

- Scope & services primer (most-used entry point)
- Site/location inventory & patterns
- Topic deep-dive `{topic}`
- Evaluation criteria decoder (entity-type aware)
- Volume-by-volume proposal blueprint (MCPP pattern)
- Forensic domain analysis `{focus}` (payment, shipping, capital, etc.)
- Financial / cash-flow risk scan

### Validation

Use **current workspace** with **new** ad-hoc queries — not `docs/NATIVE_QUALITY_BAKEOFF_AFCAP5_ISR.md` known-answer set.

---

## 2. Bypass mode (clarification)

### How it works today

- `bypass` is a **per-chat** query mode (`currentChat.mode`), selectable in chat header dropdown.
- On bypass: **no RAG retrieval** (`aquery_data` skipped; no sources panel).
- **Conversation history still travels** with each message via `chat_store.build_history()` → passed to `query_func(..., history, ...)`.
- Prior assistant turns in the same chat **are** context — user does **not** need to paste Theseus output.

### User workflow (MCPP tax, ASRC warehouses, DOE policy)

1. Run grounded Theseus queries in `mix` / `hybrid` (tiers 1–4).
2. Toggle chat to `bypass` (or send with bypass — see UX gap below).
3. Ask external-research question; model reasons over **chat history** + cloud capabilities without re-retrieving workspace docs.

### Prompt Library implication

Bypass prompts should **not** include `[PASTE THESEUS OUTPUT HERE]`. Wording example:

> Using the conversation above as grounded RFP context, research {external_topic}. Label (A) from prior messages, (B) from external sources, (C) synthesis. Do not contradict cited facts from earlier turns.

### Rerank threshold wiring (fixed in #192 follow-up)

`govcon_rerank_func` previously filtered using global `.env` `MIN_RERANK_SCORE` only, ignoring per-workspace UI `min_rerank_score`. The UI bridge now binds the workspace value via `set_active_min_rerank_score()` for each query and logs `Query tunables: {...}` at INFO.

LightRAG still applies a second filter in `utils.py` using `lightrag.min_rerank_score` (also set by the bridge).

### Mix-mode token budget (why "9 sources" is normal)

Retrieval stages are not the same as final LLM context:

1. Merge many candidate chunks (e.g. 65)
2. Rerank + `chunk_top_k` cap (e.g. 30)
3. **Token budget**: `max_total_tokens` minus system prompt minus KG entities/relations → remaining room for text chunks (often single digits on large graphs)

`max_total_tokens` is input budget, not output length. Raising it (and clicking **Save** in Query Tuning) increases chunk slots; lowering `top_k` on overview queries also helps.

### Parked UX (#89 adjacent): per-send bypass

**Request:** Option to select bypass **before Send** on a single message, without changing whole-chat mode.

**Today:** Mode is chat-level only (`PATCH /chats/{id}` + header `<select>`).

**Future options:**

- Per-message `mode` override on `POST /chats/{id}/messages/stream` body (fallback to chat default).
- Composer toggle: “Bypass retrieval for this message” (sets override).
- Visual badge on messages sent in bypass.

**Branch suggestion:** `193-bypass-per-send` or fold into #89 bypass UX.

---

## 3. Insight follow-up & exploratory threads

### Problem (old LightRAG web UI)

Reasoning model occasionally surfaced a valuable insight; user could not easily **follow up in-thread** (“focus this idea — why did you suggest that?”).

### Hypothesis: conversational chat fixes most cases

Multi-turn history + tiered system prompt should allow:

- “Expand on the APSR integration point you raised.”
- “Why is NET 30 vs government receivables a Critical risk — walk me through the evidence.”

No new feature required if follow-ups stay in the **same chat** with retrieval still on (`mix`).

### Parked feature: `/handoff` or “Focus thread”

When an insight deserves a **clean exploratory branch** without losing RAG:

| Aspect | Spec sketch |
|--------|-------------|
| Trigger | User selects assistant passage → “Focus in new chat” or `/handoff` |
| Seed | New chat preloaded with: (1) quoted insight + user framing question, (2) optional `rfp_context` summary, (3) links to source message IDs |
| Mode default | `mix` or `hybrid` (retrieval on) |
| Persona | Elaboration tier — exploratory reasoning encouraged, grounding required for RFP facts |
| Not | Full bypass — unless user explicitly switches |

**Difference from bypass:** Handoff = new chat, **with** retrieval, scoped to develop one insight. Bypass = same chat, **no** retrieval, external augmentation.

**Branch suggestion:** `194-chat-insight-handoff`

---

## 4. Prompt patterns → skills & RFP Intelligence pages

**Yes** — consolidated Prompt Library tiers are a good decomposition map for “super skills” into smaller, reliable units.

Principle: **one prompt tier ≈ one skill contract or one Intelligence page section**.

| Prompt tier | Skill / page direction | Notes |
|-------------|------------------------|-------|
| Scope primer | `rfp-orientation` or Intel tab “Contract overview” | Read-only, citation-heavy; low hallucination risk |
| Site inventory | `site-scope-analyzer` | Table output; feeds workload / logistics skills |
| Topic deep-dive | Parameterized sub-skill or Intel drill-down | `{topic}` from entity catalog |
| Evaluation decoder | Extend `rfp-reverse-engineer` or Intel “Evaluation” | Entity-type aware, not literal Section M |
| Volume blueprint | `proposal-planner` (outline only) | MCPP-style four-block structure |
| Forensic `{focus}` | Family: `payment-terms-auditor`, `logistics-sla-auditor`, `capital-obligations-auditor` | Shared skeleton, different focus slot |
| Cash-flow risk scan | Handoff to `price-to-win` / BOE | Similar to workload-analyzer → PTW envelope |
| Bypass companions | Not skills — chat mode + short library prompts | External research only |

### Super-skill decomposition pattern

```
[Orientation skill] → artifact: scope_summary.md
[Forensic payment skill] → artifact: payment_terms_table.json
[Cash-flow risk skill] → artifact: ptw_handoff.json (reuse chain_contracts pattern)
[proposal-generator] → consumes artifacts → .docx
```

Aligns with existing `SkillChainExecutor` artifact promotion and `chain_contracts.py` semantic products.

### RFP Intelligence page builds

Intel UI can mirror Prompt Library tiers as **fixed sections** populated by running the matching skill/prompt once per workspace refresh:

- Overview | Sites | Evaluation | Financial risk | Logistics SLAs

Each section = one focused skill run, not one monolithic “analyze everything” skill.

**Branch suggestion:** `195-intel-page-slices` (after prompt library stable)

---

## 5. Proposed branch sequence (after #192 merges)

| Order | Branch | Depends on | Delivers |
|-------|--------|------------|----------|
| 1 | `192-query-prompt-tone` | — | Tiered `rag_response`, consolidated Prompt Library |
| 2 | `193-bypass-per-send` | 192 | Composer bypass toggle; library bypass prompts without paste |
| 3 | `194-chat-insight-handoff` | 192 | Focus insight → new grounded chat |
| 4 | `195-forensic-prompt-skills` | 192 | payment/logistics/capital micro-skills from forensic template |
| 5 | `196-intel-page-slices` | 195 | RFP Intelligence sections backed by slice skills |

---

## 6. References

- System prompt history: `prompts/govcon_prompt.py` changelog (v2.2 #69 → v3.0 → v3.5.0)
- Query slice: `prompts/govcon/query.py`
- Prompt Library: `src/server/prompt_library.py`
- Chat / bypass: `src/server/chat_routes.py`, `CONTEXT.md` (Chat, Query modes)
- Skill chaining: `src/skills/chain_contracts.py`, `docs/SKILLS.md`
- Bypass UX tracker: README #89