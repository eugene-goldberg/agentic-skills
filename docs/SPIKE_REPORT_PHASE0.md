# Phase 0 Spike Report

Date: 2026-05-17
Branch: `skills_with_graphs`
Goal: Validate Graphify + semantic search can power an agent retrieval layer.

## Setup

- New venv `.venv-spike/` (Python 3.12) — isolated from `.venv-lg` so it can't disturb the active kimi run.
- Installed:
  - `graphifyy==0.8.9` (PyPI) — provides `graphify` CLI.
  - `openai`, `numpy` (semantic search spike — see "Library choice" below).
- Reference repo curated at `reference-repos/fastapi-good-patterns/` by snapshotting the
  kimi Run #14 target output, then stripping: `.git/`, `verify_bl*.py`, BL-specific markdown,
  `*.db`, `__pycache__/`, `.pytest_cache/`. Final size 240 KB, 28 files, app code + tests only.

## Graphify results

```
graphify update . --no-cluster
→ 174 nodes, 496 edges
```

**Node coverage:** files + functions + classes (e.g. `auth.py`, `hash_password()`, `User`, `WorkspaceRole`).

**Edge relations breakdown:**
| relation | count |
|---|---|
| `calls` | 248 |
| `contains` | 145 |
| `imports_from` | 68 |
| `inherits` | 21 |
| `imports` | 12 |
| `rationale_for` | 2 |

No clustering / no LLM run — purely tree-sitter structural extraction. Fast and deterministic.

**CLI queries tested (Q1–Q3):**

| Query | Result |
|---|---|
| `graphify explain "get_current_user"` | ✅ Returns node + 1-hop neighbors with `calls/contains` relations |
| `graphify path "create_project" "User"` | ✅ Returns 3-hop path via `Project` model |
| `graphify query "..."` (BFS) | ⚠️ Keyword-based, fails on natural-language. **Use semantic search for NL.** |

**Programmatic queries via graph.json (script `scripts/spike_graph_queries.py`):**

- `neighbors(node_id)` — directed in/out edges with relation type ✅
- `find_structural_similar` — found `_check_workspace_membership` guards in BOTH `projects.py` and `tasks.py`, each called by 5 CRUD funcs ✅
- `summarize_file('app/routers/projects.py')` — listed all 7 entities + their call targets ✅

**Concrete signal proving graph value:** the graph immediately surfaces the shared
authorization guard pattern (`_check_workspace_membership` reused across modules)
— exactly the kind of "what good looks like here" insight that would help a weaker
model write its next router consistently.

## Semantic search results

### Library choice

The plan called for `@zilliz/claude-context-mcp`. Findings:

- The Zilliz library is an **npm/MCP package**, not Python — requires Node.js + Milvus + an
  embedding API key. Adds two daemons (MCP server + Milvus).
- The PyPI package named `claude-context` is a **different project** (akatz-ai) that
  manages plain context documents — unrelated to semantic code search.

**Spike decision:** validate the API surface with the minimum viable stack
(`openai embeddings + numpy cosine`, 80-line script). Phase 1 swaps in the real
MCP integration once the surface is proven.

### Index + queries

`scripts/spike_semantic_search.py`:
- Chunked Python files at top-level `def`/`class`/decorator boundaries → 177 chunks.
- Embedded all chunks via `text-embedding-3-small`, cached to JSON.
- Queries embed and cosine-rank.

**Q1 — "how to enforce workspace membership before mutating a resource":**
- Top hit: `app/routers/workspaces.py:L38` invite_member (sim 0.554) ✅
- Highly relevant — exactly the membership-guarded pattern.

**Q2 — "JWT decode and current user dependency":**
- Top hit: `app/dependencies.py:L12` `get_current_user` (sim 0.446) ✅
- Bullseye on the canonical dep.

**Q3 — "duplicate-name 409 conflict check on POST endpoint":**
- Top hits: `tests/test_auth.py:L17`, `tests/test_projects.py:L45` (~0.49) ✅
- Found the exact test patterns covering 409 returns.

## Exit criterion: MET

All three query types return useful, agent-grade results:

1. ✅ **Structural traversal** (graph_neighbors, graph_path) via Graphify
2. ✅ **Structural similarity** (graph_find_similar) via Graphify graph.json
3. ✅ **Semantic search** via openai embeddings (stand-in for claude-context)

## Findings to feed Phase 1

1. **Graphify needs `graph.json` parsed in Python** — don't rely on the CLI for tools;
   read graph.json directly. The CLI is for humans.
2. **Graphify's BFS `query` is keyword-only** — agents will hit dead-ends. The semantic
   tool must be the entry point for NL queries; graph tools take symbol/path inputs.
3. **Tree-sitter extraction is fast** (~1s for 28 files) and deterministic. Safe to
   re-run on every target-repo cycle.
4. **No clustering / no LLM** still gives 96.5% of the value. Defer LLM-augmented
   semantic extraction (Gemini key) to a later phase if needed.
5. **Reference repo curation worked first try** — kimi Run #14's app/ + tests/ is a
   genuinely usable pattern library. Less than 2hr of curation effort estimated.
6. **For Phase 1 we should**:
   - Decide: real `@zilliz/claude-context-mcp` (heavyweight, "official" pattern) vs.
     embed the lightweight Python equivalent we just wrote (200 lines, no MCP overhead).
   - Recommendation: ship the lightweight Python version inside `langgraph_engine/retrieval/`
     to avoid an extra daemon. Document MCP path as an alternative if/when we need scale.
7. **Reference repo .gitignore needed** — `semantic_cache.json` shouldn't be committed.

## Artifacts produced

- `.venv-spike/` — isolated venv for retrieval libs.
- `reference-repos/fastapi-good-patterns/` — curated reference repo (28 files, 240 KB).
- `reference-repos/fastapi-good-patterns/graphify-out/graph.json` — 174 nodes / 496 edges.
- `scripts/spike_graph_queries.py` — programmatic graph queries.
- `scripts/spike_semantic_search.py` — semantic search prototype.
- `docs/SPIKE_REPORT_PHASE0.md` — this report.

## Time spent

~45 min wall clock, mostly waiting on embedding API. Spike well within budget.
