# Section-Aware Chunking - Quick Test Reference

**Quick Start**: 3-step validation in ~10-15 minutes for ANY federal RFP

---

## Prerequisites Checklist

- [ ] Current processing run completed
- [ ] Baseline analysis saved: `python analyze_chunks.py > baseline_token_based.txt`
- [ ] Knowledge graph backed up to `rag_storage_backups/`

---

## Quick Test (15 minutes)

### Step 1: Restart Server (2 min)

```powershell
# Stop current server (Ctrl+C), clear logs, restart
Clear-Content logs\lightrag.log
python app.py
```

**Verify**: Server starts at http://localhost:9621

---

### Step 2: Upload Small Test RFP (1 min)

**Requirements**: Any federal RFP with standard sections (A-M), 10-30 pages

Upload via WebUI → Monitor logs:

```powershell
Get-Content logs\lightrag.log -Tail 30 -Wait
```

---

### Step 3: Validate Section Detection (5-15 min)

**Watch for key log messages**:

✅ **SUCCESS** - Section-aware chunking active:

```
INFO: 🎯 RFP document detected - using enhanced section-aware chunking
INFO: 📝 Chunk 1/12: Section A - SOLICITATION/CONTRACT FORM (Page 1)
INFO: 📝 Chunk 3/12: Section C - STATEMENT OF WORK (subsection C.3.1, Page 5, 8 reqs)
INFO: 📊 Section distribution: Section A: 2 chunks, Section B: 1 chunks, Section C: 7 chunks...
```

❌ **FALLBACK** - Token-based chunking (section detection failed):

```
INFO: Using standard token-based chunking (no RFP structure detected)
INFO: Chunk 1 of 12 extracted 7 Ent + 5 Rel chunk-abc123...
```

---

### Step 4: Verify Results

```powershell
# Check for section detection
Select-String -Path logs\lightrag.log -Pattern "RFP document detected|Section [A-M]"

# Analyze processing
python analyze_chunks.py

# Check metadata
python -c "import json; print(list(json.load(open('rag_storage/kv_store_text_chunks.json')).values())[0])"
```

**Expected metadata** (if working):

```json
{
  "section": "Section A",
  "subsection": "A - SOLICITATION/CONTRACT FORM",
  "page_number": 1,
  "requirement_count": 0
}
```

---

## Troubleshooting

| Symptom                           | Cause                                | Fix                                   |
| --------------------------------- | ------------------------------------ | ------------------------------------- |
| No "RFP document detected"        | Document lacks clear section headers | Normal - fallback to token-based      |
| Section detection but no metadata | Metadata not stored properly         | Check `_CHUNK_METADATA_MAP` in code   |
| Server won't start                | Syntax error in chunking code        | Check `src/core/lightrag_chunking.py` |

---

## Test with ANY RFP

**What makes a good test document?**

✅ **Good**:

- Clear "SECTION X" or "PART X" headers
- Standard federal format (GSA, DoD, NASA)
- Multiple sections (A-M)
- 10-300 pages

❌ **Poor**:

- Non-standard headers ("Chapter", "Volume", etc.)
- Scanned images without OCR
- Non-federal contracts

**Examples of compatible formats**:

- GSA Schedule RFPs
- DoD SBIR/STTR solicitations
- NASA procurement RFPs
- Navy/Army/Air Force RFIs/RFPs
- DHS acquisition documents

---

## Section Detection Patterns

**What the code looks for** (works with ANY federal RFP):

```
Pattern 1: SECTION A - TITLE
Pattern 2: SECTION A: TITLE
Pattern 3: SECTION A -- TITLE
Pattern 4: SECTION A – TITLE (em dash)

Subsections:
- A.1, A.2, A.3
- A.1.1, A.1.2
- J-1, J-2, J-3 (attachments)

Requirements:
- "The Contractor shall..."
- "Must", "Will", "Should"
```

**If your RFP has different format**:

1. Test anyway - fallback to token-based works fine
2. Document format for future enhancement
3. Consider regex pattern adjustment (optional)

---

## Quick Commands

```powershell
# Restart & test
Clear-Content logs\lightrag.log; python app.py

# Monitor processing
Get-Content logs\lightrag.log -Tail 30 -Wait | Select-String "Section|RFP|Chunk"

# Check section detection worked
Select-String -Path logs\lightrag.log -Pattern "🎯|📝|📊"

# Analyze results
python analyze_chunks.py

# Compare baseline
diff baseline_token_based.txt <(python analyze_chunks.py)
```

---

## Success Indicators

✅ **Minimum Success**: Processing completes, entities extracted (with or without section detection)  
🎯 **Target Success**: Section detection works, metadata logged, same/better extraction quality  
🚀 **Optimal Success**: Section insights enable optimization, query performance improves

---

## Full Test Plan

For comprehensive testing (medium/large RFPs, section analysis, performance comparison):
→ See `SECTION_AWARE_CHUNKING_TEST_PLAN.md`

---

**Remember**: Section detection is **enhancement**, not **requirement**. Token-based fallback ensures processing always succeeds regardless of document format.
