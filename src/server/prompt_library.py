"""Curated Shipley suggested-prompt catalog for the Theseus UI."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

LlmFunc = Callable[[str], Awaitable[str]]

_SHIPPED_NAMESPACE = uuid.UUID("8f4e3c2a-9b1d-4e5f-a6c7-d8e9f0a1b2c3")
VALID_PHASES = frozenset({"4", "5", "6"})
REFINE_ACTIONS = frozenset({"clarity", "shorter", "citations", "structure"})

REFINE_SYSTEM = """You refine GovCon capture/proposal prompt starters for a RAG workbench.
Rules:
- Preserve intent, placeholders like {topic}, {focus}, {section_or_task}, and Shipley phase context.
- Keep prompts grounded: require [N] citations for factual claims where appropriate.
- Do NOT add markdown formatting instructions (handled elsewhere).
- Return ONLY the revised prompt text — no preamble, no quotes, no explanation."""

REFINE_USER_TEMPLATES = {
    "clarity": "Improve clarity and plain-language readability. Expand acronyms on first use where helpful.\n\nPrompt:\n{prompt}",
    "shorter": "Tighten this prompt: remove redundancy, keep all requirements and placeholders.\n\nPrompt:\n{prompt}",
    "citations": "Strengthen citation discipline: every factual claim must cite retrieved evidence with [N]. Keep length similar.\n\nPrompt:\n{prompt}",
    "structure": "Improve structure with a clear ordered outline (bullets or numbered steps) while keeping the same task scope.\n\nPrompt:\n{prompt}",
}


PROMPT_LIBRARY: list[dict[str, str]] = [
    # ═════════════════ Phase 4 — Proposal Planning ═════════════════
    # ── Discovery & orientation (content only — formatting via LightRAG + query settings) ──
    {"phase": "4", "category": "Discovery", "title": "Scope & services primer",
     "prompt": "Provide an overview of the scope and services for this contract. Use an educational tone in plain language; expand acronyms on first use. Stay grounded in retrieved document terminology and facts — cite with [N]. Explain structure: contract type, periods, task/service areas (walk major PWS/SOW sections with substantive detail per area), major deliverables, and key performance mechanisms. CLINs are supporting structure only; prioritize what the contractor must perform. Assume a reader new to this procurement who is not a domain SME. Prioritize clarity and completeness over brevity. Do not append unsolicited win themes or capture strategy."},
    {"phase": "4", "category": "Discovery", "title": "Site & location inventory",
     "prompt": "Summarize all sites and locations in scope. Organize by country, then region. Note counts where the documents support them. Identify geographic clusters, OCONUS vs CONUS concentration, and any site-specific appendix patterns. Flag data gaps. Cite every factual claim with [N]."},
    {"phase": "4", "category": "Discovery", "title": "Topic deep-dive",
     "prompt": "Deep-dive on: {topic}. Use retrieved evidence first. Structure: what the documents require → how it is performed or measured → dependencies and interfaces → compliance or performance risks visible in the text. Add brief proposal implications only where directly supported by cited facts. Cite every factual claim with [N]."},
    {"phase": "4", "category": "Discovery", "title": "Evaluation criteria decoder",
     "prompt": "Decode all evaluation_factor and subfactor entities (UCF Section M or equivalent — adjectival, LPTA, or non-UCF schemes). For each: what the government is evaluating; stated weights or rating definitions if present; evidence or proof they expect; what a strong vs weak response looks like per document language; pain points implied; proposal volumes or sections that must answer it. Ground every row in [N] citations. Label Shipley interpretation separately from document facts."},
    {"phase": "4", "category": "Strategy", "title": "Volume-by-volume proposal blueprint",
     "prompt": "Build a volume-by-volume proposal blueprint from the proposal_instruction and evaluation_factor entities. For each volume or evaluation factor, provide four blocks: (1) Compliance checks — page limits, format, submission mechanics, required artifacts; (2) Content specifics — what must be addressed, keyed to SOW/PWS sections and CLINs; (3) Customer pain points — only those supported by retrieved context; (4) Solutioning angles — proposal implications tied to cited requirements; flag assumptions. Do not invent pain points not evidenced in the workspace."},
    {"phase": "4", "category": "Forensic", "title": "Forensic domain analysis",
     "prompt": "Perform a forensic analysis of: {focus}. Search proposal_instruction, evaluation_factor, requirement, deliverable, clause, and PWS/SOW chunks (UCF and non-UCF). Deliver in order: (1) Executive summary — one paragraph, grounded; (2) Verbatim extracts — quote exact language with section/page refs and [N] citations; (3) Summary table(s) appropriate to {focus}; (4) Risk and performance implications — H/M/L with cited basis; (5) Proposal implications — only actions supported by documents. For common focuses, prefer Agent Skills: payment-terms-auditor (payment/cash flow by CLIN), logistics-sla-auditor (OTD/FR/shipping), capital-obligations-auditor (upfront capital/inventory)."},
    {"phase": "4", "category": "Forensic", "title": "Payment terms by CLIN (skill)",
     "prompt": "Run the payment-terms-auditor skill on this workspace. Forensic focus: payment terms and cash-flow timing by CLIN. Require verbatim extracts, a CLIN cash-flow table, H/M/L risks, and BOE implications — all cited to chunk_ids from the workspace."},
    {"phase": "4", "category": "Forensic", "title": "Logistics SLAs & OTD/FR (skill)",
     "prompt": "Run the logistics-sla-auditor skill on this workspace. Forensic focus: shipping destinations, on-time delivery, fill rate, and surge logistics SLAs. Require verbatim extracts, destination/metric tables, H/M/L risks, and proposal implications — all cited."},
    {"phase": "4", "category": "Forensic", "title": "Capital & inventory obligations (skill)",
     "prompt": "Run the capital-obligations-auditor skill on this workspace. Forensic focus: upfront capital, inventory ownership, disposition, and transition property obligations. Require verbatim extracts, obligation tables, H/M/L risks, and financing/BOE implications — all cited."},
    {"phase": "4", "category": "Pricing", "title": "Financial & cash-flow risk scan",
     "prompt": "What contractor financial risks does this procurement create — especially cash flow, seed capital, working capital, and payment timing mismatches? Cite the driving clauses with [N]. Quantify where the documents provide numbers. Flag what a basis-of-estimate or financing narrative must address in the proposal."},
    {"phase": "4", "category": "Bypass", "title": "External research enhancement",
     "prompt": "Using the conversation above as grounded RFP context, research and analyze: {external_topic}. Do not contradict cited facts from earlier turns. Label clearly: (A) from prior conversation, (B) from external sources, (C) your synthesis. Focus on proposal and pricing implications for this opportunity. Switch chat mode to bypass before sending."},
    {"phase": "4", "category": "Bypass", "title": "Incumbent capability research",
     "prompt": "Using the conversation above as grounded context on scope, performance metrics, and transition requirements, research publicly available information about incumbent {company} capabilities relevant to this requirement. Deliver: facility or network summary table, capability claims vs RFP requirements, incumbent advantage assessment, transition risk, gaps our solution must close. Label external claims with source. State uncertainty where data is incomplete. Switch chat mode to bypass before sending."},
    # ── Compliance & planning ──
    {"phase": "4", "category": "Compliance", "title": "Full Compliance Matrix (Instructions ↔ Evaluation)",
     "prompt": "Generate a full proposal-instruction ↔ evaluation-factor compliance matrix. For every proposal_instruction (UCF Section L or equivalent — non-UCF task orders, FOPRs, BPA calls, OTAs may name the section differently or embed instructions inline in the PWS), list the linked evaluation_factor (UCF Section M or equivalent — including adjectival or LPTA schemes), the responsible proposal volume, page-limit constraints, and any unmatched items as gaps. Tag each row with instruction_source (UCF-L | non-UCF | PWS-inline | attachment) and evaluation_source (UCF-M | non-UCF | adjectival | LPTA). Do NOT emit GAP merely because an entity lacks a literal 'Section L' / 'Section M' heading."},
    {"phase": "4", "category": "Compliance", "title": "Cross-reference matrix (9-column)",
     "prompt": "Create a proposal cross-reference matrix with nine columns: Section Number, Section Title, Proposal Instructions, Evaluation Criteria, SOW/PWS, Other, Author, Pages, Status. Populate Section Number/Title from the proposal outline implied by the proposal_instruction entities, the Proposal Instructions column from those proposal_instruction entities (UCF Section L or equivalent), the Evaluation Criteria column from the evaluation_factor entities (UCF Section M or equivalent), and the SOW/PWS column from the statement-of-work paragraphs. Works for UCF and non-UCF formats (FAR 16 task orders, FOPRs, BPA calls, OTAs, agency-specific). Leave Author/Pages/Status blank for the team to fill."},
    {"phase": "4", "category": "Compliance", "title": "Verify outline accuracy",
     "prompt": "Verify the accuracy of the draft outline language against the actual proposal_instruction entities (UCF Section L or equivalent — may live in a named attachment or inline in the PWS for non-UCF solicitations), then verify the Evaluation Criteria column language against the actual evaluation_factor entities (UCF Section M or equivalent — including adjectival or LPTA schemes), then verify the SOW/PWS column references against the actual statement of work. Surface any drift, paraphrase that loses meaning, or missing requirements."},
    {"phase": "4", "category": "Compliance", "title": "Page limits & format constraints",
     "prompt": "List every page limit, font, margin, line spacing, file-format, naming-convention, and submission-mechanic constraint stated anywhere in the RFP. Cite the source clause for each. Flag conflicts."},
    {"phase": "4", "category": "Compliance", "title": "Submission checklist",
     "prompt": "Build a submission checklist: every artifact required (volumes, certifications, reps & certs, oral-presentation slides, pricing files, model contract), the format, the page limit, the section that imposes the requirement, and the responsible owner."},
    {"phase": "4", "category": "Discovery", "title": "Unclear requirements & questions to ask",
     "prompt": "Identify requirements that are ambiguous, contradictory, or missing detail. For each: quote the source, explain why it is unclear, and draft 2-3 specific questions we should ask the contracting officer (or address in our assumptions section)."},
    {"phase": "4", "category": "Strategy", "title": "Win themes & discriminators",
     "prompt": "Identify candidate win themes, discriminators, and proof points implied by the indexed RFP. Map each to the customer priority or pain point it addresses, and to the evaluation factor it would influence. Distinguish true discriminators (likely unique to us) from table stakes."},
    {"phase": "4", "category": "Strategy", "title": "Solution architecture brief",
     "prompt": "Sketch a solution architecture brief: technical approach pillars, management approach pillars, staffing model assumptions, transition approach, and risk mitigations. Tie each pillar to the evaluation_factor it earns credit against (UCF Section M or equivalent — including adjectival or LPTA schemes) and to the customer pain point it addresses."},
    {"phase": "4", "category": "Strategy", "title": "Ghost language opportunities",
     "prompt": "Identify themes and language we can ghost to highlight likely competitor weaknesses without naming them. Anchor each ghost in a customer pain point, a likely competitor gap, and the evaluation factor it would influence."},
    {"phase": "4", "category": "Pricing", "title": "Workload & BOE drivers",
     "prompt": "Pull every workload metric, performance standard, deliverable count, frequency, surge condition, and skill-mix indicator that drives basis of estimate. For each: cite the RFP location, note the unit of measure, and flag where the data is ambiguous or missing."},
    {"phase": "4", "category": "Pricing", "title": "Labor category mapping",
     "prompt": "For task {section_or_task} (or every task if none specified): identify the most suitable labor categories and skill levels from the contract vehicle's labor matrix. For each: name the category, the skill level, the matching responsibilities, and a justification tying experience-level requirements to the task complexity. Flag any task that does not map cleanly to a defined category."},
    {"phase": "4", "category": "Risk", "title": "Risk register & mitigations",
     "prompt": "Build a risk register from the RFP: technical, schedule, cost, transition, security, supply-chain, and integration risks. For each: cite the source language, score likelihood × impact (Low/Med/High), name the owner, propose a mitigation, and identify the proposal section that will describe the mitigation."},
    {"phase": "4", "category": "Risk", "title": "Detailed project risk assessment",
     "prompt": "Perform a detailed risk assessment for the as-bid solution. Categorize risks as technical, financial, operational, strategic, and compliance. For each risk: probability (L/M/H), impact severity (L/M/H), risk score (probability × impact), specific mitigation strategies, required resources for mitigation, and the responsible owner. Format the output as a prioritized risk matrix with recommended actions."},
    {"phase": "4", "category": "Risk", "title": "Vague-language / scrutiny risk scan",
     "prompt": "Review the indexed scope/PWS for vague, consultative, or non-outcome-based language (assess, analyze, support, recommendations, strategic planning, evaluating, developing models, conducting research). Compute a high-risk-verbiage percentage = (high-risk term occurrences / total word count) × 100. Classify: >4% Critical, 2.5-4% High, 1-2.5% Moderate, <1% Low. Then compute a positive-verbiage percentage for outcome-based terms (readiness, capability, mission, deliverable, performance) using the same formula. Surface the most concerning paragraphs for rewrite or risk-section coverage."},

    # ═════════════════ Phase 5 — Proposal Development ═════════════════
    {"phase": "5", "category": "Traceability", "title": "Requirements → Deliverables → BOE",
     "prompt": "Trace every shall/will requirement to its satisfying deliverable, performance standard, and workload metric. Flag any requirement with no satisfying deliverable as a coverage gap, and any deliverable with no parent requirement as scope creep."},
    {"phase": "5", "category": "Writing", "title": "Volume outline (Shipley-aligned)",
     "prompt": "Produce a Shipley-aligned proposal volume outline. For each volume, list its sections, the page budget derived from the relevant proposal_instruction entities (UCF Section L or equivalent), the evaluation_factor entities it must answer (UCF Section M or equivalent — including adjectival or LPTA schemes), and the win theme(s) it should carry."},
    {"phase": "5", "category": "Writing", "title": "Executive summary intro (pain → value prop)",
     "prompt": "Write the executive summary introduction by opening with the customer's most painful problem (framed as a burning question), then present our value proposition as the solution to that problem, then introduce our win theme and the relevant capabilities that prove we can deliver. Use active voice, short sentences, and no jargon. Cite the source for each customer pain point."},
    {"phase": "5", "category": "Writing", "title": "Executive summary full draft",
     "prompt": "Draft a full executive summary: open with the customer's mission challenge, state our solution promise, surface three discriminators each backed by a quantified proof point, and close with a benefit-anchored call to action. Stay within the page limit imposed by the relevant proposal_instruction entities (UCF Section L or equivalent — may live inline in the PWS or in a named attachment for non-UCF solicitations); default to 4 pages if no limit is stated."},
    {"phase": "5", "category": "Writing", "title": "Section storyboard",
     "prompt": "Storyboard a single proposal section: the proposal_instruction it answers (UCF Section L or equivalent), the evaluation_factor entities it earns (UCF Section M or equivalent), the win theme it carries, the proof points it cites, the graphic concepts, and the action caption for each graphic. Include placeholder counts for words and graphics so authors can budget."},
    {"phase": "5", "category": "Writing", "title": "Why-What-Who-How-When-Where-Wow framework",
     "prompt": "Develop a proposal section using the Why-What-Who-How-When-Where-Wow framework. Step 1 (Why): introductory paragraphs framed by the highest inherent risk and how our approach mitigates it. Step 2 (What): paragraphs detailing the benefits of our approach. Step 3 (Who): a sentence (with placeholder for names) describing who performs the work and their roles. Step 4 (How): paragraphs diving into implementation detail, mapped to the relevant statement-of-work paragraphs. Step 5 (When/Where): schedule and place-of-performance integration. Step 6 (Wow): the discriminator that lifts this section above competitor responses."},
    {"phase": "5", "category": "Writing", "title": "Capability narrative (active voice, 200-250 words)",
     "prompt": "Generate a clear, concise, compelling response in active voice that showcases our capabilities in {capability}. Structure: (1) strong assertive opening (1-2 sentences); (2) 3-4 key capabilities or achievements with specific metrics or outcomes (bullets); (3) brief success-story example (3-4 sentences); (4) examples of programs/platforms where we have implemented {capability} (include legacy platforms); (5) forward-looking conclusion tying us to future challenges (1-2 sentences). Active voice throughout. No jargon. Short impactful sentences. 200-250 words total."},
    {"phase": "5", "category": "Writing", "title": "Past performance narrative",
     "prompt": "Turn our past performance around {capability} into a narrative that shows we are a strong vendor/partner selection for the customer agency. For each cited past performance: name the customer, the period, the scope and scale, the outcomes (quantified), and the direct relevance to this opportunity's requirements and evaluation factors."},
    {"phase": "5", "category": "Writing", "title": "Past performance ↔ requirement match",
     "prompt": "For requirement {requirement_id} (or every requirement if none specified): list the past performances that demonstrate we have done this before, what we delivered, the customer outcome, and the evidence we can cite. Flag requirements with no matching past performance as proof-point gaps."},
    {"phase": "5", "category": "Writing", "title": "Task-driven proposal section",
     "prompt": "For task {section_or_task}: construct a compelling proposal response with these elements integrated into a natural narrative — Task Number; Task Heading; our step-by-step approach (name specific tools/methods, identify analysis steps, name the customer organizations we coordinate with); Discriminators (unique qualities, methods, or partnerships); Features and benefits that exceed the task requirements (efficiency, alignment, sustainability, risk reduction, mission outcomes); Proof Points (past projects with quantified outcomes). Cite source paragraphs for each claim and label any AI-pre-existing-knowledge content separately from indexed-document content."},
    {"phase": "5", "category": "Writing", "title": "Convert structured response to paragraph",
     "prompt": "Convert the previous structured (heading + bullet) response into proposal-ready paragraph form. Preserve every claim, every metric, every citation. Use active voice. No section headings within the paragraphs except the task heading."},
    {"phase": "5", "category": "Writing", "title": "RFI question response",
     "prompt": "Respond to the RFI question: '{requirement_text}'. Use the indexed past-performance and capability content. Make the response substantive (not just keyword-checking), use the keywords once each, and add concrete examples, metrics, and past customer outcomes that demonstrate we have done this before."},
    {"phase": "5", "category": "Strategy", "title": "FAB chain for top discriminator",
     "prompt": "For our most defensible discriminator, write a Feature → Advantage → Benefit chain grounded in cited proof points and tied to the relevant evaluation_factor (UCF Section M or equivalent) and customer hot button."},
    {"phase": "5", "category": "Strategy", "title": "Strength & benefit identification (eval-anchored)",
     "prompt": "Identify 3-4 strengths in our draft that meet the formal definition: 'an aspect of the proposal that has merit or exceeds specified requirements in a way advantageous to the government during contract performance.' For each strength: name the unique capability/method/technology, cite the proposal text, tie it to the specific evaluation_factor it influences (UCF Section M or equivalent — including adjectival or LPTA schemes), and articulate the quantifiable benefit (positive outcome) the customer gains. A benefit must be tangible, tied to evaluation criteria, and not merely 'potential value.'"},
    {"phase": "5", "category": "Strategy", "title": "Strength/benefit conciseness rewrite",
     "prompt": "Rewrite the provided strengths and benefits to be clear, concise, and table-cell-sized while preserving every quantitative claim and tie-back to evaluation criteria. Distinguish whether each item is genuinely a strength versus a benefit and reorganize accordingly. Output ready for a strength table."},
    {"phase": "5", "category": "Risk", "title": "Risk to operations from requirements",
     "prompt": "Identify and describe requirements that may pose a risk to operations after award. For each: quote the source language, name the risk category (integration, security, dependency, methodology, scale, complexity, transition), describe how it would manifest, and propose the mitigation we will offer in our management volume."},

    # ═════════════════ Phase 6 — Color Reviews & Submittal ═════════════════
    {"phase": "6", "category": "Review", "title": "Pink team feedback prompts",
     "prompt": "Generate Pink team review prompts for each volume: are win themes visible, are discriminators substantiated with cited proof, are graphics earning their space (action captions tied to themes), is compliance language unambiguous, are FAB chains complete, is the customer's mission outcome the subject of the verbs?"},
    {"phase": "6", "category": "Review", "title": "Red team challenge questions",
     "prompt": "Generate Red team challenge questions a tough source-selection evaluator would ask. For each: point to the proposal section that should answer it and the specific proof point that should land it. Flag questions our current draft cannot answer."},
    {"phase": "6", "category": "Review", "title": "Red team rewrite (Shipley expert)",
     "prompt": "Act as a Shipley-process expert performing a Red team review. For each response: provide detailed strengths, detailed weaknesses, and specific recommendations. Then provide a rewritten version of the answer that incorporates the recommendations. The rewrite must use active voice, mirror the existing response tone, reference appropriate doctrine where relevant, avoid blustery or overly complex language, avoid language patterns that signal LLM-generated text, and avoid em-dashes/en-dashes. Recommendations must be unbiased and worded as recommendations (not as commitments we are making)."},
    {"phase": "6", "category": "Review", "title": "Gold team executive narrative check",
     "prompt": "Read the executive summary and management volume openers as a Gold team would. Flag any place the customer's mission outcome is not the subject of the verbs, where benefits are not quantified, where discriminators read as table stakes, or where compliance language is missing."},
    {"phase": "6", "category": "Review", "title": "Gap analysis vs evaluation factors",
     "prompt": "Run a gap analysis: for each evaluation_factor and subfactor (UCF Section M or equivalent — including adjectival or LPTA schemes), list the proposal sections, deliverables, and proof points that respond to it. Highlight unanswered factors, weakly-answered factors, and factors answered in the wrong volume."},
    {"phase": "6", "category": "Review", "title": "Compliance review checklist",
     "prompt": "Generate a Pink/Red-team-executable compliance review checklist organized by proposal_instruction (UCF Section L or equivalent), with the matching evaluation_factor pass/fail criteria (UCF Section M or equivalent), the responsible volume, and a column for reviewer pass/fail/comment."},
    {"phase": "6", "category": "Review", "title": "Strengths & benefits enhancement review",
     "prompt": "Review the draft strength table. For each row: assess whether the strength is genuinely advantageous to the customer (not just a feature), whether the benefit is tied to evaluation criteria, and whether the language is clear and concise. Provide specific suggestions: quantify outcomes, tighten unique-capability language, add a brief success story, detail forward benefits, and (if available) cite a customer testimonial. Output a revised, table-ready version."},
    {"phase": "6", "category": "Review", "title": "Reflect on win strategy",
     "prompt": "Review the win strategies and themes we've adopted. Identify any risks we haven't considered, opportunities we haven't pursued, competitor counter-moves we haven't anticipated, and proof gaps that would weaken the strategy under Red-team scrutiny."},
    {"phase": "6", "category": "Submission", "title": "Final compliance sweep",
     "prompt": "Final pre-submission sweep: confirm every proposal_instruction (UCF Section L or equivalent) is answered, every evaluation_factor (UCF Section M or equivalent — including adjectival or LPTA schemes) is addressed, every page limit is met, every required artifact (volumes, certifications, reps & certs, pricing, model contract, oral slides) is named, every cross-reference is intact, and every page footer/header complies with format constraints."},
]


def shipped_prompt_id(phase: str, category: str, title: str) -> str:
    """Stable id for a shipped starter (deterministic across workspaces)."""
    key = f"{phase}|{category}|{title}"
    return str(uuid.uuid5(_SHIPPED_NAMESPACE, key))


def _normalize_shipped(entry: dict[str, str]) -> dict[str, str]:
    phase = str(entry["phase"]).strip()
    category = str(entry["category"]).strip()
    title = str(entry["title"]).strip()
    prompt = str(entry["prompt"]).strip()
    return {
        "id": shipped_prompt_id(phase, category, title),
        "phase": phase,
        "category": category,
        "title": title,
        "prompt": prompt,
        "source": "shipped",
    }


def shipped_defaults() -> list[dict[str, str]]:
    """Return shipped catalog with stable ids."""
    return [_normalize_shipped(entry) for entry in PROMPT_LIBRARY]


class PromptEntryCreate(BaseModel):
    phase: str = Field(min_length=1, max_length=4)
    category: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=20000)


class PromptEntryUpdate(BaseModel):
    phase: str | None = Field(default=None, max_length=4)
    category: str | None = Field(default=None, max_length=80)
    title: str | None = Field(default=None, max_length=160)
    prompt: str | None = Field(default=None, max_length=20000)


class PromptImportPayload(BaseModel):
    prompts: list[PromptEntryCreate] = Field(min_length=1, max_length=200)


class PromptRefinePayload(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)
    action: str = Field(default="clarity", max_length=32)


class PromptLibraryStore:
    """Per-workspace prompt library overrides layered on shipped defaults."""

    def __init__(self, *, workspace_dir: Callable[[], Path]) -> None:
        self._workspace_dir = workspace_dir

    def path(self) -> Path:
        return self._workspace_dir() / "ui_prompt_library.json"

    def defaults(self) -> list[dict[str, str]]:
        entries = shipped_defaults()
        entries.sort(key=self._entry_sort_key)
        return entries

    def _empty_overrides(self) -> dict[str, Any]:
        return {"hidden": [], "overrides": {}, "custom": []}

    def read_raw(self) -> dict[str, Any]:
        path = self.path()
        if not path.exists():
            return self._empty_overrides()
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed reading %s, using empty overrides: %s", path, exc)
            return self._empty_overrides()
        if not isinstance(loaded, dict):
            return self._empty_overrides()
        hidden = loaded.get("hidden") if isinstance(loaded.get("hidden"), list) else []
        overrides = loaded.get("overrides") if isinstance(loaded.get("overrides"), dict) else {}
        custom = loaded.get("custom") if isinstance(loaded.get("custom"), list) else []
        return {"hidden": hidden, "overrides": overrides, "custom": custom}

    def customized(self) -> bool:
        return self.path().exists()

    def _validate_phase(self, phase: str) -> None:
        if phase not in VALID_PHASES:
            raise ValueError(f"Unsupported phase: {phase}")

    def _entry_sort_key(self, entry: dict[str, str]) -> tuple[str, str, str]:
        return (entry.get("phase", ""), entry.get("category", ""), entry.get("title", ""))

    def read(self) -> list[dict[str, str]]:
        """Merge shipped defaults with workspace overrides."""
        raw = self.read_raw()
        hidden = {str(item) for item in raw["hidden"]}
        overrides: dict[str, Any] = raw["overrides"]
        merged: list[dict[str, str]] = []

        for entry in self.defaults():
            entry_id = entry["id"]
            if entry_id in hidden:
                continue
            patch = overrides.get(entry_id)
            if isinstance(patch, dict):
                merged.append({
                    **entry,
                    "phase": str(patch.get("phase", entry["phase"])).strip(),
                    "category": str(patch.get("category", entry["category"])).strip(),
                    "title": str(patch.get("title", entry["title"])).strip(),
                    "prompt": str(patch.get("prompt", entry["prompt"])).strip(),
                    "source": "shipped",
                })
            else:
                merged.append(dict(entry))

        for item in raw["custom"]:
            if not isinstance(item, dict):
                continue
            phase = str(item.get("phase", "")).strip()
            category = str(item.get("category", "")).strip()
            title = str(item.get("title", "")).strip()
            prompt = str(item.get("prompt", "")).strip()
            entry_id = str(item.get("id") or uuid.uuid4())
            if not (phase and category and title and prompt):
                continue
            merged.append({
                "id": entry_id,
                "phase": phase,
                "category": category,
                "title": title,
                "prompt": prompt,
                "source": "user",
            })

        merged.sort(key=self._entry_sort_key)
        return merged

    def write_raw(self, data: dict[str, Any]) -> None:
        path = self.path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _find_entry(self, entry_id: str) -> tuple[dict[str, str], str]:
        for entry in self.read():
            if entry["id"] == entry_id:
                return entry, entry["source"]
        raise KeyError(entry_id)

    def add(self, payload: PromptEntryCreate) -> dict[str, str]:
        phase = payload.phase.strip()
        self._validate_phase(phase)
        raw = self.read_raw()
        entry = {
            "id": str(uuid.uuid4()),
            "phase": phase,
            "category": payload.category.strip(),
            "title": payload.title.strip(),
            "prompt": payload.prompt.strip(),
            "source": "user",
        }
        raw["custom"].append(entry)
        self.write_raw(raw)
        return entry

    def update(self, entry_id: str, payload: PromptEntryUpdate) -> dict[str, str]:
        updates = payload.model_dump(exclude_none=True)
        if not updates:
            raise ValueError("No fields to update")
        if "phase" in updates:
            self._validate_phase(str(updates["phase"]).strip())

        raw = self.read_raw()
        shipped_ids = {item["id"] for item in self.defaults()}

        if entry_id in shipped_ids:
            current = next(item for item in self.defaults() if item["id"] == entry_id)
            patch = dict(raw["overrides"].get(entry_id, {}))
            for key in ("phase", "category", "title", "prompt"):
                if key in updates:
                    patch[key] = str(updates[key]).strip()
            raw["overrides"][entry_id] = patch
            self.write_raw(raw)
            merged = next(item for item in self.read() if item["id"] == entry_id)
            return merged

        for idx, item in enumerate(raw["custom"]):
            if not isinstance(item, dict) or str(item.get("id")) != entry_id:
                continue
            for key in ("phase", "category", "title", "prompt"):
                if key in updates:
                    item[key] = str(updates[key]).strip()
            raw["custom"][idx] = item
            self.write_raw(raw)
            return {
                "id": entry_id,
                "phase": str(item["phase"]).strip(),
                "category": str(item["category"]).strip(),
                "title": str(item["title"]).strip(),
                "prompt": str(item["prompt"]).strip(),
                "source": "user",
            }

        raise KeyError(entry_id)

    def delete(self, entry_id: str) -> None:
        raw = self.read_raw()
        shipped_ids = {item["id"] for item in self.defaults()}

        if entry_id in shipped_ids:
            if entry_id not in raw["hidden"]:
                raw["hidden"].append(entry_id)
            raw["overrides"].pop(entry_id, None)
            self.write_raw(raw)
            return

        before = len(raw["custom"])
        raw["custom"] = [
            item for item in raw["custom"]
            if not (isinstance(item, dict) and str(item.get("id")) == entry_id)
        ]
        if len(raw["custom"]) == before:
            raise KeyError(entry_id)
        self.write_raw(raw)

    def duplicate(self, entry_id: str) -> dict[str, str]:
        source_entry, _ = self._find_entry(entry_id)
        title = source_entry["title"]
        if not title.endswith(" (copy)"):
            title = f"{title} (copy)"
        payload = PromptEntryCreate(
            phase=source_entry["phase"],
            category=source_entry["category"],
            title=title,
            prompt=source_entry["prompt"],
        )
        return self.add(payload)

    def import_entries(self, entries: list[PromptEntryCreate]) -> list[dict[str, str]]:
        created: list[dict[str, str]] = []
        for item in entries:
            created.append(self.add(item))
        return created

    def reset(self) -> list[dict[str, str]]:
        path = self.path()
        if path.exists():
            path.unlink()
        return self.defaults()


def register_prompt_library_routes(
    app: FastAPI,
    *,
    workspace_name: Callable[[], str],
    store: PromptLibraryStore,
    llm_func: LlmFunc | None = None,
) -> None:
    """Register prompt library CRUD endpoints."""

    def _library_payload() -> dict[str, Any]:
        return {
            "workspace": workspace_name(),
            "prompts": store.read(),
            "defaults": store.defaults(),
            "customized": store.customized(),
        }

    @app.get("/api/ui/prompt-library", tags=["theseus-ui"])
    async def get_prompt_library() -> JSONResponse:
        """Return merged shipped + workspace prompt starters."""
        return JSONResponse(_library_payload())

    @app.post("/api/ui/prompt-library", tags=["theseus-ui"])
    async def create_prompt_library_entry(payload: PromptEntryCreate) -> JSONResponse:
        """Add a user-created starter for the active workspace."""
        try:
            entry = store.add(payload)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(500, f"Failed writing prompt library: {exc}") from exc
        return JSONResponse({"entry": entry, **_library_payload()})

    @app.put("/api/ui/prompt-library/{entry_id}", tags=["theseus-ui"])
    async def update_prompt_library_entry(
        entry_id: str,
        payload: PromptEntryUpdate,
    ) -> JSONResponse:
        """Update a shipped override or user-created starter."""
        try:
            entry = store.update(entry_id, payload)
        except KeyError as exc:
            raise HTTPException(404, f"Unknown prompt id: {entry_id}") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(500, f"Failed writing prompt library: {exc}") from exc
        return JSONResponse({"entry": entry, **_library_payload()})

    @app.delete("/api/ui/prompt-library/{entry_id}", tags=["theseus-ui"])
    async def delete_prompt_library_entry(entry_id: str) -> JSONResponse:
        """Hide a shipped starter or remove a user-created one."""
        try:
            store.delete(entry_id)
        except KeyError as exc:
            raise HTTPException(404, f"Unknown prompt id: {entry_id}") from exc
        except OSError as exc:
            raise HTTPException(500, f"Failed writing prompt library: {exc}") from exc
        return JSONResponse(_library_payload())

    @app.post("/api/ui/prompt-library/{entry_id}/duplicate", tags=["theseus-ui"])
    async def duplicate_prompt_library_entry(entry_id: str) -> JSONResponse:
        """Duplicate any starter into an editable user copy."""
        try:
            entry = store.duplicate(entry_id)
        except KeyError as exc:
            raise HTTPException(404, f"Unknown prompt id: {entry_id}") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(500, f"Failed writing prompt library: {exc}") from exc
        return JSONResponse({"entry": entry, **_library_payload()})

    @app.post("/api/ui/prompt-library/import", tags=["theseus-ui"])
    async def import_prompt_library(payload: PromptImportPayload) -> JSONResponse:
        """Import an array of starters as user entries."""
        try:
            created = store.import_entries(payload.prompts)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(500, f"Failed writing prompt library: {exc}") from exc
        return JSONResponse({"imported": created, **_library_payload()})

    @app.post("/api/ui/prompt-library/reset", tags=["theseus-ui"])
    async def reset_prompt_library() -> JSONResponse:
        """Restore shipped defaults for the active workspace."""
        try:
            store.reset()
        except OSError as exc:
            raise HTTPException(500, f"Failed resetting prompt library: {exc}") from exc
        return JSONResponse(_library_payload())

    @app.post("/api/ui/prompt-library/refine", tags=["theseus-ui"])
    async def refine_prompt_library_entry(payload: PromptRefinePayload) -> JSONResponse:
        """AI-assisted prompt refinement (clarity, shorter, citations, structure)."""
        action = payload.action.strip().lower()
        if action not in REFINE_ACTIONS:
            raise HTTPException(400, f"Unsupported refine action: {payload.action}")
        if llm_func is None:
            raise HTTPException(503, "LLM not available for prompt refinement")

        user_prompt = REFINE_USER_TEMPLATES[action].format(prompt=payload.prompt.strip())
        llm_prompt = f"{REFINE_SYSTEM}\n\n{user_prompt}"
        try:
            refined = await llm_func(llm_prompt)
        except Exception as exc:
            logger.exception("Prompt refine failed")
            raise HTTPException(500, f"Refine failed: {exc}") from exc

        text = refined.strip() if isinstance(refined, str) else str(refined).strip()
        if not text:
            raise HTTPException(500, "Refine returned empty text")
        return JSONResponse({"prompt": text, "action": action})


__all__ = [
    "PROMPT_LIBRARY",
    "PromptLibraryStore",
    "register_prompt_library_routes",
    "shipped_defaults",
    "shipped_prompt_id",
]