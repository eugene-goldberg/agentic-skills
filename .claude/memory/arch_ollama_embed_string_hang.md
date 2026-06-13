---
name: arch_ollama_embed_string_hang
description: "Root cause of \"retrieval fails / PO grounds blind\" — Ollama /api/embed hangs on STRING input (needs array); spike-node bridge _embedOne fixed 2026-06-12 (95d0f81)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 36f446e4-bf0d-4484-aecb-c91ae129c9d8
---

**The all-day "retrieval failing, PO grounds blind, semantic_search hangs" symptom
(seen on BOTH the Mac and remote) has ONE root cause, found 2026-06-12 by isolating
the spike-node bridge on the remote host:**

- **Ollama `/api/embed` HANGS on a bare-STRING `input`** (request never returns,
  `http=000` at 40s) but works with an **array** `input: ["..."]` (~3.8s). Observed on
  Ollama **0.24.0**. Worse: each stuck string request pins an inference slot at 100%
  CPU and never releases → after a few, the whole Ollama instance wedges (even array
  requests then hang) and only `systemctl restart ollama` (sudo) clears it.
- The bridge (`langgraph_engine/retrieval/semantic.py` `BRIDGE_SCRIPT` →
  `.spike-node/bridge.js`) split exactly on this:
  - `embedBatch` (used by **INDEX**) sends `input: [array]` → indexing always worked.
  - `_embedOne` (used by **SEARCH** query embed) sent `input: text` (string) → every
    `semantic_search` query embed hung → agent retrieval wedged → grounding blind.
- This is why index_initial succeeded but the PO's `semantic_search` hung, and why
  `retrieval.jsonl` showed only `target_status` (the one non-embedding call).

**Fix (commit 95d0f81, dev≡main):** `_embedOne` now sends `input: [text]` and reads
`embeddings[0]` (parser already handled it); both `_embedOne` (60s) and `embedBatch`
(120s) got `AbortSignal.timeout` so a future Ollama stall can never hang an agent
indefinitely. The harness regenerates `bridge.js` from `BRIDGE_SCRIPT` on next run.

**Verification status:** the string-vs-array hang is deterministic + reproduced. Final
live verification of the search path was BLOCKED on restarting the already-wedged
remote Ollama (sudo, operator-only). After restart, the patched bridge won't re-wedge.

**Lesson:** any host-level embed/HTTP call in the bridge MUST carry a timeout, and
MUST use the array `input` form. A no-timeout `fetch` to a model server is a latent
whole-crew wedge. See [[arch_zero_escape_chain]] context (retrieval is advisory, so the
crew still *runs* blind — but grounded retrieval needs this fix). Remote migration:
[[arch_active_branch]].
