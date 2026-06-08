# ABL-0016 Stage 1.5 — Semantic lessons retrieval (problem→lesson matching)

> **Status: SPEC + implementation (2026-06-08).** Author: architect.
> Extends [`ABL-0016_LESSONS_AS_CONTEXT.md`](ABL-0016_LESSONS_AS_CONTEXT.md)
> (Stage 1 / Option A, shipped). Grounded in a verification pass of the live
> retrieval stack (Ollama bge-m3 1024-dim ✓, Milvus reachable via pymilvus
> 3.0.0 ✓, `retrieval_server.py` tool pattern). Every infra claim probed.

---

## 1. The gap this closes (precise)

Stage 1 (Option A) injects a **coarse, target-scoped** lessons block: the union
of all confirmed lessons in the target, ranked by recurrence/recency, capped at
8 — with **no matching to the agent's actual problem**. Relevance is delegated
entirely to the receiving agent's judgment. That is fine at 1 lesson; it
**degrades as the store grows** (top-8-by-recurrence injects a near-arbitrary
set w.r.t. the current BL; the genuinely relevant lesson may not make the cap,
while unrelated ones consume prompt budget).

Stage 1.5 adds the **precise matching mechanism**: the agent **dynamically
derives a natural-language description of the problem it is facing** and queries
a **lessons vector store** for the nearest-neighbour lesson(s) above a relevance
floor. Match is on the *problem*, not the *repo* — and on the agent's *live*
understanding, not a static file list. This is **pull** (a tool the agent calls
during grounding), mirroring how the crew already grounds against code.

## 2. Why pull-by-problem-statement (not push-by-filename)

- The agent's articulation of its problem is a richer, semantically-aligned
  query than the BL's nominal file list — and it tracks the problem as the agent
  *discovers* it mid-task (e.g. "this forces me to touch streak aggregation" →
  pull the streak lesson, even if the BL never named `streak.py`).
- Pull fits the existing grounding loop (`semantic_search` is already 4–5 calls
  per agent). `search_lessons` is a sibling tool, same muscle memory.
- The agent weighs results with its own grounding — the advisory framing
  ("falsification priors, not bans") is preserved.

## 3. Architecture (grounded in the live stack)

**Embedding:** local Ollama `bge-m3` (1024-dim), via `OLLAMA_HOST` +
`EMBEDDING_MODEL` from `webapp/.env` — the SAME embedder the code index uses.
`POST {OLLAMA_HOST}/api/embeddings {model, prompt}` → `{"embedding":[…1024]}`
(probed: dim=1024 ✓).

**Vector store:** a dedicated per-target Milvus collection
`lessons_<md5(repo_path)[:8]>` (parallel to the code `hybrid_code_chunks_<md5>`
collections; probed reachable). Schema: `finding_id` (PK varchar),
`feature_slug`, `classification`, `verdict`, `scope` (target|global), `body`
(the A63 rendered lesson text — root_cause+fix_locus, else summary),
`source_run_id`, `embedding` (FLOAT_VECTOR[1024]). Metric **COSINE**.
NOT routed through the claude-context Node bridge (that is code-file-oriented).

**Relevance floor (the critical guard):** a lessons corpus is small and each
lesson short — in a sparse space, nearest-neighbour ALWAYS returns something
with deceptively high similarity. `search_lessons` returns only hits with
`score >= LESSON_MIN_SCORE`; below floor → empty (silent). Without this, the
mechanism reintroduces the noise it exists to remove.

**Write path (freshness):** confirmed lessons are indexed (a) lazily —
`search_lessons` builds the target index from the ledger if the collection is
empty — and (b) write-through — on any `set_verdict→confirmed` (incl. A62
self-confirm), upsert that lesson. Dedup is free: `finding_id` is the PK
(stable hash).

**Read path (the tool):** `search_lessons(query, k=5)` in `retrieval_server.py`
— embeds the agent's problem statement, searches the target's lessons
collection, returns lessons above floor with body+provenance. Registered
alongside `semantic_search`; added to the agent `--allowedTools`. A prompt line
(behind `inject_lessons`) instructs roles to derive a problem statement and
query it during grounding.

## 4. Testability / effectiveness proof

The matching logic is factored from the Milvus backend so effectiveness is
provable WITHOUT Milvus in CI:
- `embed_text(text)` — real Ollama call (skip test cleanly if Ollama down).
- `select_above_floor(scored, k, min_score)` — pure ranking/floor (synthetic
  vectors, deterministic, no infra).
- Two store backends behind one interface: `InMemoryLessonStore` (cosine, for
  tests + a no-Milvus fallback) and `MilvusLessonStore` (production).
- **Effectiveness test (real bge-m3 embeddings, in-memory store):** index 3
  semantically-distinct lessons (streak/rest-aware, auth/login, pagination);
  query with a problem statement near ONE → assert it is top-1 above floor; an
  unrelated problem ("how to send email") → assert empty (floor works). This is
  the real proof that problem→lesson matching works on actual embeddings.

## 5. Batches

| Batch | Scope | Test gate |
|---|---|---|
| **A — `lessons_index.py`** | embed_text (Ollama), `select_above_floor` (pure), `InMemoryLessonStore` + `MilvusLessonStore` (one iface), `index_lessons(repo)` (read ledger via `lessons.list_lessons`, embed A63 body, upsert), `search_lessons(repo, query, k, min_score)`. | unit: floor/rank (synthetic); **effectiveness (real embeddings, in-memory): right lesson top-1, unrelated→empty**; Milvus backend smoke (skip if Milvus down) |
| **B — MCP tool + wiring** | `search_lessons` tool in `retrieval_server.py` (lazy build-if-empty + floor); add to `--allowedTools`; prompt instruction (behind `inject_lessons`) for roles to derive a problem statement and query. | tool registered; allowlist contains it; prompt carries the instruction when flag on |
| **C — write-through** | upsert on `set_verdict→confirmed` (A62 seam + the operator triage path); observable. | unit: confirming a finding indexes it; search then finds it |

## 6. Cross-target / "community" extension (Stage 3 — scoped, not built here)

The same mechanism, with `scope="global"` lessons in a shared collection,
queried by problem statement, gives the mission's literal "carries forward
across targets." Deferred because it sharpens the poisoned-memory risk and
needs: provenance marking (target-of-origin), **operator-gated graduation** from
per-target → global (consistent with "doctrine stays operator-gated forever"),
and the same relevance floor. Stage 1.5 builds the substrate (the `scope` field
+ the vector mechanism) so Stage 3 is an additive collection + a graduation
gate, not a rebuild.

## 7. Calibrated proposal

**Risk:** Low–medium. Additive; advisory (agent grounds; not binding). New infra
dependency (Milvus) for the production path, but the read path degrades
gracefully — if Milvus/Ollama are down, `search_lessons` returns empty (never
errors a sprint). Main failure mode is weak nearest-neighbours → mitigated by
the relevance floor + advisory framing + small k.
**Named test that proves benefit:** the real-embedding effectiveness test (§4) —
problem→correct-lesson top-1, unrelated→empty.
**Named rollback:** `search_lessons` returns empty when the collection is absent
or the flag prompt-instruction is off; remove the tool from the allowlist to
fully disable. The Stage-1 Option-A push block is untouched and independent.

## 8. Out of scope (this stage)
- Cross-target/global collection + graduation gate (Stage 3, §6).
- Re-embedding strategy beyond lazy-build + write-through (fine at current
  scale).
- Improving `_extract_evidence_summary` prose fallback (A63 follow-up).
