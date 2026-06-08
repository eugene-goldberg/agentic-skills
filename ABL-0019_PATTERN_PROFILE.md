# ABL-0019 — Per-target Pattern Profile (cumulative learning, Stage 4)

> **Status: SPEC + implementation (2026-06-08).** Author: architect.
> Implements **Stage 4** of [`CUMULATIVE_LEARNING_ROADMAP.md`](CUMULATIVE_LEARNING_ROADMAP.md).
> Operator-approved 2026-06-08. Builds directly on the ABL-0016 Stage 1.5
> vector-retrieval machinery (`lessons_index.py`). Every infra claim shares
> Stage 1.5's verified stack (Ollama bge-m3 1024-dim, Milvus via pymilvus 3.0.0).

---

## 1. The gap this closes (verified)

Every engineer writes `_brownfield/{bl_id}/eng_patterns.md` — this target's
**architectural patterns** (layering, naming, error handling, DI), **invariants
to preserve**, **compatibility strategy**, closest-analog files, and blast
radius. The QA/scorer cite it and the brownfield rubric scores **Pattern
Fidelity** against it. Then it is discarded: a codebase grep confirms
`eng_patterns.md` is **written and existence-checked (R10/R11) but its content
is NEVER read back** — zero `read_text`/`glob`/parse of it anywhere in
`webapp/backend/app/`. Each new engineer re-derives the same conventions from
scratch. The crew hand-writes a style guide every sprint and burns it.

**Stage 4 closes it:** consolidate the per-BL `eng_patterns.md` into a durable,
semantically-retrievable per-target **pattern profile**, and surface it to
future engineers/scorers via the Stage 1.5 problem→neighbour mechanism. The
engineer about to touch the data layer pulls "how this codebase does
persistence/validation/DI" instead of re-deriving it. **Pattern Fidelity
compounds** — each sprint makes the next sprint's grounding cheaper and sharper.

This is the symmetric completion of the cumulative within-target story: A62/A63
+ Stage 1.5 closed the *findings → lessons* loop; ABL-0019 closes the
*eng_patterns → patterns* loop, reusing the same machinery.

## 2. Design (reuses Stage 1.5, minimal new surface)

**Source:** `_brownfield/**/eng_patterns.md` across the target (all features/BLs).
Engineers write a fixed `##`-section structure (prompts_brownfield.py:308–334):
`Closest existing implementations` · `Architectural patterns in use here` ·
`Invariants to preserve` · `Integration points / blast radius` ·
`Compatibility strategy` · `Planned slices`.

**Extractor (`pattern_profile.py`):** glob the files; split each by `##` headers
into **section entries**; keep the DURABLE convention sections (architecture,
invariants, compatibility — the cross-BL knowledge) and drop the BL-specific
noise (planned slices, this-BL blast radius) from the retrievable set; tag each
entry with its section as `area` + provenance (`bl_id`, `feature_slug`). A
stable `pattern_id = sha256(area + normalized text)[:…]` dedups near-identical
conventions repeated across BLs (the common case — every BL restates the same
layering).

**Store:** a dedicated per-target Milvus collection `patterns_<md5(repo)>`,
**reusing `lessons_index`'s store backends + embed + relevance floor unchanged**
(the store is a generic id→vec→payload store; patterns map onto the same payload
field names, `classification="pattern"`, plus an `area`). In-memory backend for
tests / no-Milvus fallback. Same `LESSON_MIN_SCORE` floor.

**Consolidated artifact:** `_brownfield/_pattern_profile/PATTERN_PROFILE.md` — a
deduped, area-grouped human/operator-readable profile (and a fallback push
source), written by the consolidator.

**Read path:** a `search_patterns(query, k)` MCP tool (sibling to
`search_lessons`), added to the agent `--allowedTools`, keyed by the stable
`RETRIEVAL_LESSONS_REPO`. Lazy build-if-empty (first agent indexes from existing
`eng_patterns.md`); refreshed at sprint end as new files land. Distinct from
`search_lessons` because the advisory framing differs: a pattern is "how this
codebase does X" (a convention to follow), not "a hazard that shipped" (a
falsification prior).

## 3. Batches

| Batch | Scope | Test gate |
|---|---|---|
| **A — `pattern_profile.py`** | extractor (glob + `##` split + durable-section filter + dedup by stable id), `consolidate` (write PATTERN_PROFILE.md), `index_patterns` (embed via lessons_index, upsert into patterns collection), `search_patterns` (floor, lazy build). Reuses lessons_index primitives. | unit: N files → section entries; dedup near-identical; durable-section filter; **effectiveness (real bge-m3): "adding a new DB table+model" → data-layer pattern top-1, unrelated → empty (floor)**; Milvus smoke (skip if down) |
| **B — MCP tool + wiring** | `search_patterns` tool in `retrieval_server.py`; add to `RETRIEVAL_MCP_TOOLS`; advisory push→pull pointer (behind a flag) telling engineers to search patterns. | tool in allowlist; tool returns [] gracefully when unavailable |
| **C — refresh hook** | re-consolidate + re-index at sprint end (after engineers write new eng_patterns.md) so the profile compounds. | unit: indexing new files updates the store |

## 4. Calibrated proposal (risk / test / rollback)

**Risk:** Low. Additive, advisory, target-scoped, reuses Stage 1.5's proven
machinery. Failure mode = stale/over-broad patterns crowding the prompt →
mitigated by the relevance floor + advisory framing + the agent's own grounding.
**Honest dependency:** pattern quality inherits `eng_patterns.md` quality — thin
source files → thin profile (the same "garbage-in" exposure A63 surfaced for
findings). Worth a later source-quality check; not blocking.

**Named test that proves benefit:** the real-embedding effectiveness test — index
real consolidated patterns; a problem statement ("adding a new SQLModel table and
route") retrieves the data-layer/route pattern above floor; an unrelated problem
returns nothing. Plus the consolidation/dedup unit tests.

**Named rollback:** behind a flag (mirror `inject_lessons`); the consolidator is
dormant additive code; `search_patterns` returns [] when the collection is absent
or infra is down; remove the tool from the allowlist to fully disable. The
existing lessons + code-retrieval paths are untouched.

## 5. Out of scope (this ABL)
- Cross-target/global pattern transfer (roadmap Stage 3).
- LLM-summarized profile synthesis (v1 is extract+dedup+retrieve; a synthesis
  pass over clusters is a later refinement).
- Source-quality enforcement on `eng_patterns.md` (noted dependency, separate).
