---
name: arch_retrieval_has_index_shortcircuit
description: Root cause + fix for agent semantic_search failing with a 900s op=index timeout (the real grounding-blind blocker after the Ollama string-embed fix)
metadata:
  type: project
---

2026-06-12: THE blocker that made agents ground-blind on the remote even after
the [[arch_ollama_embed_string_hang]] fix. Root cause (read from source, not
inferred): `SemanticRegistry.search()` (`langgraph_engine/retrieval/semantic.py`)
ran a **blocking `op=index`** on the first search per process. On CPU-only bge-m3
a full `indexCodebase` of a real repo exceeds the **900s op=index timeout**
(`_run_bridge`: `timeout = 900 if op=='index'`), so `search()` returned the index
*error* without ever querying — every agent `semantic_search` failed (PO + engineer
both errored `"node bridge timed out after 900s during op='index'"`; `index_initial`
itself exit-124'd at 900s with `claude_context.ok=false`).

The kicker: bridge.js already had an **`op=has_index`** op built for exactly this
short-circuit ("skip re-indexing when the index is already populated") — but **no
Python code ever called it** (`grep` = zero callers). So every fresh MCP-server
process re-triggered the doomed index.

**Fix (commit `bb3ef2e`, dev≡main):** `search()` now probes `has_index` first; if
the collection has rows, mark `_indexed` and go straight to `op=search`; else fall
through to the original `index()` path. Empty/missing collection and a failed
has_index probe both preserve prior behavior. Test:
`webapp/backend/tests/test_semantic_has_index_shortcircuit.py` (4 cases).

**Proven:** after a clean full index, `has_index` → `has_rows:true` and `op=search`
returns relevant hits in ~1.2s (no 900s index). retrieval_server.py loads semantic.py
via `spec_from_file_location` → that file IS the live source for the webapp MCP server.

**Separate follow-up (not fixed):** `index_initial` re-indexes every run and its own
op=index can time out at 900s on CPU; indexCodebase is incremental (entity count
grows monotonically across runs) so a one-time complete index + this short-circuit
makes grounding work. A clean full index of the ecommerce repo = 243 files / 1187
chunks / ~887 Milvus entities (the earlier "6000" was duplicate accumulation from
concurrent search-triggered reindexes).

Operational note: a manually-launched `node bridge.js {...}` (cwd `.spike-node`) has
NO path in argv → `pkill -f "spike-node/bridge.js"` MISSES it; use `pkill -f bridge.js`.
Concurrent indexers on one collection corrupt/duplicate — always ensure exactly one.
