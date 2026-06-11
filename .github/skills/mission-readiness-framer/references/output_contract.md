# Mission Readiness Framer — Output Contract

Every run emits **both**:

1. `artifacts/brief.md` — capture-team narrative (citation discipline in SKILL.md)
2. `artifacts/mission_readiness_frame.json` — machine-readable envelope for Briefings / `proposal-generator`

## Philosophy (read before filling)

- **Program office = customer** (requirement owner, bill payer, readiness accountable).
- **CO / contracts shop = administrator** — shapes how workload is bought and scored; not the mission customer.
- **Contract = workload enabler** — instruments readiness; it is not the mission itself.

## Required JSON top-level keys

```json
{
  "opportunity_context": {
    "solicitation_id": "...",
    "agency": "...",
    "package_documents": ["PWS", "Section M", "..."]
  },
  "mission_readiness_frame": {
    "readiness_outcome": "...",
    "confidence": "high|medium|low",
    "source_chunk_ids": [],
    "failure_modes_feared": [],
    "workload_enablers": [
      {
        "label": "...",
        "readiness_link": "...",
        "source_chunk_ids": []
      }
    ],
    "readiness_signals": [
      {
        "signal": "...",
        "type": "explicit|proxy",
        "source_chunk_ids": []
      }
    ],
    "our_read": "..."
  },
  "customer_pain_points": [
    {
      "id": "PP-001",
      "text": "...",
      "source_role": "program_office",
      "anxiety_level": "high|medium|low",
      "sections_echoed": [],
      "readiness_link": "...",
      "source_chunk_ids": [],
      "recommended_response_type": "mitigation|proof|transition"
    }
  ],
  "importance_signals": [
    {
      "id": "IS-001",
      "signal_type": "explicit_weight|repetition|section_order|qasp_consequence|amendment_emphasis|background_eval_echo",
      "source_role": "program_office|co|both",
      "what_it_suggests": "...",
      "confidence": "high|medium|low",
      "source_chunk_ids": []
    }
  ],
  "implicit_criteria": [
    {
      "id": "IC-001",
      "label": "...",
      "customer_read": "...",
      "acquisition_read": "...",
      "alternate_read": "...",
      "confidence": "high|medium|low",
      "linked_evaluation_factors": [],
      "source_chunk_ids": []
    }
  ],
  "win_theme_candidates": [
    {
      "id": "WT-001",
      "theme_label": "...",
      "why_the_customer_cares": "...",
      "readiness_link": "...",
      "proof_required": [],
      "linked_hooks": [],
      "evaluation_factor_links": [],
      "priority": 1,
      "source_chunk_ids": []
    }
  ],
  "clarification_questions": [],
  "claim_gaps": [],
  "citations": {
    "kg_entities": [],
    "kg_chunks": []
  }
}
```

## Discipline

- Every array entry cites `source_chunk_ids[]` or `entity_id` from tool output.
- `implicit_criteria` must include `alternate_read` when `confidence` is not `high`.
- `win_theme_candidates` are **seeds only** — no FAB chains or proposal prose.
- If readiness language is absent, use proxy signals and set `confidence` accordingly; do not invent outcomes.