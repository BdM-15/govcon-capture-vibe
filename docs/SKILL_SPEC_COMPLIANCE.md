# Skill Spec Compliance Audit

**Branch:** `120-skills-spec-compliance` · **Date:** 2026-04-27 · **Sub-phase:** 2.3 (✅ Done)

**Sub-phase status:**

| Sub-phase | Scope                                                           | State                                                          |
| --------- | --------------------------------------------------------------- | -------------------------------------------------------------- |
| 2.0       | Vendor skill-creator + this audit doc + Copilot instructions    | ✅ Done (9134f0f)                                              |
| 2.1       | Tool-calling runtime (`src/skills/{tools,runtime,llm_chat}.py`) | ✅ Done (b4b9e33)                                              |
| 2.2       | Migrate `proposal-generator` end-to-end                         | ✅ Done                                                        |
| 2.3       | Migrate remaining 4 skills + UI transcript drawer               | ✅ Done (98980a7, 2dc8e1a, 55d694b, d3cf024, 90610d7, fe716a4) |

This document audits every skill under `.github/skills/` against the open
[Agent Skills specification](https://agentskills.io/specification) and
Anthropic's
[best-practices guide](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices).
It is the authoritative gap list driving sub-phases 2.1 through 2.3.

---

## 1. Specification reference (the rules we audit against)

### 1.1 Frontmatter — six allowed fields only

| Field           | Required     | Constraints                                                                                 |
| --------------- | ------------ | ------------------------------------------------------------------------------------------- |
| `name`          | yes          | Max 64 chars, lowercase + hyphens, no XML, no reserved words (`anthropic`, `claude`)        |
| `description`   | yes          | Max 1024 chars, third-person, "pushy" (combats undertriggering), states **what** + **when** |
| `license`       | no           | SPDX identifier                                                                             |
| `compatibility` | no           | Max 500 chars, environment requirements                                                     |
| `metadata`      | no           | Free-form key/value — **the escape hatch for custom extensions**                            |
| `allowed-tools` | experimental | Space-separated tool names                                                                  |

**Anything else at the top level is non-conformant** and must move under
`metadata:`.

### 1.2 Directory layout

```
<skill-root>/
├── SKILL.md           # required — body <500 lines, workflow as Markdown checklist
├── scripts/           # executable code (agent EXECUTES via run_script, doesn't load)
├── references/        # loaded on demand into context (one level deep)
├── assets/            # templates, icons, fonts — files used in OUTPUT
├── evals/             # test prompts (evals.json)
└── LICENSE / LICENSE.txt
```

**Note:** spec uses `assets/` — we currently use `templates/` in two skills.

### 1.3 Progressive disclosure

Three tiers, smallest → largest:

1. **Metadata** (~100 tokens, always loaded for all skills) — frontmatter
2. **SKILL.md body** (<500 lines, loaded when skill activates)
3. **Bundled resources** (`references/`, `scripts/`, `assets/` — loaded only
   when needed)

### 1.4 Workflow patterns live in the BODY

The spec has **no** `workflow:` YAML field. Multi-step workflows are written
as Markdown checklists in the SKILL.md body, and the runtime gives the model
tools (`read_file`, `run_script`, `write_file`, plus domain tools) to execute
them. Example pattern from the best-practices doc:

```markdown
## PDF form filling workflow

Copy this checklist:

- [ ] Step 1: Run scripts/analyze_form.py input.pdf
- [ ] Step 2: Edit fields.json
- [ ] Step 3: Run scripts/validate_fields.py fields.json
```

### 1.5 Naming convention

- **Preferred:** gerund form (`processing-pdfs`, `analyzing-spreadsheets`)
- **Acceptable:** noun phrases (`pdf-processing`)
- **Avoid:** `helper`, `utils`, `tools`, `documents`

---

## 2. Current-state inventory

| Skill                                      | Body lines | Subdirs present                                  | Frontmatter extras                            | Spec-conformant?                                                                                                                               |
| ------------------------------------------ | ---------: | ------------------------------------------------ | --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `skill-creator` (vendored)                 |        ~30 | agents, assets, eval-viewer, references, scripts | none                                          | ✅ Yes                                                                                                                                         |
| `improve-codebase-architecture` (vendored) |        ~95 | references, evals                                | none (`metadata:` block)                      | ✅ Yes (2026-05-01, branch `156-developer-skills`)                                                                                             |
| `caveman` (vendored)                       |        ~35 | evals                                            | none (`metadata:` block)                      | ✅ Yes (2026-05-01, branch `156-developer-skills`)                                                                                             |
| `grill-me` (vendored)                      |        ~10 | evals                                            | none (`metadata:` block)                      | ✅ Yes (2026-05-01, branch `156-developer-skills`)                                                                                             |
| `to-prd` (vendored)                        |        ~70 | evals                                            | none (`metadata:` block)                      | ✅ Yes (2026-05-01, branch `156-developer-skills`)                                                                                             |
| `to-issues` (vendored)                     |        ~60 | evals                                            | none (`metadata:` block)                      | ✅ Yes (2026-05-01, branch `156-developer-skills`)                                                                                             |
| `tdd` (vendored)                           |        ~80 | references, evals                                | none (`metadata:` block)                      | ✅ Yes (2026-05-01, branch `156-developer-skills`)                                                                                             |
| `grill-me-govcon`                          |        ~75 | references (4), evals                            | none (`metadata:` block)                      | ✅ Yes (2026-05-01, branch `156-developer-skills`)                                                                                             |
| `grill-me-bid-strategy`                    |        ~65 | evals                                            | none (`metadata:` block)                      | ✅ Yes (2026-05-01, branch `156-developer-skills`)                                                                                             |
| `grill-me-capture`                         |        ~65 | evals                                            | none (`metadata:` block)                      | ✅ Yes (2026-05-01, branch `156-developer-skills`)                                                                                             |
| `grill-me-proposal`                        |        ~65 | evals                                            | none (`metadata:` block)                      | ✅ Yes (2026-05-01, branch `156-developer-skills`)                                                                                             |
| `grill-me-ptw`                             |        ~65 | evals                                            | none (`metadata:` block)                      | ✅ Yes (2026-05-01, branch `156-developer-skills`)                                                                                             |
| `competitive-intel`                        |         60 | references                                       | `category`, `version`, `status`               | ⚠️ Extras at top level                                                                                                                         |
| `compliance-auditor`                       |        116 | references                                       | `category`, `version`                         | ⚠️ Extras at top level                                                                                                                         |
| `govcon-ontology`                          |        166 | references                                       | `category`, `version`, `authoritative_source` | ⚠️ Extras at top level                                                                                                                         |
| `huashu-design-govcon`                     |  (removed) | n/a                                              | n/a                                           | ⚠️ Removed in 2.3 — superseded by vendored `huashu-design` (engine) + `proposal-generator` (govcon content + HTML render templates). See §3.5. |
| `proposal-generator`                       |        200 | references, **assets**, evals                    | none (`metadata:` block)                      | ✅ Yes (2.2)                                                                                                                                   |

**All bodies are under the 500-line limit.** ✅
**All descriptions are third-person and reasonably "pushy."** ✅
**Naming convention:** all use noun phrases (acceptable, not gerund).

---

## 3. Gaps and required changes (per skill)

### 3.1 `skill-creator` (vendored)

| Gap                                             | Action                                                  | Sub-phase  |
| ----------------------------------------------- | ------------------------------------------------------- | ---------- |
| None — fully spec-conformant                    | Verify `SkillManager.discover()` registers it cleanly   | 2.0        |
| Subagent assumption (Claude Code parallel runs) | Document Claude.ai-specific adaptation in `UPSTREAM.md` | 2.0 (done) |
| Script dependencies (chevron, etc.)             | Inventory + add to `pyproject.toml` if needed           | 2.1        |

### 3.2 `competitive-intel` (placeholder)

| Gap                                                                            | Action                                                                      | Sub-phase |
| ------------------------------------------------------------------------------ | --------------------------------------------------------------------------- | --------- |
| `category`, `version`, `status` at top level                                   | Move under `metadata:`                                                      | 2.3       |
| Description starts with "PLACEHOLDER (roadmap)" — may suppress trigger scoring | Keep "DO NOT USE" guard but lead with the trigger phrasing                  | 2.3       |
| No `evals/evals.json`                                                          | Add 3 test prompts (even for placeholder, to prove the contract)            | 2.3       |
| Body is pure prose (no checklist workflow)                                     | Acceptable for placeholder; add stub checklist + scripts/ when implementing | 2.3       |

### 3.3 `compliance-auditor`

| Gap                                                                              | Action                                                                                                     | Sub-phase |
| -------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | --------- |
| `category`, `version` at top level                                               | Move under `metadata:`                                                                                     | 2.3       |
| Body assumes briefing-book is pre-loaded — Option B requires explicit tool calls | Rewrite body as workflow checklist invoking `kg_query`, `kg_chunks`, `kg_entities`                         | 2.3       |
| No `evals/evals.json`                                                            | Add 3 test prompts (gap report, FAR coverage, requirement→deliverable mapping)                             | 2.3       |
| No `scripts/` despite being a deterministic-friendly skill                       | Add `scripts/coverage_matrix.py` (computes proposal_instruction↔evaluation_factor coverage from KG output) | 2.3       |

### 3.4 `govcon-ontology`

| Gap                                                        | Action                                                                                                                                     | Sub-phase |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | --------- |
| `category`, `version`, `authoritative_source` at top level | Move under `metadata:` (keeps the `authoritative_source` pointer to `src/ontology/schema.py`)                                              | 2.3       |
| Pure-reference skill — no scripts needed                   | Body checklist should be: 1) read_file references, 2) answer using only ontology vocabulary, 3) refuse if asked about non-Theseus concepts | 2.3       |
| No `evals/evals.json`                                      | Add 3 test prompts (entity type lookup, relationship semantics, vocabulary extension request)                                              | 2.3       |

### 3.5 `huashu-design-govcon` — REMOVED in sub-phase 2.3

Original plan was to migrate this hand-rolled overlay to spec compliance. During 2.3 the underlying assumption collapsed: the upstream [`alchaincyf/huashu-design`](https://github.com/alchaincyf/huashu-design) was vendored verbatim under its Personal Use License (see [`.github/skills/huashu-design/UPSTREAM.md`](../.github/skills/huashu-design/UPSTREAM.md)), and the overlay's actual govcon-specific value (KG-driven content + 4 HTML render templates + design tokens + anti-slop checklist) belongs alongside the content drafter, not as a third skill straddling content and presentation.

**Resolution:**

- Salvaged into `proposal-generator/`:
  - `references/anti_slop_checklist.md`
  - `references/critique_prompt.md`
  - `references/govcon_design_tokens.md`
  - `references/section_lm_visualization.md`
  - `assets/compliance_matrix.html`, `one_pager.html`, `slide_master.html`, `theme_card.html`
- Deleted (duplicates of vendored upstream): `scripts/html2pdf.sh`, `scripts/html2pptx.js`, `scripts/render_video.py`. The canonical renderers live in `huashu-design/scripts/{html2pptx.js, render-video.js, export_deck_*.mjs, convert-formats.sh}`.
- Deleted (obsolete): `references/upstream_attribution.md`, `SKILL.md`, the directory itself.
- `proposal-generator/SKILL.md` updated with: visual-handoff guidance pointing at `huashu-design`, new step 10 (anti-slop self-critique gate), reference list extended.
- `compliance-auditor/SKILL.md` updated with visual-handoff guidance.
- All `huashu-design-govcon` references scrubbed from `README.md`, `.github/skills/README.md`, `theseus-skills/README.md`, `docs/SKILLS.md`, `huashu-design/UPSTREAM.md`.

The "design domain" is now cleanly split: `huashu-design` (vendored, format-agnostic engine) + `proposal-generator` (govcon content + render templates). Either can be invoked independently.

### 3.6 `proposal-generator`

| Gap                                                      | Action                                                                                                                                                                                                          | Sub-phase | State |
| -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | ----- |
| `category`, `version` at top level                       | Moved under `metadata:` (now `metadata.runtime: tools`, `metadata.category`, `metadata.version: 0.3.0`, `metadata.status`)                                                                                      | 2.2       | ✅    |
| **`templates/` directory name**                          | Renamed to `assets/` via `git mv`; all in-body links updated                                                                                                                                                    | 2.2       | ✅    |
| Body has Workflow section but no executable script chain | Body rewritten as a 10-step numbered checklist that invokes `kg_entities`, `kg_query`, `kg_chunks`, `read_file`, `write_file`. No bundled scripts needed for v0.3 — entire flow runs through the runtime tools. | 2.2       | ✅    |
| No `evals/evals.json`                                    | Added 3 evals: compliance matrix, win themes, executive summary. Each carries verifiable expectations on tool-call patterns + artifact contents.                                                                | 2.2       | ✅    |
| Implicit briefing-book dependency                        | Removed — runtime no longer pre-builds briefing book for tools-mode skills (route layer skips it). Skill fetches what it needs via `kg_entities` + `kg_chunks`.                                                 | 2.2       | ✅    |
| Output persistence                                       | Final draft saved to `<run_dir>/artifacts/proposal_draft.json` via `write_file`; cover note (counts + warnings + chunk_ids) returned as the assistant message.                                                  | 2.2       | ✅    |

---

## 4. Cross-cutting issues

### 4.1 Mojibake in existing SKILL.md files

Several existing skills contain `â€"`, `â†'`, `â†”`, `â€"` — UTF-8 round-tripped
through Windows-1252. Symptoms visible in `competitive-intel`,
`compliance-auditor`, `proposal-generator`,
`govcon-ontology`. **Repair during the 2.2/2.3 rewrites** so we don't
introduce a separate "fix encoding" commit. PowerShell rule per
`.github/copilot-instructions.md`: always `Out-File -Encoding utf8`.

### 4.2 `templates/` → `assets/` rename

Affects `proposal-generator` (and originally `huashu-design-govcon`, since
removed). Also requires
updating `src/skills/manager.py` lines that probe for the `templates`
subdirectory:

- `Skill.has_templates` field
- `_load_skill()` `(folder / "templates").is_dir()`
- `get_skill_detail()` `_list_subdir(Path(skill.path) / "templates", ...)`

Add `has_assets` field and probe for `assets/` instead. **Backward compat:**
keep `has_templates` as a deprecated alias for one release.

### 4.3 `evals/` directory missing everywhere except `skill-creator`

Spec doesn't strictly require `evals/`, but skill-creator's whole iteration
loop depends on it. Add `evals/evals.json` to every skill in 2.2/2.3.
Schema (from `skill-creator/references/schemas.md`):

```json
{
  "version": "1.0",
  "tests": [
    {
      "id": "test-1",
      "prompt": "...",
      "expected_signals": ["..."],
      "rubric": "..."
    }
  ]
}
```

---

## 5. Runtime capabilities

`SkillManager.invoke()` supports both the legacy single-shot path and the
tools-mode runtime declared by `metadata.runtime: tools`. Tools-mode skills run
through `src/skills/runtime.py` with a persisted `transcript.json`, bounded tool
calls, and Studio-visible artifacts under `<run_dir>/artifacts/`.

| Capability                           | Current state                                                                                                 |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| Tool-calling loop                    | xAI Grok function-calling, multi-turn until the model emits no tool calls                                     |
| `read_file` tool                     | Reads files under `<skill_root>/{references,assets,scripts}/` (read-only)                                     |
| `run_script` tool                    | Subprocess sandbox: timeout, cwd locked to skill dir, captures stdout/stderr                                  |
| Default renderer roots               | Every tools-mode skill can call `renderers/scripts` and `huashu-design/scripts` without wrapper code          |
| `write_file` tool                    | Writes confined to `<run_dir>/artifacts/` with optional Studio display labels                                 |
| `kg_query(cypher)` tool              | Calls Neo4j directly via existing client                                                                      |
| `kg_entities(types[], limit)` tool   | Typed slicing via the current workspace KG                                                                    |
| `kg_chunks(query, top_k, mode)` tool | Chat-grade hybrid retrieval via the Phase 1.6 retrieval path                                                  |
| `invoke_skill(name, prompt)` tool    | Tier A synchronous child skill invocation, depth=1, same workspace, child run/artifacts returned              |
| Tool-call transcript                 | `transcript.json` in `<run_dir>/` capturing every call, args, result, timing                                  |
| Per-script outputs                   | `tool_outputs/<NN>_<tool>_<descriptor>.{stdout,stderr}.txt`                                                   |
| Generic product emission             | Enabled by default unless `metadata.auto_emit_artifacts: false`; emits a Studio-visible final HTML product plus source `report.md/json`; DOCX requires `metadata.auto_emit_formats` opt-in; XLSX also requires `metadata.auto_emit_xlsx_source` |

The existing Phase 1.6 hybrid retrieval pipeline is **fully reused** — it
is the implementation of `kg_chunks(...)`. Studio indexes artifacts, not
`response.md`, so generic product emission guarantees even chat-only skills
produce a Studio-visible final HTML product. Source `report.md/json` remains on
disk for reasoning/editing workflows but is filtered out of Studio. Office renders
are opt-in, and XLSX auto-emission requires a table JSON source so skills do not
publish faux workbook products by default.

---

## 6. skill-creator runtime adaptation

`skill-creator/SKILL.md` describes its workflow assuming **Claude Code**
(parallel subagents). Theseus is single-process, so we follow the
**"Claude.ai-specific instructions"** path:

| Upstream behavior                                                            | Theseus adaptation                                                    |
| ---------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| Spawn parallel `with-skill` + `baseline` subagents                           | Sequential runs in the same process                                   |
| Browser-based eval viewer                                                    | Use `eval-viewer/generate_review.py --static` to emit standalone HTML |
| Aggregate via `python -m scripts.aggregate_benchmark` (assumes specific cwd) | Wrap in a Theseus CLI entry point that sets cwd correctly             |
| `python -m scripts.run_loop` for description optimization                    | Document as an opt-in tool, not auto-run                              |

These adaptations are notes, not code changes for 2.0 — they inform sub-phase
2.4 if/when we wire skill-creator's eval loop into Theseus directly.

---

## 7. Sub-phase rollout plan (final)

| Sub-phase | Scope                                                        | Skills touched                                                                                                                                                                | Commit                                                                                                                                                                 |
| --------- | ------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **2.0**   | Vendor skill-creator + this audit doc                        | skill-creator only                                                                                                                                                            | This commit                                                                                                                                                            |
| **2.1**   | Tool-calling runtime in `src/skills/manager.py`              | None — runtime only                                                                                                                                                           | Separate commit                                                                                                                                                        |
| **2.2**   | Migrate `proposal-generator` end-to-end (proves the pattern) | proposal-generator                                                                                                                                                            | Separate commit                                                                                                                                                        |
| **2.3**   | Migrate remaining 4 skills + UI transcript drawer            | competitive-intel, compliance-auditor, govcon-ontology; **`huashu-design-govcon` removed** — superseded by vendored `huashu-design` + `proposal-generator` salvage (see §3.5) | ✅ 98980a7 (compliance-auditor), 2dc8e1a (competitive-intel), 55d694b (govcon-ontology), d3cf024 (vendor huashu-design), 90610d7 (remove overlay), fe716a4 (UI drawer) |

Each sub-phase commit MUST be approved by the user before being created
(per the MANDATORY rule in `.github/copilot-instructions.md`).
