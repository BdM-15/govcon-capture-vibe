# LightRAG Library Patch Notes

## Issue Summary

**Problem**: Section-aware chunking for RFP documents was not activating despite proper configuration in `src/server.py`.

**Root Cause**: The LightRAG framework does not natively support custom chunking functions through its configuration system (`global_args`). When `create_app(global_args)` is called, it creates a `LightRAG` instance at line 595 of `lightrag_server.py` without any `chunking_func` parameter, even if one is set in `global_args`.

## Solution Applied

### Modified File: `.venv\Lib\site-packages\lightrag\api\lightrag_server.py`

**Location**: Line 593-630

**Change**: Added support for custom chunking functions by:

1. Reading `chunking_func` from `global_args` (if present)
2. Passing it to the `LightRAG` constructor

**Modified Code**:

```python
# Initialize RAG with unified configuration
try:
    # Check if custom chunking function is provided in global_args
    chunking_func_param = getattr(args, 'chunking_func', None)

    rag = LightRAG(
        working_dir=args.working_dir,
        workspace=args.workspace,
        # ... other parameters ...
        chunking_func=chunking_func_param,  # Add custom chunking function support
        # ... remaining parameters ...
    )
```

### Updated File: `src\server.py`

**Changes**:

1. **Removed**: Ineffective post-creation patching code (lines 91-107)
2. **Simplified**: Configuration now relies on the patched library
3. **Documentation**: Added comments explaining that library has been patched

**Key Lines**:

```python
# Line 78: Set chunking function in global_args
global_args.chunking_func = rfp_aware_chunking_func

# Line 89-90: Create app - library now handles chunking_func automatically
app = create_app(global_args)

# Line 92: Confirmation message
print("   ✅ Section-aware chunking enabled via patched LightRAG library")
```

## How It Works

### Before Patch

1. `src/server.py` sets `global_args.chunking_func = rfp_aware_chunking_func`
2. `create_app(global_args)` is called
3. **PROBLEM**: Library creates `LightRAG(...)` without checking for `chunking_func` in `global_args`
4. Result: Token-based chunking used (74 chunks)
5. Custom logs never appeared (no 🔍, 📋 emojis)

### After Patch

1. `src/server.py` sets `global_args.chunking_func = rfp_aware_chunking_func`
2. `create_app(global_args)` is called
3. **FIX**: Library reads `chunking_func` from `global_args` via `getattr(args, 'chunking_func', None)`
4. Passes it to `LightRAG()` constructor as `chunking_func=chunking_func_param`
5. Result: Section-aware chunking active, custom logs will appear
6. Expected: Different chunk count (not 74), section boundaries respected

## Testing Section-Aware Chunking

### Expected Logs

When processing starts, you should see:

```
🔍 Starting chunking - content length: 489,234 chars
📋 RFP detection result: True
🎯 RFP document detected - using enhanced section-aware chunking
⚙️ Initializing ShipleyRFPChunker...
✅ ShipleyRFPChunker initialized
📊 Processing document with Shipley RFP methodology...
🔍 Scanning document for RFP sections (489,234 chars)...
   Searching for Section A...
   Searching for Section B...
   ...
```

### Expected Behavior

1. **Chunk Count**: Should differ from 74 (token-based count)
2. **Chunk 33 Area**: Should split at section boundaries or complete faster
3. **Section Metadata**: Chunks should include RFP section information
4. **No Timeout**: Chunk 33 should not timeout after 59 minutes

## Reverting the Patch (If Needed)

If you need to revert to standard LightRAG behavior:

### Option 1: Restore Library File

```powershell
# Uninstall and reinstall LightRAG to get clean version
uv pip uninstall lightrag
uv pip install lightrag-hku==1.4.9
```

### Option 2: Remove Patch Manually

Edit `.venv\Lib\site-packages\lightrag\api\lightrag_server.py` line 593:

**Remove these lines:**

```python
# Check if custom chunking function is provided in global_args
chunking_func_param = getattr(args, 'chunking_func', None)
```

**Remove from LightRAG constructor:**

```python
chunking_func=chunking_func_param,  # Remove this line
```

### Option 3: Don't Set chunking_func

In `src/server.py`, comment out line 78:

```python
# global_args.chunking_func = rfp_aware_chunking_func  # Disable section-aware
```

## Future Improvements

### Upstream Contribution

Consider submitting a pull request to LightRAG project:

- **Repository**: https://github.com/HKUDS/LightRAG
- **Feature Request**: Native support for `chunking_func` in `global_args`
- **Benefit**: Enables domain-specific chunking for all users
- **Use Case**: Government contracting, legal documents, structured reports

### Alternative Approaches (Not Recommended)

1. **Monkey Patching**: Use garbage collector to find and patch instances
2. **Middleware**: Intercept requests and patch before processing
3. **Pre-chunking**: Chunk document before passing to LightRAG

These were rejected because:

- More complex and brittle
- Harder to maintain
- Don't follow LightRAG patterns
- Patching library is cleaner and more reliable

## Related Files

- **Chunking Implementation**: `src/core/lightrag_chunking.py`
- **Shipley Chunker**: `src/core/chunking.py`
- **Prompt Templates**: `prompts/shipley_requirements_extraction.txt`
- **Architecture**: `README.md` (Copilot instructions)

## Version Information

- **LightRAG Version**: 1.4.9
- **Patch Date**: 2025-01-02
- **Python Environment**: `.venv` (uv-managed)
- **Patched File**: `.venv\Lib\site-packages\lightrag\api\lightrag_server.py`

## Next Steps

1. **Stop Current Server**: User should stop the currently running server
2. **Restart Server**: Run `python app.py` to activate patched library
3. **Upload Document**: Use WebUI to upload RFP
4. **Monitor Logs**: Check `logs/lightrag.log` for custom chunking messages
5. **Verify Chunks**: Confirm chunk count differs from 74
6. **Test Chunk 33**: Ensure no timeout occurs in problematic area

---

**Note**: This patch modifies a library file in `.venv`. If you reinstall LightRAG or recreate the virtual environment, you will need to reapply this patch.
