---
name: local-milvus
description: claude-context indexing depends on a local Milvus container already running
metadata: 
  node_type: memory
  type: project
  originSessionId: 2b184b19-1809-4a2e-bad8-ec19ea9ee94c
---

**Local Milvus is already running** on this machine via Docker — `milvusdb/milvus:v2.5.27` container `milvus-standalone` on `localhost:19530`. Container has multi-day uptime; user does not start it explicitly.

This means: the `@zilliz/claude-context-core` retrieval layer and the webapp's `Run claude-context index` button work out of the box. No Zilliz Cloud signup is needed.

**Collections of interest:**
- `hybrid_code_chunks_azure_3_large_<pathhash>` — 3072-dim, populated by the AzureEmbedding adapter through `.spike-node/bridge.js`. The `azure_3_large` suffix comes from `CODE_CHUNKS_COLLECTION_NAME_OVERRIDE` in `.env.gpt54` / `.env.kimi`.

**Stat counter gotcha:** Milvus's `getCollectionStatistics` returns lazy/cached row counts. To get a real count after indexing, call `flush()` first and then `query(filter:'', output_fields:['relativePath'], limit:N)` and count results.

**How to apply:** if a future task involves indexing or semantic search, assume Milvus is up. If it's not (`docker ps | grep milvus` returns nothing), the user needs to bring it back up — don't try to spin up a new one without asking, the env may rely on existing collections.
