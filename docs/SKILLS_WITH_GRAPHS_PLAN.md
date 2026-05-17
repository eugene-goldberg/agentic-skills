# Skills + Graph/Semantic Retrieval — Implementation Plan

Branch: `skills_with_graphs`

## 1. Thesis

Today the harness gives each role a `SKILLS.md` doctrine file. The role-LLM operates
on a freshly cloned target repo with only file-level tools (`read_file`,
`list_dir`, `bash`, `edit_file`, `write_file`). The LLM has no structural
or semantic view of the codebase beyond what it manually `read_file`s.

**Add a Codebase Intelligence Layer** that gives the role-LLM agent-controllable
retrieval over a pre-indexed view of the codebase:

- **Graphify** — Tree-sitter + LLM-extracted knowledge graph (entities, relationships, call/import edges).
- **claude-context** — Hybrid semantic + BM25 search via Milvus vector DB, exposed as MCP tools.

These are **complementary**, not redundant:

| Layer | What it answers |
|---|---|
| Graphify | "How does this codebase fit together? What's connected to X?" |
| claude-context | "Where in this codebase does something *like this* exist?" |
| SKILLS.md | "How should I think about this task?" |
| File tools | "Read/edit this specific file." |

## 2. Why bother (signal from our own runs)

- **gpt-5.4 ceiling at ~58–61 QA** — repeatedly fails on architecture / "follows
  project patterns" axes. Plausibly fixable with grounded examples.
- **Kimi run #14** wrote a clean layered FastAPI app — proves the upper-tier
  models *can* produce production-shaped code, but every cycle re-derives the
  same patterns from scratch. Retrieval would let weaker models match this
  consistency.
- **QA discriminates models** — QA work needs to know "what's normal" to flag
  what's abnormal. A graph view of the target repo is exactly that.

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  langgraph_engine (orchestrator)                │
└─────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│  PO node ──┐                                                    │
│  Eng node ─┼──► run_agent (agent_loop.py) ──► bound LLM         │
│  QA node ──┘                                                    │
└─────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│                          tools.py                               │
│  Existing:  read_file, list_dir, bash, edit_file, write_file,   │
│             copy_path                                           │
│  NEW:       graph_query, graph_neighbors, graph_find_similar,   │
│             semantic_search, semantic_find_examples             │
└─────────────────────────────────────────────────────────────────┘
              │                              │
              ▼                              ▼
┌──────────────────────────┐    ┌──────────────────────────────┐
│   Graphify index         │    │  claude-context (MCP)        │
│   (.planning/graph.json) │    │  Milvus vector DB            │
│   read-only, in-process  │    │  HTTP/MCP client             │
└──────────────────────────┘    └──────────────────────────────┘
```

## 4. Reference codebase strategy

The agent works on a **fresh target repo** (`target-repos/lg-graph-test/`),
which starts empty. Indexing an empty repo gives nothing.

Two sources of "what good looks like":

1. **Reference repo** (read-only): a known-good FastAPI/SQLAlchemy app we curate
   as the pattern library. Suggested seed: kimi Run #14's output, hand-cleaned.
   Lives at `reference-repos/fastapi-good-patterns/`.
2. **Live target repo**: re-indexed after each engineering cycle so QA can
   query the actual code under test.

Both are exposed through the same tool surface — the agent learns to use
`reference=true` flag (or sees them as separate tool names) when it wants
exemplars vs. wants to inspect what was just built.

## 5. Phased rollout

### Phase 0 — Spike (1 day)
- Install both libraries side-by-side in `.venv-lg`.
- Run Graphify against `target-repos/lg-graph-test/` (kimi's output) — verify graph.json
  produced, inspect `GRAPH_REPORT.md`.
- Stand up claude-context with local Milvus Lite (no Zilliz Cloud needed for dev).
- Hand-craft a `reference-repos/fastapi-good-patterns/` from the kimi Run #14
  output; strip BL-specific artifacts, keep only `app/`, `tests/`.
- **Exit criterion**: a Python script can issue 3 representative queries
  (semantic search, graph neighbors, find-similar-function) and get sensible
  results.

### Phase 1 — Wire up tools (2 days)
- New module `langgraph_engine/retrieval/`:
  - `graph.py` — wraps Graphify graph.json with query functions.
  - `semantic.py` — claude-context client (HTTP or subprocess MCP).
  - `tools.py` — LangChain `@tool` wrappers.
- Extend `langgraph_engine/tools.py` `build_tools()` to optionally include retrieval
  tools when `RETRIEVAL_ENABLED=1` in env.
- Tool surface:
  ```
  semantic_search(query: str, k: int = 5, source: "reference" | "target" = "reference")
    → list of {file, lines, snippet, score}

  graph_neighbors(symbol: str, depth: int = 1, kinds: list[str] = None)
    → list of related entities + relationship type

  graph_find_similar(symbol: str, k: int = 5)
    → list of structurally/semantically similar symbols

  graph_summary(path: str)
    → high-level summary of a file or module from graph
  ```
- Each tool call is logged to `runs/<role>-.../raw_logs/retrieval.jsonl` for
  later analysis.

### Phase 2 — Skill prompt updates (1 day)
Add a "Codebase Intelligence Layer" section to each role's SKILLS.md. Critical:
**describe when to use the tools, not just that they exist.** Models will ignore
unused tools unless their value is forced.

For `skills/engineer/eng-001-incremental-implementation/SKILLS.md`:

```markdown
## Codebase Intelligence (use BEFORE writing code)

Before implementing any backlog item:
1. `semantic_search(query="<feature name> implementation", source="reference")` —
   find similar patterns in the reference repo. Read at least 2 examples.
2. If editing existing target code: `graph_neighbors(symbol="<module>")` to see
   what currently depends on the area you're touching.
3. After writing the first draft: `graph_find_similar` on your new function;
   if there's a closer template in the reference repo, refactor toward it.

Anti-patterns to avoid:
- Skipping retrieval and inventing a structure from scratch.
- Dumping the entire graph_summary into context — query narrowly.
- Copying reference code verbatim without adapting to current target schema.
```

For `skills/qa/qa-001-test-engineer/SKILLS.md`:

```markdown
## Codebase Intelligence (use during journey design)

When designing test journeys:
1. `graph_neighbors(symbol="<endpoint>")` — discover hidden dependencies
   (auth, db, side-effects) that a test must exercise.
2. `semantic_search(query="<bug class>", source="reference")` — find how
   similar concerns are tested in the reference repo.
3. `graph_summary(path="app/routers/")` — confirm new routes follow project
   layering before approving.
```

For `skills/po/po-001-agile-v-product-owner/SKILLS.md`:

```markdown
## Reference Patterns (use during backlog decomposition)

Before sizing a BL item, `semantic_search(query="<feature>", source="reference")`
to confirm there's a known pattern. If there is, the BL should reference it;
if there isn't, mark the item as "exploratory" and split it smaller.
```

### Phase 3 — Auto-index lifecycle (1 day)
- New CLI flag: `--reference-repo <path>` and `--enable-retrieval`.
- On engine startup:
  - If reference repo provided and not indexed → run Graphify + claude-context
    index. Cache under `.planning/cache/{repo-sha}/`.
- Between BL cycles:
  - Re-index the **target** repo (incremental). Graphify supports incremental
    updates by file mtime; claude-context supports upsert.
- Index outputs are written to `runs/po-lg-...` (PO cycle) and refreshed before
  Eng / QA.

### Phase 4 — A/B evaluation (2 days)
Run the same model twice on the same brief:
- **A:** current harness (no retrieval).
- **B:** retrieval enabled with reference repo.

Models to test:
- `gpt-5.4` (target — known QA ceiling)
- `kimi-k2.6` (baseline — already strong)
- `qwen3-coder-next` (mid-tier)

Metrics:
- Eng score delta per BL
- QA score delta per BL
- Tool-call counts and types (does the agent actually use retrieval?)
- Wall-clock delta (retrieval adds latency)
- Pattern-conformance score (manual review of how closely target output matches
  reference repo's layering)

Hypothesis: gpt-5.4 QA ceiling lifts by 5–10 pts; kimi marginal; qwen mid-gain.

### Phase 5 — Stretch: graph-guided self-critique (optional)
After engineering completes, have the engineer call `graph_summary(path="app/")`
on its own work, then `graph_find_similar(reference)` to compare. Self-correct
before handoff to QA. Cheaper iterations than full QA re-roll.

## 6. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Context bloat from over-retrieval | Default `k=5`, snippet ≤ 40 lines, hard cap on retrieval tool budget per agent run (e.g. 20 calls). |
| Stale reference repo locking us into legacy patterns | Reference repo is curated, versioned. Re-curate after each major project shift. |
| Indexing overhead dominates short cycles | Cache by content hash; only re-index changed files. |
| Agent copies reference verbatim including BL labels | Strip BL-specific markers from reference repo at curation time. |
| MCP server flakiness adds another failure mode | claude-context tools wrap with timeout + degrade-gracefully (return empty result, log warning) so retrieval failures don't crash cycles. |
| Two libraries → two indices to keep in sync | Single `--index` CLI subcommand drives both; record both index SHAs in `runs/.../metadata.yaml`. |

## 7. Open questions

1. **Reference repo selection.** Use kimi Run #14 as-is, or hand-pick patterns
   from multiple sources?
2. **MCP vs. in-process.** claude-context's MCP server adds a hop. Worth wrapping
   the underlying Python client directly to avoid that?
3. **Graph staleness.** Should target re-indexing happen between BL cycles or
   only at QA boundary?
4. **Token cost.** claude-context embeddings + LLM-extracted entities (Graphify)
   both call paid APIs. Need a cost guardrail per run.

## 8. Verdict on the original question

Adding graph + semantic retrieval is **not likely to make the system rigid or
brittle**, provided:

- Retrieval is **agent-controlled** (tools), not auto-injected.
- Skills explicitly govern *when* to query (otherwise tools are ignored or abused).
- Reference repo stays curated and versioned.
- Tool budget caps prevent runaway retrieval loops.

The expected upside is meaningful pattern-conformance gains on weaker models
and an actual mechanism for QA to ground its critique. Worth the implementation
cost.

## 9. Suggested order of operations

1. **Spike (Phase 0)** — confirm Graphify + claude-context work on lg-graph-test.
2. **Curate reference repo** from kimi Run #14 (one-time, ~2 hrs manual).
3. **Wire tools (Phase 1)** behind `RETRIEVAL_ENABLED` flag.
4. **Skill prompt updates (Phase 2)** — small, reversible.
5. **A/B harness (Phase 4)** before declaring a winner.
6. **Auto-index lifecycle (Phase 3)** only after A/B shows ≥5pt QA gain.
7. **Stretch self-critique (Phase 5)** only if cheap.
