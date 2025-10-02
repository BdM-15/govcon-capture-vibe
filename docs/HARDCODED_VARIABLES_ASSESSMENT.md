# Hardcoded Variables Assessment - Configuration Centralization

**Date**: October 2, 2025  
**Status**: Assessment Only - No Changes Made  
**Purpose**: Identify hardcoded values that should be moved to `.env` for easier management

---

## 🎯 Executive Summary

**Current State:**

- ✅ Most critical values are already in `.env` (timeouts, chunk sizes, LLM config)
- ⚠️ Several hardcoded values found that would benefit from centralization
- 📊 Total identified: **15 categories** of hardcoded values

**Recommendation Priority:**

1. **HIGH** - Values that affect processing behavior (chunk limits, thresholds)
2. **MEDIUM** - Values that affect performance (batch sizes, retry limits)
3. **LOW** - Values that rarely change (logging defaults, page estimation)

---

## 📋 Detailed Findings

### **Category 1: Chunk Processing Limits** ⚠️ HIGH PRIORITY

#### **File:** `src/core/lightrag_chunking.py`

**Current Hardcoded Values:**

```python
# Line 165
MAX_CHUNK_LENGTH = 8000  # characters, not tokens
```

**Impact:**

- Safety truncation for extremely long chunks
- Prevents timeout failures on oversized content
- Currently prevents 20-30 minute processing times

**Recommendation:**

```bash
# Add to .env
MAX_CHUNK_CHAR_LENGTH=8000  # Max characters per chunk (safety truncation)
```

**Rationale:**

- You may want to adjust this based on fine-tuning results
- Different models (Qwen 2.5 7B vs Mistral Nemo 12B) may handle different lengths
- Golden dataset collection may require different limits

---

### **Category 2: RFP Section Processing** ⚠️ HIGH PRIORITY

#### **File:** `src/core/chunking.py`

**Current Hardcoded Values:**

```python
# Line 275 - Page estimation
estimated_page = max(1, chars_before // 2000)  # ~2000 chars per page estimate

# Line 343 - Default chunk size
def create_contextual_chunks(self, sections: List[RFPSection], max_chunk_size: int = 2000)

# Line 532 - Document processing default
def process_document(self, document_text: str, max_chunk_size: int = 2000)
```

**Impact:**

- Page number estimation for metadata
- Default chunking strategy for sections
- Affects chunk distribution across RFP

**Recommendation:**

```bash
# Add to .env
RFP_CHARS_PER_PAGE=2000           # Estimated characters per page for page numbering
RFP_MAX_CHUNK_SIZE=2000           # Default max chunk size for RFP sections (characters)
RFP_MIN_SUBSECTION_LENGTH=50      # Minimum chars for valid subsection (line 324)
RFP_MIN_REQUIREMENT_LENGTH=30     # Minimum chars for valid requirement (line 494)
RFP_MAX_REQUIREMENTS_PER_CHUNK=10 # Limit requirements per chunk (line 497)
```

**Rationale:**

- Different RFP formats may have different page densities
- Experimentation during fine-tuning may require different chunk sizes
- Currently coupled to code, should be tunable

---

### **Category 3: Query Retrieval Thresholds** ⚠️ HIGH PRIORITY

#### **File:** `src/api/rfp_routes.py`

**Current Hardcoded Values:**

```python
# Line 411 - Content retrieval threshold
elif max_content < 50:

# Line 1050 - "Good enough" results threshold
if total_context >= 10:  # Threshold for "good enough" results

# Line 1057 - Best results threshold
if best_context_count >= 10:  # Good enough results found

# Line 1174 - Retry attempts
"broader_searches_attempted": 7,
```

**Impact:**

- Determines when query results are "sufficient"
- Affects retry logic for failed queries
- Controls search strategy escalation

**Recommendation:**

```bash
# Add to .env
QUERY_MIN_CONTENT_THRESHOLD=50    # Minimum content items for valid query result
QUERY_GOOD_ENOUGH_THRESHOLD=10    # Context count considered "good enough"
QUERY_MAX_RETRY_ATTEMPTS=7        # Max broader search attempts on failure
```

**Rationale:**

- Quality vs speed tradeoff should be tunable
- Different RFP types may need different thresholds
- Fine-tuned model may change optimal values

---

### **Category 4: Content Preview Limits** 🔶 MEDIUM PRIORITY

#### **File:** `src/api/rfp_routes.py`

**Current Hardcoded Values:**

```python
# Line 647 - Content truncation
"content": content[:2000],  # Limit to prevent context overflow

# Line 469 (rfp_agents.py) - Prompt truncation
{combined_content[:2000]}...  # Truncated for prompt efficiency
```

**Impact:**

- Limits content size in API responses
- Prevents context overflow in prompts
- Affects debugging visibility

**Recommendation:**

```bash
# Add to .env
API_CONTENT_PREVIEW_LENGTH=2000   # Max characters in content previews
PROMPT_CONTENT_MAX_LENGTH=2000    # Max characters in LLM prompts
```

**Rationale:**

- Response size vs completeness tradeoff
- May need adjustment for different use cases
- Debugging may require longer previews

---

### **Category 5: Batch Processing** 🔶 MEDIUM PRIORITY

#### **File:** `src/core/lightrag_integration.py`

**Current Hardcoded Values:**

```python
# Line 318 - Batch size for chunk processing
batch_size = 10  # Process in smaller batches
```

**Impact:**

- Controls parallel processing chunk batching
- Affects memory usage and processing speed
- Balances throughput vs resource consumption

**Recommendation:**

```bash
# Add to .env
CHUNK_BATCH_SIZE=10               # Number of chunks to process in parallel batch
```

**Rationale:**

- Different hardware may support different batch sizes
- RTX 4060 (8GB VRAM) vs RTX 3090 (24GB VRAM) different optimal sizes
- Fine-tuned smaller model may allow larger batches

---

### **Category 6: Pattern Matching Thresholds** 🔷 LOW PRIORITY

#### **File:** `src/core/lightrag_chunking.py`

**Current Hardcoded Values:**

```python
# Line 122-127 - RFP detection thresholds
pattern_matches >= 3  # Require multiple pattern matches for RFP detection
sections_found >= 3   # Strong indicator of RFP structure
```

**Impact:**

- Determines when document is classified as RFP vs standard doc
- Affects whether enhanced chunking is applied
- False positives/negatives in RFP detection

**Recommendation:**

```bash
# Add to .env
RFP_DETECTION_MIN_PATTERNS=3      # Minimum pattern matches to classify as RFP
RFP_DETECTION_MIN_SECTIONS=3      # Minimum sections to strongly indicate RFP
```

**Rationale:**

- Different RFP formats may need different detection sensitivity
- Currently conservative (may miss some RFPs)
- Tunable precision vs recall

---

### **Category 7: Requirement Extraction** 🔷 LOW PRIORITY

#### **File:** `src/core/processor.py`

**Current Hardcoded Values:**

```python
# Line 137 - Pattern search limit
match = re.search(pattern, document_text[:2000])  # Search first 2000 chars
```

**Impact:**

- Limits requirement pattern matching to document header
- Affects solicitation number extraction
- May miss patterns deeper in document

**Recommendation:**

```bash
# Add to .env
PATTERN_SEARCH_LENGTH=2000        # Characters to search for header patterns
```

**Rationale:**

- Some RFPs have long preambles
- Solicitation number may appear later
- Tunable based on RFP corpus analysis

---

### **Category 8: Logging Configuration** 🔷 LOW PRIORITY

#### **File:** `src/utils/logging_config.py`

**Current Hardcoded Values:**

```python
# Line 88-89
max_file_size: int = 10 * 1024 * 1024,  # 10MB
backup_count: int = 5,
```

**Impact:**

- Log file rotation thresholds
- Number of backup log files kept
- Disk space usage over time

**Current Status:**
✅ **Already configurable via function parameters**

**Recommendation:**

```bash
# Optional: Add to .env for startup override
LOG_MAX_FILE_SIZE_MB=10           # Max log file size before rotation (MB)
LOG_BACKUP_COUNT=5                # Number of backup log files to keep
```

**Rationale:**

- Currently works well as defaults
- Low priority since rarely needs changing
- Could add `.env` override for advanced users

---

## 📊 Summary Table

| Category                  | File                    | Line(s)  | Current Value   | Priority  | Impact              |
| ------------------------- | ----------------------- | -------- | --------------- | --------- | ------------------- |
| **Chunk Length Limit**    | lightrag_chunking.py    | 165      | 8000 chars      | 🔴 HIGH   | Processing timeouts |
| **Page Estimation**       | chunking.py             | 275      | 2000 chars/page | 🔴 HIGH   | Metadata accuracy   |
| **Default Chunk Size**    | chunking.py             | 343, 532 | 2000 chars      | 🔴 HIGH   | Chunking strategy   |
| **Min Subsection**        | chunking.py             | 324      | 50 chars        | 🔴 HIGH   | Section detection   |
| **Min Requirement**       | chunking.py             | 494      | 30 chars        | 🔴 HIGH   | Requirement quality |
| **Max Requirements**      | chunking.py             | 497      | 10 per chunk    | 🔴 HIGH   | Data structure      |
| **Content Threshold**     | rfp_routes.py           | 411      | 50 items        | 🔴 HIGH   | Query quality       |
| **Good Enough Threshold** | rfp_routes.py           | 1050     | 10 items        | 🔴 HIGH   | Search strategy     |
| **Retry Attempts**        | rfp_routes.py           | 1174     | 7 attempts      | 🔴 HIGH   | Reliability         |
| **Content Preview**       | rfp_routes.py           | 647      | 2000 chars      | 🟡 MEDIUM | API responses       |
| **Prompt Truncation**     | rfp_agents.py           | 469      | 2000 chars      | 🟡 MEDIUM | LLM efficiency      |
| **Batch Size**            | lightrag_integration.py | 318      | 10 chunks       | 🟡 MEDIUM | Performance         |
| **RFP Detection**         | lightrag_chunking.py    | 122-127  | 3 patterns      | 🔵 LOW    | Classification      |
| **Pattern Search**        | processor.py            | 137      | 2000 chars      | 🔵 LOW    | Header parsing      |
| **Log File Size**         | logging_config.py       | 88       | 10MB            | 🔵 LOW    | Disk usage          |

---

## 🎯 Recommended Implementation Plan

### **Phase 1: HIGH Priority (Do First)** 🔴

**Target**: Before next RFP processing run

**Changes:**

1. Add chunk processing limits to `.env`
2. Add RFP section processing config to `.env`
3. Add query retrieval thresholds to `.env`

**Files to Update:**

- `.env` - Add new variables
- `src/core/lightrag_chunking.py` - Read from env
- `src/core/chunking.py` - Read from env
- `src/api/rfp_routes.py` - Read from env

**Benefit:**

- Easy tuning during fine-tuning experiments
- No code changes needed for optimization
- Documented configuration in one place

---

### **Phase 2: MEDIUM Priority (Do After Golden Dataset)** 🟡

**Target**: Before fine-tuned model deployment

**Changes:**

1. Add content preview limits to `.env`
2. Add batch processing config to `.env`

**Files to Update:**

- `.env` - Add new variables
- `src/api/rfp_routes.py` - Read from env
- `src/core/lightrag_integration.py` - Read from env
- `src/agents/rfp_agents.py` - Read from env

**Benefit:**

- Optimize for fine-tuned model characteristics
- Tune batch sizes for faster/smaller model
- Adjust preview lengths based on actual usage

---

### **Phase 3: LOW Priority (Optional Enhancement)** 🔵

**Target**: After production deployment

**Changes:**

1. Add pattern matching thresholds to `.env`
2. Add requirement extraction config to `.env`
3. Add logging overrides to `.env`

**Files to Update:**

- `.env` - Add new variables
- `src/core/lightrag_chunking.py` - Read from env
- `src/core/processor.py` - Read from env
- `src/utils/logging_config.py` - Read from env (optional)

**Benefit:**

- Advanced tuning for specific RFP corpus
- Better detection for non-standard RFPs
- Flexible logging for different environments

---

## 💡 Implementation Example

### **Proposed `.env` Additions**

```bash
# ============================================================================
# RFP Processing Configuration
# ============================================================================

# Chunk Processing Limits
MAX_CHUNK_CHAR_LENGTH=8000        # Max characters per chunk (safety truncation)
RFP_CHARS_PER_PAGE=2000           # Estimated characters per page
RFP_MAX_CHUNK_SIZE=2000           # Default max chunk size (characters)
RFP_MIN_SUBSECTION_LENGTH=50      # Minimum chars for valid subsection
RFP_MIN_REQUIREMENT_LENGTH=30     # Minimum chars for valid requirement
RFP_MAX_REQUIREMENTS_PER_CHUNK=10 # Limit requirements extracted per chunk

# Query Retrieval Thresholds
QUERY_MIN_CONTENT_THRESHOLD=50    # Minimum content items for valid result
QUERY_GOOD_ENOUGH_THRESHOLD=10    # Context count considered sufficient
QUERY_MAX_RETRY_ATTEMPTS=7        # Max broader search attempts

# Content Handling
API_CONTENT_PREVIEW_LENGTH=2000   # Max characters in API previews
PROMPT_CONTENT_MAX_LENGTH=2000    # Max characters in LLM prompts

# Performance Tuning
CHUNK_BATCH_SIZE=10               # Chunks to process in parallel batch

# RFP Detection (Advanced)
RFP_DETECTION_MIN_PATTERNS=3      # Pattern matches to classify as RFP
RFP_DETECTION_MIN_SECTIONS=3      # Section count for strong RFP indicator
PATTERN_SEARCH_LENGTH=2000        # Characters to search for header patterns

# Logging (Optional Overrides)
LOG_MAX_FILE_SIZE_MB=10           # Log file rotation size (MB)
LOG_BACKUP_COUNT=5                # Backup log files to keep
```

### **Code Update Example**

**Before:**

```python
# src/core/lightrag_chunking.py
MAX_CHUNK_LENGTH = 8000  # characters, not tokens
```

**After:**

```python
# src/core/lightrag_chunking.py
import os

MAX_CHUNK_LENGTH = int(os.getenv("MAX_CHUNK_CHAR_LENGTH", "8000"))
```

---

## ⚠️ Important Considerations

### **1. Backward Compatibility**

- All new env vars should have sensible defaults
- Existing behavior maintained if `.env` not updated
- No breaking changes to current processing

### **2. Documentation**

- Each variable needs clear comment explaining purpose
- Include units (chars vs tokens, seconds vs minutes)
- Document safe ranges (min/max values)

### **3. Validation**

- Add validation for numeric ranges
- Warn if values are outside recommended bounds
- Fail gracefully with helpful error messages

### **4. Performance Impact**

- Reading env vars has negligible performance cost
- One-time read at module import is optimal
- Consider caching computed values (e.g., bytes from MB)

---

## 🔍 What's Already Good

### **✅ Currently in `.env` (Well Configured)**

```bash
# Core LLM Configuration
LLM_MODEL=mistral-nemo:latest
LLM_TIMEOUT=1800
OLLAMA_LLM_NUM_CTX=64000
NUM_PREDICT=4096

# Embedding Configuration
EMBEDDING_MODEL=bge-m3:latest
EMBEDDING_DIM=1024
EMBEDDING_TIMEOUT=300
MAX_EMBED_TOKENS=8192

# RAG Configuration
CHUNK_SIZE=800                    # Token-based chunk size
CHUNK_OVERLAP_SIZE=80             # Token-based overlap
MAX_ASYNC=2
MAX_PARALLEL_INSERT=2
COSINE_THRESHOLD=0.05
TOP_K=60
SUMMARY_MAX_TOKENS=8192
SUMMARY_CONTEXT_SIZE=12000

# Server Configuration
HOST=localhost
PORT=9621
WORKING_DIR=./rag_storage
INPUT_DIR=./inputs

# Logging
LOG_LEVEL=INFO
LOG_CONSOLE=true
```

**Analysis:**
✅ All critical LLM/embedding settings centralized  
✅ Timeout configurations in one place  
✅ Server/storage paths configurable  
✅ RAG parameters accessible for tuning

**No changes needed to these!**

---

## 📈 Expected Benefits

### **After Phase 1 Implementation:**

**Easier Experimentation:**

```bash
# Try different chunk limits without code changes
MAX_CHUNK_CHAR_LENGTH=10000  # Test with larger chunks
MAX_CHUNK_CHAR_LENGTH=6000   # Test with smaller chunks
```

**Fine-Tuning Optimization:**

```bash
# Adjust for faster fine-tuned model
CHUNK_BATCH_SIZE=20           # Process more chunks in parallel
QUERY_GOOD_ENOUGH_THRESHOLD=5 # Accept results faster
```

**RFP-Specific Tuning:**

```bash
# For DoD RFPs with dense sections
RFP_CHARS_PER_PAGE=2500       # Higher text density

# For commercial RFPs with graphics
RFP_CHARS_PER_PAGE=1500       # Lower text density
```

---

## ✅ Conclusion

**Summary:**

- **15 categories** of hardcoded values identified
- **9 HIGH priority** values affect processing behavior
- **3 MEDIUM priority** values affect performance
- **3 LOW priority** values rarely need changes

**Recommendation:**
✅ **Implement Phase 1 (HIGH priority) before next RFP processing run**

**Estimated Effort:**

- Phase 1: ~2 hours (update .env + 3 files)
- Phase 2: ~1 hour (update .env + 3 files)
- Phase 3: ~30 min (update .env + 3 files)

**Total: ~3.5 hours for complete centralization**

**Risk:**

- 🟢 LOW - Changes are straightforward env var reads
- 🟢 LOW - All have sensible defaults
- 🟢 LOW - No breaking changes to existing behavior

---

**Assessment Complete** ✅  
**Ready for implementation when RFP processing is finished**  
**All identified values documented with rationale and priority**
