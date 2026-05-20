---
name: embedding-stack-ollama
description: On brownfield-production, embeddings come from local Ollama (bge-m3), not Azure
metadata:
  type: reference
---

**Embedding stack on `brownfield-production`:**

- **Provider:** local Ollama on this Mac (`brew services start ollama`).
- **Model:** `bge-m3` (1024-dim).
- **Endpoint:** `http://127.0.0.1:11434/api/embed`.
- **Config:** `webapp/.env` carries only embedding + Milvus vars:
  ```
  EMBEDDING_PROVIDER=Ollama
  OLLAMA_HOST=http://127.0.0.1:11434
  EMBEDDING_MODEL=bge-m3
  EMBEDDING_DIMENSION=1024
  MILVUS_ADDRESS=localhost:19530
  ```
- **Bridge:** the auto-generated `.spike-node/bridge.js` (regenerated from
  `langgraph_engine/retrieval/semantic.py`'s `BRIDGE_SCRIPT` constant)
  ships an `OllamaEmbedding` class alongside `AzureEmbedding`.
- **Warm latency:** ~250 ms per embed call.

**Why we left Azure:** Azure `text-embedding-3-large` deployment at
`aif-eus2-intplatformsvc-dev-001` became unresponsive after a 1086-chunk
indexing burst (TPM throttling). Local Ollama removes the network and
quota dependencies entirely.

**Defender gotcha (independently relevant):** Microsoft Defender for
Endpoint on this Mac silently blocked Node's outbound connections to
intra-LAN hosts that hosted Ollama. curl, ping, and SSH worked; Node got
EHOSTUNREACH on the same destination. The fix was running Ollama directly
on this Mac (loopback only — Defender doesn't intercept). If embeddings
ever need to come from another host on the LAN, expect Defender to need
explicit whitelisting or use an SSH tunnel to 127.0.0.1.

**Refs:** see also [[local-milvus-assumption]], superseded
[[azure-openai-access]] (still valid for the older harness runs in
`langgraph_engine/ab_runs/`).
