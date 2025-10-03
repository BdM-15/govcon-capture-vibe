# Next Conversation Starter - Quick Reference

**Use this prompt to start your next conversation with complete context:**

---

## 🎯 **Conversation Starter Prompt**

```
I need to implement Path B for ontology-guided LightRAG integration. Here's the complete context:

**⚠️ ABSOLUTE REQUIREMENT - Virtual Environment Activation**:
- EVERY terminal command using Python/uv/dependencies MUST start with: .venv\Scripts\Activate.ps1; <command>
- NO EXCEPTIONS - The agent's run_in_terminal does NOT auto-activate venv
- Example: .venv\Scripts\Activate.ps1; uv pip list
- See copilot-instructions.md "CRITICAL: Virtual Environment Activation" section for full details

**Current Status**:
- Using lightrag-hku==1.4.9 (installed via uv in .venv/Lib/site-packages/lightrag/)
- Path A (custom chunking with regex) has been ARCHIVED - it created fictitious entities like "RFP Section J-L" that don't exist in Uniform Contract Format
- All documentation is complete (PATH_B_IMPLEMENTATION_PLAN.md, copilot-instructions.md, README.md updated)
- Branch: 002-lighRAG-govcon-ontology
- Ready to start Phase 1: Codebase cleanup

**Path B Approach (CORRECT)**:
- MODIFY LightRAG's extraction engine by injecting government contracting ontology into addon_params["entity_types"]
- TEACH LightRAG domain concepts it would never extract using generic entity types
- Replace generic types with domain types (CLIN, FAR_CLAUSE, EVALUATION_FACTOR, REQUIREMENT)
- Add government contracting examples to teach Section L↔M relationships
- Constrain relationships to valid patterns (SOW→Deliverable, not random)
- Post-process to ensure extractions match ontology

**Critical Understanding**:
- Generic LightRAG CANNOT understand government contracting without ontology injection
- "RFP Section J-L" DOES NOT EXIST in Uniform Contract Format
- All Sections are INDIVIDUAL sections, not merged
- Path A's regex preprocessing created these fictitious entities and corrupted the knowledge graph
- We actively MODIFY LightRAG's prompts and entity types, not just use it "as-is"

**Key Files**:
- Implementation plan: docs/PATH_B_IMPLEMENTATION_PLAN.md
- Framework guidelines: .github/copilot-instructions.md
- Fresh conversation context: docs/FRESH_CONVERSATION_STARTER.md
- LightRAG source reference: .venv/Lib/site-packages/lightrag/
  - prompt.py (PROMPTS dictionary)
  - operate.py (extraction pipeline, lines 2020-2170)
  - lightrag.py (addon_params field, line 362)

**Immediate Next Steps** (Phase 1 - ~30 minutes):
1. Create archive/path_a_exploratory_work/ directory
2. Move src/core/chunking.py to archive (ShipleyRFPChunker with regex)
3. Move test_phase1_optimizations.py to archive
4. Keep src/core/ontology.py (will integrate with Path B)
5. Simplify src/core/lightrag_chunking.py (remove complex regex)
6. Commit: "chore: Archive Path A exploratory work"

Let's start with Phase 1 to clean up the codebase and archive Path A artifacts.
```

---

## 📚 **Essential Documents**

**Read these first** (in order):

1. **`docs/FRESH_CONVERSATION_STARTER.md`** - Complete context and implementation plan
2. **`docs/PATH_B_IMPLEMENTATION_PLAN.md`** - Detailed 5-phase implementation guide
3. **`.github/copilot-instructions.md`** - Framework boundaries and integration guidelines

**Reference as needed**:

- **`README.md`** - System architecture and LightRAG framework integration
- **`docs/RAG_STORAGE_ANALYSIS.md`** - Why Path A failed (fictitious entities)
- **`.venv/Lib/site-packages/lightrag/`** - LightRAG source code reference

---

## ⚡ **Quick Commands**

```powershell
# ⚠️ CRITICAL: ALL Python/uv commands MUST activate venv first!

# Verify environment (WITH VENV ACTIVATION)
.venv\Scripts\Activate.ps1; uv pip list | Select-String -Pattern "lightrag"
# Expected: lightrag-hku                             1.4.9

# Verify branch (git doesn't need venv)
git branch --show-current
# Expected: 002-lighRAG-govcon-ontology

# Open key documents (doesn't need venv)
code docs/FRESH_CONVERSATION_STARTER.md
code docs/PATH_B_IMPLEMENTATION_PLAN.md
code .github/copilot-instructions.md

# Start Phase 1 (file operations don't need venv)
New-Item -ItemType Directory -Path "archive/path_a_exploratory_work"
Move-Item "src/core/chunking.py" "archive/path_a_exploratory_work/"
Move-Item "test_phase1_optimizations.py" "archive/path_a_exploratory_work/"
```

---

## 🎯 **Success Criteria**

**Phase 1-3 Complete** (Target: 3.5 hours):

- ✅ Path A artifacts archived
- ✅ Ontology integrated with LightRAG prompts
- ✅ Test RFP processed with new approach
- ✅ Zero "RFP Section J-L" entities
- ✅ Individual J, K, L sections properly recognized

**Phase 4-5 Complete** (Target: 6 hours total):

- ✅ Simple chunking strategy implemented
- ✅ Full RFP processing <60 minutes
- ✅ <25 entities per chunk average
- ✅ Knowledge graph contains only valid Uniform Contract Format sections
- ✅ Semantic search returns correct results

---

**Last Updated**: October 2025  
**Status**: Documentation complete, ready to start fresh conversation  
**Estimated Time to Phase 5**: 6 hours total (1.5 days at 4 hours/day)
