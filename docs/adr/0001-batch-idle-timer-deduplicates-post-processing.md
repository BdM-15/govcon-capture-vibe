# Batch idle-timer deduplicates semantic post-processing runs

LightRAG originally triggered our custom semantic post-processor after every individual document insert. Uploading N documents -> N post-processor runs. Each run is expensive and O(graph-size), so N concurrent runs on a growing graph became exponentially wasteful.

Decision: declare a "batch" via idle-timeout (`BATCH_TIMEOUT_SECONDS`). When the server goes idle for that window after the last document completes, exactly one post-processor run fires for the whole batch. The user controls effective batch size implicitly by uploading documents together.

Considered alternative: explicit batch-start/end API calls. Rejected — requires callers to manage lifecycle; idle-timer is zero-friction and works for both UI drag-drop and scan-folder flows.
