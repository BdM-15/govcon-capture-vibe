# Logs Directory

Captures all processing and server activity with automatic rotation (10MB files, 5 backups per log).

## Log File Locations

| File                         | Location                   | Purpose                                            |
| ---------------------------- | -------------------------- | -------------------------------------------------- |
| `{workspace}_processing.log` | `rag_storage/{workspace}/` | RFP extraction, inference progress (per workspace) |
| `{workspace}_errors.log`     | `rag_storage/{workspace}/` | All errors for this workspace                      |
| `server.log`                 | `logs/`                    | Server startup, API calls (central, shared)        |

The workspace name is embedded in the filename so logs are self-describing when viewed in an editor, file explorer, or log aggregator without needing to navigate the directory tree.

**Example** — workspace `afcapv_bos_i_t7`:

```
rag_storage/afcapv_bos_i_t7/afcapv_bos_i_t7_processing.log
rag_storage/afcapv_bos_i_t7/afcapv_bos_i_t7_errors.log
logs/server.log
```

## Log Files

### `{workspace}_processing.log`

**Purpose**: Complete RFP processing history  
**Contains**:

- Document upload and parsing through the native LightRAG parser pipeline (MinerU/native routes)
- Entity extraction counts by type
- Relationship inference (Phase 6) results
- Metadata enrichment (Phase 7) results
- GraphML file operations
- LLM calls for extraction/inference

**Use Cases**:

- Review overnight RFP processing results
- Debug extraction quality issues
- Track Phase 6/7 execution
- Analyze entity/relationship counts over time

**Example Entries**:

```
2025-01-25 14:30:15 | INFO | src.server.native_ingestion | 📄 Processing M6700425R0007 MCPP II DRAFT RFP 23 MAY 25.pdf via native LightRAG parser pipeline
2025-01-25 14:30:45 | INFO | src.server.routes | 📊 PRE-INFERENCE: 4793 entities, 5932 relationships
2025-01-25 14:31:02 | INFO | src.server.routes | 🤖 Running LLM-powered relationship inference (5 algorithms)...
2025-01-25 14:31:15 | INFO | src.server.routes | ✅ Phase 7 complete: 40 entities enriched with metadata
```

---

### `server.log`

**Purpose**: Server operations and configuration  
**Contains**:

- Server startup and initialization
- Configuration settings (LLM models, embeddings, chunk sizes)
- API endpoint registrations
- WebUI access logs
- Health checks (if not filtered)

**Use Cases**:

- Verify server started correctly
- Check configuration values
- Monitor API endpoint usage
- Debug server issues

**Example Entries**:

```
2025-01-25 14:29:50 | INFO | theseus.server | 🚀 LightRAG-first Capture Workbench Starting
2025-01-25 14:29:51 | INFO | theseus.server | LLM: grok-4-fast-reasoning via https://api.x.ai/v1
2025-01-25 14:29:51 | INFO | theseus.server | Embeddings: text-embedding-3-large via https://api.openai.com/v1
2025-01-25 14:29:52 | INFO | uvicorn | Application startup complete
```

---

### `{workspace}_errors.log`

**Purpose**: All errors from any component  
**Contains**:

- Processing errors (parsing, extraction, inference)
- Server errors (API failures, config issues)
- LLM errors (rate limits, API failures)
- GraphML errors (schema conflicts, file corruption)

**Use Cases**:

- Debug failed RFP processing
- Identify recurring issues
- Track error patterns
- Monitor system health

**Example Entries**:

```
2025-01-25 14:35:22 | ERROR | lightrag | ValueError: invalid literal for int() with base 10: 'Significantly More Important'
2025-01-25 14:35:22 | ERROR | src.server.routes | ❌ GraphML never populated after 15s total wait
```

---

## Log Rotation

**Max File Size**: 10MB per log file  
**Backup Count**: 5 files per log (e.g., `{workspace}_processing.log.1`, `{workspace}_processing.log.2`, etc.)  
**Total Storage**: ~50MB per log type (10MB × 5 backups)  
**Rotation Trigger**: Automatic when file reaches 10MB

When a log file reaches 10MB:

1. `{workspace}_processing.log` → `{workspace}_processing.log.1`
2. `{workspace}_processing.log.1` → `{workspace}_processing.log.2`
3. ... (up to `{workspace}_processing.log.5`)
4. `{workspace}_processing.log.5` is deleted
5. New `{workspace}_processing.log` starts fresh

---

## Console Output

Terminal still shows important messages, but **filtered** to remove noise:

- ✅ **Shows**: RFP processing progress, entity counts, Phase 6/7 results, errors
- ❌ **Filters**: HTTP health checks, uvicorn access logs, localhost requests

This prevents terminal buffer overflow during overnight processing while keeping visibility into active operations.

---

## Viewing Logs

### Tail Live Processing

```powershell
Get-Content logs/processing.log -Wait -Tail 50
```

### Check Recent Errors

```powershell
Get-Content logs/errors.log | Select-Object -Last 20
```

### Search for Specific RFP

```powershell
Select-String -Path logs/processing.log -Pattern "MCPP II"
```

### View All Entity Counts

```powershell
Select-String -Path logs/processing.log -Pattern "entities, .* relationships"
```

### Monitor Phase 7 Enrichment

```powershell
Select-String -Path logs/processing.log -Pattern "Phase 7"
```

---

## Troubleshooting

### "Log files too large"

Logs auto-rotate at 10MB with 5 backups (~50MB total per log). If you need more history, increase `backup_count` in `app.py`:

```python
log_info = setup_logging(
    backup_count=10,  # Keep 10 backup files instead of 5
)
```

### "Can't find processing details"

Processing logs are in `rag_storage/{workspace}/{workspace}_processing.log`, not `server.log`. Use:

```powershell
# Replace 'afcapv_bos_i_t7' with your workspace name
Get-Content rag_storage/afcapv_bos_i_t7/afcapv_bos_i_t7_processing.log -Wait -Tail 100
```

### "Terminal still showing health checks"

Console filtering only removes HTTP GET/POST patterns. If health checks still appear, update `HTTPFilter` in `src/utils/logging_config.py`.

---

## Integration

Logging is initialized in `app.py` before server startup:

```python
from src.utils.logging_config import setup_logging

log_info = setup_logging(
    log_level="INFO",
    log_dir="logs",
    max_file_size=10 * 1024 * 1024,  # 10MB
    backup_count=5,
    console_output=True
)
```

All `logger.info()`, `logger.error()`, etc. calls automatically route to appropriate log files based on filters defined in `logging_config.py`.
