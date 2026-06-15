---
name: arch-reindex-incremental
description: Flag-gated incremental barrier reindex (op=index_baseline + op=reindex) + the pre-existing index_initial 900s baseline-cap finding
metadata:
  type: project
---

2026-06-15: SHIPPED the reindex-incremental short-circuit (`be37669`, dev≡main), flag
`reindex_incremental` **DEFAULT ON** for every crew run (operator 2026-06-15, `3ad9c9c`);
`reindex_incremental=false` is the byte-identical full-index rollback. Operator-chosen +
operator-gated (high blast radius: the bridge is the shared retrieval indexer for every agent).

**Root cause** (claude-context-core 0.1.13): the bridge `op=index` calls
`indexCodebase(force=false)` which ALWAYS re-embeds every file (`getCodeFiles` →
`processFileList(all)`) — no snapshot diff. The incremental path is the SEPARATE
`reindexByChange` (merkle `checkForChanges` → embeds only added/removed/modified, instant on 0
changes), which the harness never called. So every barrier reindex was a full re-embed.

**Change**: source of truth is `langgraph_engine/retrieval/semantic.py`'s `BRIDGE_SCRIPT`
(`.spike-node/bridge.js` is GITIGNORED + regenerated from it). New ops: `index_baseline`
(establish merkle snapshot FIRST, then full embed) and `reindex` (incremental reindexByChange,
full-index fallback if no collection). `indexing.run_claude_context_index` gained an `op` param;
`orchestrator._run_indexers` maps label→op when the flag is on (index_initial→index_baseline,
reindex_after_*→reindex; else "index" everywhere); flag threaded through run_brief +
RunBriefRequest. 4 unit tests + isolation test + 567 suite.

**Snapshot-FIRST ordering is the crux** (caught by the FIRST live-proof, run-…132221Z-e5aa54):
index_baseline's full embed HITS the 900s indexer timeout and the node process is killed. With
the snapshot established AFTER the embed, that step never ran → no baseline snapshot → op=reindex
saw 0 changes and SILENTLY DROPPED the wave's .cs files from the index (verified absent from
search as code). Fix: establish the snapshot first (hashing only, embeds nothing) so a timeout
on the embed can't lose it. Unit+isolation tests PASSED before this was caught — only the live
search of the real index exposed it. Lesson: live-prove index/retrieval changes against a real
search; unit-green is not enough. [[feedback_honest_verification]]

**Live-proven** (run-20260615T140733Z-df8c69, flag ON): reindex 4.4s vs the 900s-capped full
embed (~200x); a real search of the live Milvus collection returns the wave-added
DiagAlpha/DiagBetaController.cs (+ their tests) as INDEXED relativePaths → no silent drop.

**PRE-EXISTING follow-up surfaced (NOT fixed here):** index_initial's full `indexCodebase` of
fullstack-ecommerce-app (~280 files) EXCEEDS the 900s timeout on CPU bge-m3 and is TRUNCATED →
the baseline index is PARTIAL on every run (flag on or off). This is THE likely reason agents
sometimes "ground blind". Orthogonal to the incremental reindex (which reliably indexes the wave
delta). Fix options: raise/stream the index_initial budget, batch embeds, or GPU embeddings.
See [[arch_retrieval_has_index_shortcircuit]] (has_index guards the SEARCH path, not
index_initial/reindex) and [[arch_ollama_embed_string_hang]]. [[feedback_remote_first_dev]]
