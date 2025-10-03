# Section-Aware Chunking Test Plan (RFP-Agnostic)

**Version**: 1.0  
**Date**: October 2, 2025  
**Purpose**: Validate section-aware chunking functionality across any federal RFP document  
**Prerequisites**: Current processing run complete, baseline analysis captured

---

## Overview

This test plan validates that the fixed `rfp_aware_chunking_func` correctly identifies RFP sections across any federal RFP document structure, logs section metadata during processing, and improves knowledge graph quality through section-aware boundaries.

### Key Success Metrics

- ✅ Section detection works for standard federal RFP formats (A-M sections, J attachments)
- ✅ Section metadata logged and tracked throughout processing
- ✅ Chunk boundaries respect section boundaries where possible
- ✅ Knowledge graph maintains or improves entity/relation quality
- ✅ Section-specific performance insights available

---

## Test Environment Setup

### 1. Verify Fixed Code is Ready

```powershell
# Check that lightrag_chunking.py has correct signature
Select-String -Path "src\core\lightrag_chunking.py" -Pattern "def rfp_aware_chunking_func"
# Should show: def rfp_aware_chunking_func(tokenizer, content: str, split_by_character, ...)
```

**Expected**: 6-parameter signature matching LightRAG requirements

### 2. Prepare Test RFP Documents

#### Option A: Small Test Document (Quick Validation - 5-10 min)

Use a **minimal federal RFP** with standard sections:

- **Sections**: At least A (Forms), B (CLINs), C (SOW/PWS), I (Clauses)
- **Pages**: 10-30 pages
- **Purpose**: Rapid validation of section detection logic
- **Location**: `inputs/test_small_rfp.pdf`

**Characteristics to look for**:

- Clear section headers (e.g., "SECTION A - SOLICITATION/CONTRACT FORM")
- Standard federal format
- Representative content (not just forms)

#### Option B: Medium Test Document (Comprehensive - 30-60 min)

Use a **full federal RFP** with complex structure:

- **Sections**: A-M sections, J attachments, subsections
- **Pages**: 50-150 pages
- **Purpose**: Validate handling of complex section hierarchies
- **Location**: `inputs/test_medium_rfp.pdf`

**Characteristics to look for**:

- Multiple J attachments
- Deep subsection nesting
- Requirements tables
- Technical appendices

#### Option C: Navy MBOS RFP (Baseline Comparison - 2-4 hours)

Reprocess the **current document** to compare:

- **Document**: `inputs/__enqueued__/_N6945025R0003.pdf`
- **Purpose**: Direct comparison with token-based baseline
- **Benefit**: Quantifiable improvement metrics

### 3. Backup Current State

```powershell
# Create timestamped backup of token-based processing
$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
New-Item -Path "rag_storage_backups\token_based_$timestamp" -ItemType Directory -Force
Copy-Item -Path "rag_storage\*" -Destination "rag_storage_backups\token_based_$timestamp\" -Recurse

# Save baseline analysis
python analyze_chunks.py > "analysis_outputs\baseline_token_based_$timestamp.txt"
```

---

## Test Execution Sequence

### **Test 1: Server Restart with Fixed Code** ⏱️ ~2 min

**Objective**: Activate corrected `rfp_aware_chunking_func` signature

**Steps**:

1. Stop current server (if running):

   ```powershell
   # In terminal running app.py, press Ctrl+C
   ```

2. Clear old logs:

   ```powershell
   Clear-Content logs\lightrag.log
   Clear-Content logs\govcon_server.log
   Clear-Content logs\errors.log
   ```

3. Start server with fixed code:

   ```powershell
   python app.py
   ```

4. Verify startup:
   ```powershell
   # Check logs for successful initialization
   Get-Content logs\govcon_server.log -Tail 10
   ```

**Expected Output**:

```
INFO: Uvicorn running on http://localhost:9621
INFO: Application startup complete
```

**Success Criteria**:

- ✅ Server starts without errors
- ✅ WebUI accessible at http://localhost:9621
- ✅ No import errors related to chunking function

**Troubleshooting**:

- ❌ Import error → Check `src/core/lightrag_chunking.py` syntax
- ❌ Signature error → Verify 6-parameter signature matches LightRAG requirements
- ❌ Port in use → Kill existing process on port 9621

---

### **Test 2: Small Document Validation** ⏱️ ~5-15 min

**Objective**: Verify section detection and logging with minimal processing time

**Steps**:

1. Prepare test document in `inputs/` (not `inputs/__enqueued__/`)

2. Upload via WebUI:

   - Navigate to http://localhost:9621
   - Click "Upload Document"
   - Select small test RFP
   - Monitor processing start

3. **Monitor logs in real-time**:

   ```powershell
   # Terminal 1: Watch lightrag.log
   Get-Content logs\lightrag.log -Tail 30 -Wait

   # Terminal 2: Filter for section-specific logs
   Get-Content logs\lightrag.log -Wait | Select-String "RFP document|Section|📝|📊"
   ```

4. Check for section detection markers:
   ```powershell
   # After processing starts, search logs
   Select-String -Path logs\lightrag.log -Pattern "RFP document detected|Section [A-M]|subsection"
   ```

**Expected Log Output** (Section-Aware Detection):

```
INFO: 🎯 RFP document detected - using enhanced section-aware chunking
INFO: 📄 Document structure: 4 sections detected (A, B, C, I)
INFO: 📝 Chunk 1/12: Section A - SOLICITATION/CONTRACT FORM (Page 1, 0 reqs)
INFO: 📝 Chunk 2/12: Section B - CLINs (subsection B.1, Page 3, 2 reqs)
INFO: 📝 Chunk 5/12: Section C - STATEMENT OF WORK (subsection C.3.1, Page 8, 8 reqs)
INFO: 📊 Section distribution: Section A: 1 chunks, Section B: 2 chunks, Section C: 7 chunks, Section I: 2 chunks
```

**Expected Log Output** (If Section Detection FAILS - Fallback to Token-Based):

```
INFO: Using standard token-based chunking (no RFP structure detected)
INFO: Chunk 1 of 12 extracted 7 Ent + 5 Rel chunk-abc123...
```

**Success Criteria**:

- ✅ Log contains "🎯 RFP document detected" message
- ✅ Log shows section-specific chunk messages with section identifiers
- ✅ Log includes section distribution summary
- ✅ Processing completes successfully
- ✅ Entities and relations extracted (check with `analyze_chunks.py`)

**Validation**:

```powershell
# After processing completes
python analyze_chunks.py

# Check chunk metadata for section information
python -c "import json; data = json.load(open('rag_storage/kv_store_text_chunks.json')); print(list(data.values())[0])"
```

**Expected Metadata** (if section-aware working):

```json
{
  "content": "SECTION A - SOLICITATION/CONTRACT FORM...",
  "chunk_order_index": 0,
  "full_doc_id": "...",
  "section": "Section A",
  "subsection": "A - SOLICITATION/CONTRACT FORM",
  "page_number": 1,
  "requirement_count": 0
}
```

**If Section Detection Fails**:

1. Check document format: Does it have clear "SECTION X" headers?
2. Verify regex patterns in `lightrag_chunking.py`:
   ```python
   section_pattern = r'SECTION\s+([A-M])\s*[-–—]\s*(.+?)(?:\n|$)'
   ```
3. Test with known federal RFP format (e.g., GSA Schedule, DoD IDIQ)

---

### **Test 3: Full RFP Reprocessing** ⏱️ ~2-4 hours

**Objective**: Process complete RFP with section-aware chunking for baseline comparison

**Steps**:

1. Clear previous processing:

   ```powershell
   # Backup current state first (if not done)
   Remove-Item -Path rag_storage\* -Recurse -Force
   ```

2. Upload full RFP:

   - Use Navy MBOS RFP or equivalent large federal RFP
   - Upload via WebUI
   - Monitor processing

3. **Continuous monitoring** (recommended for long runs):

   ```powershell
   # Create monitoring script: monitor_processing.ps1
   while ($true) {
       $latest = Get-Content logs\lightrag.log -Tail 5
       $chunkInfo = $latest | Select-String "Chunk \d+ of \d+"
       if ($chunkInfo) {
           Clear-Host
           Write-Host "=== Processing Status ===" -ForegroundColor Cyan
           Write-Host $chunkInfo[-1] -ForegroundColor Green
           Write-Host "`nLast 5 log lines:"
           $latest | ForEach-Object { Write-Host $_ }
       }
       Start-Sleep -Seconds 30
   }
   ```

4. **Analyze section performance**:

   ```powershell
   # After processing completes
   python analyze_chunks.py > analysis_outputs\section_aware_full_run.txt

   # Extract section-specific stats
   Select-String -Path logs\lightrag.log -Pattern "Section [A-M]" | Group-Object | Select-Object Count, Name
   ```

**Success Criteria**:

- ✅ All chunks processed successfully
- ✅ Section metadata present in logs throughout processing
- ✅ No increase in timeout or error rates vs baseline
- ✅ Entity/relation extraction quality maintained or improved
- ✅ Section distribution matches expected RFP structure

**Performance Comparison**:

```powershell
# Compare with baseline
diff (Get-Content analysis_outputs\baseline_token_based_*.txt) (Get-Content analysis_outputs\section_aware_full_run.txt)
```

**Key Metrics to Compare**:

- Total entities extracted
- Total relations extracted
- Average entities per chunk
- Average relations per chunk
- Processing time per chunk
- Warning/error rates
- Section coverage (new metric)

---

### **Test 4: Section-Specific Analysis** ⏱️ ~10 min

**Objective**: Analyze processing performance by section type

**Steps**:

1. **Extract section performance data**:

   ```powershell
   # Create analysis script: analyze_sections.py
   python -c "
   import json
   import re
   from pathlib import Path
   from collections import defaultdict

   # Load logs
   log_file = Path('logs/lightrag.log')
   if not log_file.exists():
       print('No log file found')
       exit(1)

   logs = log_file.read_text(encoding='utf-8')

   # Parse section information from logs
   section_pattern = r'Chunk (\d+) of \d+.*?Section ([A-M])'
   chunk_time_pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?Chunk (\d+) of \d+ extracted (\d+) Ent \+ (\d+) Rel'

   section_data = defaultdict(lambda: {'chunks': [], 'entities': 0, 'relations': 0})

   for match in re.finditer(chunk_time_pattern, logs):
       timestamp, chunk_num, ent, rel = match.groups()
       # Find section for this chunk
       section_match = re.search(f'Chunk {chunk_num} of.*?Section ([A-M])', logs)
       if section_match:
           section = section_match.group(1)
           section_data[section]['chunks'].append(int(chunk_num))
           section_data[section]['entities'] += int(ent)
           section_data[section]['relations'] += int(rel)

   # Print analysis
   print('\\n=== Section Performance Analysis ===\\n')
   for section in sorted(section_data.keys()):
       data = section_data[section]
       chunk_count = len(data['chunks'])
       print(f'Section {section}:')
       print(f'  Chunks: {chunk_count}')
       print(f'  Entities: {data[\"entities\"]} (avg: {data[\"entities\"]/chunk_count:.1f}/chunk)')
       print(f'  Relations: {data[\"relations\"]} (avg: {data[\"relations\"]/chunk_count:.1f}/chunk)')
       print()
   "
   ```

2. **Identify high-density sections**:

   ```powershell
   # Sections with most entities/relations (likely Section C, M)
   # Sections with most warnings (likely Section I for FAR clauses)
   ```

3. **Document section characteristics**:
   - Which sections take longest to process?
   - Which sections generate most warnings?
   - Which sections have highest entity density?
   - Which sections need specialized handling?

**Expected Insights**:

- **Section A (Forms)**: Low entity count, fast processing
- **Section B (CLINs)**: Moderate entities, numerical data
- **Section C (SOW/PWS)**: High entity density, technical requirements
- **Section I (Clauses)**: FAR clause format challenges, warnings expected
- **Section J (Attachments)**: Variable, depends on content
- **Section M (Evaluation)**: High importance, moderate complexity

**Use Case**: Future optimization targets

- Adjust chunk sizes per section type
- Customize prompts for section-specific content
- Set section-specific timeouts

---

## Comparison Analysis Framework

### Quantitative Metrics

| Metric              | Token-Based Baseline | Section-Aware | Improvement |
| ------------------- | -------------------- | ------------- | ----------- |
| **Processing**      |                      |               |             |
| Total chunks        | [baseline]           | [section]     | +/- %       |
| Avg time/chunk      | [baseline]           | [section]     | +/- %       |
| Timeout events      | [baseline]           | [section]     | +/- count   |
| **Extraction**      |                      |               |             |
| Total entities      | [baseline]           | [section]     | +/- %       |
| Total relations     | [baseline]           | [section]     | +/- %       |
| Avg entities/chunk  | [baseline]           | [section]     | +/- %       |
| Avg relations/chunk | [baseline]           | [section]     | +/- %       |
| **Quality**         |                      |               |             |
| Warning rate        | [baseline]           | [section]     | +/- %       |
| Format errors       | [baseline]           | [section]     | +/- count   |
| Section coverage    | N/A                  | [section]     | NEW         |

### Qualitative Assessment

**Section Boundary Preservation**:

- [ ] Technical requirements kept within Section C chunks
- [ ] Contract clauses not split across chunks
- [ ] J attachment content isolated properly

**Knowledge Graph Quality**:

- [ ] Cross-section relationships captured (e.g., C → M evaluation criteria)
- [ ] Section context preserved in entity descriptions
- [ ] Section-specific entity types recognized

**Query Performance** (Manual Testing):

```bash
# Test queries that benefit from section awareness
Query 1: "What are the technical requirements in Section C?"
Query 2: "List all contract clauses from Section I"
Query 3: "What are the evaluation criteria in Section M?"
Query 4: "Find J attachments related to cybersecurity"
```

**Expected Improvement**: Section-aware chunking should improve relevance and reduce noise in section-specific queries.

---

## Success Criteria Summary

### ✅ **Minimum Success (Must Have)**

- [ ] Section detection logs appear for any federal RFP
- [ ] Processing completes without new errors
- [ ] Entity/relation extraction matches or exceeds baseline
- [ ] Chunk metadata includes section information

### 🎯 **Target Success (Should Have)**

- [ ] Section distribution summary logged
- [ ] Section-specific performance insights available
- [ ] Warnings do not increase vs baseline
- [ ] Processing time comparable or improved

### 🚀 **Optimal Success (Nice to Have)**

- [ ] Section boundary preservation demonstrable
- [ ] Query performance improvement measurable
- [ ] Section-specific optimization opportunities identified
- [ ] Reusable patterns for future RFP processing

---

## Troubleshooting Guide

### Issue: No Section Detection Logs

**Symptoms**: Logs show standard token-based chunking, no "RFP document detected" message

**Diagnosis**:

1. Check document format:

   ```powershell
   # Extract text from PDF to verify structure
   # Look for clear "SECTION X" headers
   ```

2. Verify regex patterns:

   ```python
   # In src/core/lightrag_chunking.py
   section_pattern = r'SECTION\s+([A-M])\s*[-–—]\s*(.+?)(?:\n|$)'
   # Test against sample section headers
   ```

3. Check function is being called:
   ```powershell
   # Add debug logging to verify function invocation
   Select-String -Path logs\lightrag.log -Pattern "rfp_aware_chunking_func"
   ```

**Resolution**:

- **Option A**: Adjust regex for document-specific header format
- **Option B**: Use fallback token-based chunking (baseline behavior)
- **Option C**: Pre-process PDF to normalize section headers

### Issue: Section Detection Works But No Metadata in Chunks

**Symptoms**: Logs show section detection but chunk metadata lacks section fields

**Diagnosis**:

1. Check metadata storage:

   ```python
   import json
   chunks = json.load(open('rag_storage/kv_store_text_chunks.json'))
   print(chunks[list(chunks.keys())[0]])
   ```

2. Verify global metadata map:
   ```python
   # In lightrag_chunking.py
   from src.core.lightrag_chunking import get_all_chunk_metadata
   print(get_all_chunk_metadata())
   ```

**Resolution**:

- Ensure `_CHUNK_METADATA_MAP` is populated during chunking
- Verify metadata is attached to chunk objects before return
- Check LightRAG's chunk storage process

### Issue: Increased Processing Time

**Symptoms**: Section-aware processing significantly slower than baseline

**Diagnosis**:

1. Compare chunk sizes:

   ```powershell
   # Section-aware may create different chunk boundaries
   # Check if chunks are smaller (more chunks = more processing)
   ```

2. Check section detection overhead:
   ```python
   # Time the regex matching operations
   # If pattern matching is slow, optimize regex
   ```

**Resolution**:

- Optimize regex patterns (use compiled patterns)
- Consider caching section detection results
- Profile chunking function for bottlenecks

### Issue: Section Detection False Positives

**Symptoms**: Non-section content incorrectly classified as sections

**Diagnosis**:

1. Review false positive examples in logs
2. Identify patterns causing misclassification

**Resolution**:

- Tighten regex patterns (e.g., require line start `^`)
- Add content validation (section headers typically short)
- Implement confidence scoring

---

## Post-Test Documentation

### Required Outputs

1. **Test Results Summary** (`test_results_section_aware_YYYYMMDD.md`):

   - Test execution date/time
   - Documents tested (name, size, sections)
   - Success criteria checklist
   - Performance metrics comparison
   - Issues encountered and resolutions
   - Recommendations for production use

2. **Section Performance Report** (`section_performance_analysis.txt`):

   - Output from Test 4 analysis
   - Section-by-section breakdown
   - Optimization recommendations
   - High-value sections identified

3. **Knowledge Graph Comparison** (if applicable):
   - Entity type distribution (token vs section)
   - Relation type distribution
   - Cross-section relationship analysis
   - Query performance comparison

### Integration into Development Workflow

**Update Documentation**:

- [ ] Update `README.md` with section-aware capabilities
- [ ] Document section detection patterns in `docs/ARCHITECTURE.md`
- [ ] Add section-specific configuration examples to `.env.example`

**Code Improvements**:

- [ ] Add section-specific chunk size configuration
- [ ] Implement section-specific timeout settings
- [ ] Create section-aware prompt templates
- [ ] Build section performance monitoring dashboard

**Future Enhancements** (add to roadmap):

- [ ] ML-based section classification (beyond regex)
- [ ] Section importance weighting in embeddings
- [ ] Section-specific entity extraction strategies
- [ ] Automated section structure learning

---

## Appendix: Test Document Recommendations

### Publicly Available Test RFPs

1. **GSA Schedules** (Simple structure, 20-50 pages)

   - Clear section delineation
   - Standard federal format
   - Good for initial validation

2. **DoD SBIR/STTR Solicitations** (Moderate complexity, 50-100 pages)

   - Multiple J attachments
   - Technical sections
   - Evaluation criteria

3. **NASA Procurement RFPs** (Complex, 100-300 pages)
   - Deep section nesting
   - Technical specifications
   - Multiple amendments

### Document Selection Criteria

**Good Test Documents**:

- ✅ Clear "SECTION X" headers
- ✅ Standard federal format (SF-30, SF-33, etc.)
- ✅ Representative content (not just forms)
- ✅ Multiple sections (A-M coverage)
- ✅ J attachments present

**Avoid for Testing**:

- ❌ Non-standard header formats
- ❌ Heavily redacted documents
- ❌ Scanned images without OCR
- ❌ Foreign government contracts
- ❌ Pre-1990s formats (outdated structure)

---

## Quick Reference Commands

```powershell
# Restart server
Ctrl+C; python app.py

# Monitor processing
Get-Content logs\lightrag.log -Tail 30 -Wait

# Check section detection
Select-String -Path logs\lightrag.log -Pattern "RFP document|Section"

# Analyze completed run
python analyze_chunks.py

# Backup knowledge graph
$ts = Get-Date -Format 'yyyyMMdd_HHmmss'; Copy-Item rag_storage\* -Destination "rag_storage_backups\section_aware_$ts\" -Recurse

# Compare results
diff analysis_outputs\baseline_*.txt analysis_outputs\section_aware_*.txt
```

---

**Test Plan Owner**: Development Team  
**Review Frequency**: After each major RFP processing run  
**Success Target**: 90%+ section detection accuracy across federal RFP formats
