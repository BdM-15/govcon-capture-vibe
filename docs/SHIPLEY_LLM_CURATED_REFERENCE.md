# Shipley-Aligned Training Reference (Curated, Paraphrased)

Purpose: Provide non-proprietary, paraphrased guidance derived from standard capture/proposal best practices to shape LLM training data. This document avoids copying text from any commercial publications and instead summarizes widely known concepts for federal capture and proposal work. Use this as the authoritative reference when crafting instruction/response pairs and evaluation checks.

## How to Use This File in Training

- Treat each bullet as a “fact source” the model should learn to reproduce or apply.
- When generating examples, include short context snippets that cite this file (by section) plus schema fields from USAspending data.
- Pair each instruction with: expected answer, rationale, and which section(s) below informed the answer.

## Capture Milestones (M0–M3) and Gate Themes

- M0 – Opportunity Identification
  - Goal: Confirm relevance and basic feasibility.
  - Questions: Does it match NAICS/PSC target areas? Is the customer fit clear? Any set-aside constraints? Is timing realistic?
  - Data cues: Period-of-performance windows, parent agency hierarchy, contract vehicle, recent similar awards.
- M1 – Assessment/Validation
  - Goal: Decide to pursue with resources.
  - Questions: Who is the incumbent? Competition level? Budget realism? Preliminary teaming needs? Price range from history?
  - Data cues: Number of offers received (competitiveness), historical obligations, pricing type, vehicle usage patterns.
- M2 – Bid/No-Bid
  - Goal: Commit to bid with strategy in place.
  - Questions: Differentiators? Teaming finalized? Compliance risks? Price-to-win range? Past performance fit?
  - Data cues: Agency preferences, award type and pricing, set-aside specifics, incumbent modification cadence.
- M3 – Proposal Strategy Validation
  - Goal: Ensure proposal aligns to strategy and evaluation factors.
  - Questions: Are themes/discriminators clear? Is compliance airtight? Are price and technical trade-offs defensible?
  - Data cues: Evaluation factor patterns from similar awards, agency trend lines, geographic/labor rate context.

## Core Capture Artifacts (Summarized)

- Capture Plan: Opportunity summary, customer map, win themes, competitor profiles, teaming plan, call plan actions.
- Win Strategy: Discriminators tied to customer outcomes; evidence drawn from historical awards and references.
- Competitive Analysis: Incumbent posture, likely competitors, SWOT, “ghosting” opportunities, pricing posture.
- Teaming Plan: Roles/capabilities matrix, set-aside eligibility, gaps coverage, contact and decision timelines.
- Price-to-Win Notes: Range anchored to historical obligations, pricing type norms, geographic wage context.
- Call Plan: Stakeholders, tailored questions, proof points, next steps; logs that convert discovery to actions.

## Proposal Artifacts (Summarized)

- Compliance Matrix: Maps RFP sections to proposal responses; ensures no requirement is missed.
- Annotated Outline: Section-by-section plan with themes, evidence, and graphic callouts.
- Storyboards: Visual-first drafts aligning to themes and customer benefits.
- Color Team Reviews: Pink (concept), Red (customer voice/compliance), Gold (final polish/consistency).

## Typical Evaluation Factors (FAR-style)

- Technical/Management Approach: Understanding, feasibility, risk controls, staffing, schedule.
- Past Performance/Relevance: Similarity in scope/size/complexity, quality ratings, recency.
- Cost/Price: Realism, reasonableness, balance; pricing type alignment (FFP, CPFF, T&M).
- Small Business Participation: Prime/sub plans, goals, and documented approach.
- Others as applicable: Cybersecurity posture, key personnel qualifications, transition plan.

LLM behaviors to train:

- Extract factors from RFP-like prompts and map them to proposal sections.
- Recommend discriminators that match the factors and customer mission outcomes.
- Flag missing compliance items or risky assertions.

## Competitive Analysis Patterns (Summarized)

- Incumbent Indicators: Long performance periods, steady modifications, high utilization vs ceiling.
- Market Concentration: Few bidders and recurring winners within a NAICS/agency cluster.
- Vehicle Dynamics: Multiple-award IDVs imply recurring task-order competitions; single-award reduces competitors.
- Discriminator Design: Tie capability strengths to customer outcomes; identify “ghosting” angles ethically.

## Risk Management (Concise)

- Common Risk Types: Staffing, transition, schedule, integration, security, subcontractor dependency.
- Mitigation Themes: Cross-training, phased transition, surge capacity, quality gates, SLAs, reserves/management controls.
- Train the model to: Identify risks from short narratives and propose mitigations aligned to evaluation factors.

## Business Rules for Contract Data (Reinforcement)

- Contracts vs. Modifications:
  - Base award: modification_number = '0' (the actual contract award).
  - Any other modification_number indicates a change to an existing award (funding, scope, time, admin).
  - “P” mods often refer to admin funding changes (pattern P00001, etc.).
- IDV and Orders:
  - Indefinite vehicles (IDV/IDIQ/BPA) issue task/delivery orders.
  - parent_award_id_piid links the order to its vehicle; award_id_piid is the order identifier.
- Set-Asides and Competition:
  - type_of_set_aside indicates socioeconomic reservations; extent_competed signals openness of the market.
- Pricing Structures:
  - type_of_contract_pricing drives risk: FFP (vendor risk), cost-type (government shares risk), T&M (labor-hour centric).

LLM behaviors to train:

- Always respect “base vs mod” distinction in summaries, stats, and recommendations.
- Detect IDV contexts and infer pursuing future orders via on-ramp or teaming.
- Explain set-aside constraints and teaming implications.

## Data-Supported Pricing Intelligence (Non-proprietary)

- Historical Benchmarks: Use median/percentiles by NAICS/agency/pricing type as price anchors.
- Wage Context: Align labor categories to public wage data (e.g., BLS OEWS) and awarded rates (e.g., CALC) for justification ranges.
- Competition Sensitivity: Higher bidder counts generally compress price; single-bidder contexts often allow stronger margins.

LLM behaviors to train:

- Propose a defensible price band and justify with public benchmarks.
- Call out when pricing type implies specific risk controls (e.g., EVMS for cost-type).

## Dataset-Ready Task Shapes (Examples)

- Classification:
  - Input: Award record subset; Task: Identify if base award, modification, or order under IDV; Output: one of [BASE, MOD, ORDER].
- Relationship Reasoning:
  - Input: Records with parent_award_id_piid and award_id_piid; Task: Explain parent-child linkage and pursuit path.
- Competition Insight:
  - Input: Aggregated number_of_offers_received by agency/NAICS; Task: Describe competitiveness and suggest strategy.
- Evaluation Mapping:
  - Input: RFP-style factor list; Task: Produce outline segments with themes and discriminators.
- Risk/Mitigation:
  - Input: Short scenario; Task: Identify top 3 risks and concise mitigations.
- Pricing Justification:
  - Input: NAICS, region, pricing type; Task: Provide price band with data-backed rationale.

## Prompt Augmentation with Authoritative References

- USAspending “References” endpoints (Glossary and Data Dictionary) should be used to append brief definitions for fields present in the prompt (e.g., extent_competed, type_of_set_aside, type_of_contract_pricing).
- Cache responses locally with date/version; include provenance in metadata.
- Keep definitions short (1–2 sentences) to preserve context window while improving terminology fidelity.

## Acceptance Checks for Generated Answers

- Contract vs Mod rule applied correctly (no double-counting mods as separate contracts).
- If an order references an IDV, mention the vehicle context and ordering implications.
- Set-aside guidance is consistent with the stated category; teaming advice is feasible.
- Evaluation factor responses include compliance thread and discriminators.
- Pricing advice cites public benchmarks and aligns with pricing type risk.

---

This curated reference is a living document. Update as new patterns emerge, but keep wording generic, paraphrased, and free of proprietary text.
