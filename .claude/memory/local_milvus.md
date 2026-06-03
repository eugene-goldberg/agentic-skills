---
name: local-milvus
description: Milvus runs as the official 3-container compose stack (etcd + minio + milvus-standalone). The embedded-single-container deployment SEGFAULTS on arm64 Macs.
metadata: 
  node_type: memory
  type: project
  originSessionId: 68d7b58a-c1db-43e1-bf9a-cac442cd4c1d
---

## How Milvus is actually deployed (updated 2026-06-02)

**Official 3-container compose stack** at `/tmp/milvus/docker-compose.yml`, downloaded from
`https://raw.githubusercontent.com/milvus-io/milvus/v2.5.27/deployments/docker/standalone/docker-compose.yml`.

Containers:
- `milvus-standalone` — main API on port 19530, healthcheck `/healthz` on 9091
- `milvus-etcd` — metadata coordination
- `milvus-minio` — object storage. **Container shows "unhealthy" but is functional** — the official healthcheck uses `curl` which isn't installed in the minio image. The actual `http://127.0.0.1:9000/minio/health/live` returns 200. Benign.

Image: `milvusdb/milvus:v2.5.27`.
Backend connection: `MILVUS_ADDRESS=localhost:19530` (in `webapp/.env`).

## DON'T use the embedded-single-container deployment

The `docker run -d milvusdb/milvus:v2.5.27 milvus run standalone` shortcut **segfaults on arm64 Macs** (verified 2026-06-02):

```
SIGNAL CATCH BY NON-GO SIGNAL HANDLER
SIGNO: 11; SIGNAME: Segmentation fault; SI_CODE: 1; SI_ADDR: 0x18
```

If a memory or prior session suggests bringing up Milvus that way, prefer the 3-container compose path.

## How to bring it back up (verified 2026-06-02)

```bash
mkdir -p /tmp/milvus
curl -sL https://raw.githubusercontent.com/milvus-io/milvus/v2.5.27/deployments/docker/standalone/docker-compose.yml \
  -o /tmp/milvus/docker-compose.yml
cd /tmp/milvus && docker compose -p milvus up -d
# Wait ~20 seconds for standalone to become healthy
```

Verify:
```python
import socket; s = socket.socket(); s.connect(('127.0.0.1', 19530))  # should not raise
```
or:
```bash
curl http://127.0.0.1:9091/healthz   # → 200 OK
```

## Collections of interest

- `hybrid_code_chunks_*_<pathhash>` — populated by `@zilliz/claude-context-core` via `.spike-node/bridge.js`. Provider selected by `EMBEDDING_PROVIDER` env (`Ollama` = bge-m3 1024-dim; `AzureOpenAI` = azure_3_large 3072-dim).

## When Milvus is rebuilt

Collections from prior sessions are LOST. Re-indexing happens automatically at sprint start (`index_initial.start` phase). For Financial_Management or any new feature, no manual re-index needed — orchestrator handles it.

## Stat counter gotcha

`getCollectionStatistics` returns lazy/cached row counts. For a real count after indexing, call `flush()` first then `query(filter:'', output_fields:['relativePath'], limit:N)` and count results.

## Related

- `arch_disk_leak_fixes.md` (the disk reap that wiped Milvus once)
- `embedding_stack_ollama.md` (bge-m3 provider)
