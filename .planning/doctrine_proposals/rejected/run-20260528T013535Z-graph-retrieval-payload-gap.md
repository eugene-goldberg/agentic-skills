# Proposal: Log graph_* retrieval arguments + result shape in `retrieval.jsonl`

**Sprint:** run-20260528T013535Z-ed1a60 (documents-3 validation sprint, 3 BLs)
**Topic:** graph-retrieval-payload-gap
**Invariant:** I-2 (doctrine contract — every R-rule maps to enforceable signal) with I-3 adjacency (closure / observability)
**Class:** observability-gap
**Direction:** tighten
**Evidence count:** 10 (well above the ≥3 floor for tightening)

## Summary

The streaming-side and post-validation enforcement of R9 (≥1 `graph_*` call) and R5 (≥3 grounded calls) both count entries in `retrieval.jsonl` by `tool` name. In every trace of this sprint, `semantic_search` records `query` + `source` + `n_hits` — substance is auditable. By contrast, every `graph_neighbors`, `graph_summary`, and `graph_find_similar` entry records ONLY `{ts, tool}` — no node id, no center, no result count, no error. The meta-agent and framework-reviewer cannot determine from a sealed trace whether an R9-satisfying graph call returned 12 neighbors or 0. R9 is currently a **shape-satisfied** rule, not a **substance-satisfied** one; an agent invoking `graph_neighbors(node="nonexistent")` would still pass.

## Evidence

All citations open the same archive directory:
`webapp/backend/traces_archive/run-20260528T013535Z-ed1a60/`.

Each cite is `<trace_dir>/retrieval.jsonl, line N, observed_value`.

**Graph calls with no observable payload (10):**

1. `20260528T013703Z-po-b203aafe3ec1/retrieval.jsonl`, lines 9–10, two `graph_summary` entries: `{"tool":"graph_summary","ts":...}` — no center, no n_results.
2. `20260528T014825Z-engineer-BL-0001-5bed032923c2/retrieval.jsonl`, line 3, `graph_neighbors` — no node, no neighbor count.
3. `20260528T014825Z-engineer-BL-0001-5bed032923c2/retrieval.jsonl`, line 4, `graph_summary` — no payload.
4. `20260528T021042Z-qa-BL-0001-dd838612f3d0/retrieval.jsonl`, line 3, `graph_neighbors` — no payload.
5. `20260528T021042Z-qa-BL-0001-dd838612f3d0/retrieval.jsonl`, line 4, `graph_summary` — no payload.
6. `20260528T023055Z-scorer-BL-0001-d6b0d576eda6/retrieval.jsonl`, line 3, `graph_neighbors` — no payload.
7. `20260528T023055Z-scorer-BL-0001-d6b0d576eda6/retrieval.jsonl`, line 4, `graph_find_similar` — no payload.
8. `20260528T023431Z-engineer-BL-0002-619e056450f0/retrieval.jsonl`, line 4, `graph_summary` — no payload.
9. `20260528T025546Z-qa-BL-0002-6016828b5d06/retrieval.jsonl`, lines 3, 5, 6 — three graph calls, no payload on any.
10. `20260528T040610Z-scorer-BL-0003-77726e82e97d/retrieval.jsonl`, lines 3–4, `graph_neighbors` + `graph_find_similar`, no payload.

**Contrast (semantic_search records substance):**

- `20260528T013703Z-po-b203aafe3ec1/retrieval.jsonl`, line 2: `{"tool":"semantic_search","query":"SQLModel database model definition Item User","source":"target","n_hits":4}`.
- `20260528T034309Z-qa-BL-0003-b99716846aea/retrieval.jsonl`, line 4: `{"tool":"semantic_search","query":"conftest db fixture teardown order","source":"target","n_hits":3}`.

The asymmetry is the finding: one tool family is auditable, the other is not.

**Trigger frequency (R9 enforcement was satisfied by call count in every BL):**

```json
{
  "graph_neighbors":  {"calls": 8,  "with_n_results": 0},
  "graph_summary":    {"calls": 6,  "with_n_results": 0},
  "graph_find_similar": {"calls": 4, "with_n_results": 0},
  "semantic_search":  {"calls": 16, "with_n_hits": 16},
  "target_status":    {"calls": 10, "with_n_source": 10}
}
```

(Derived by reading every `retrieval.jsonl` under the archive; reproducible by parsing the file list above.)

## Proposed change

Extend `retrieval.jsonl` schema for graph tools to match the substance-recording precedent of `semantic_search` + `target_status`. Concrete fields per tool:

| tool | required new fields |
|---|---|
| `graph_neighbors` | `node` (the queried node-id or path), `n_neighbors` (int), `direction` (in/out/both) |
| `graph_summary`   | `scope` (path or node spec, "" if global), `n_nodes`, `n_edges` |
| `graph_find_similar` | `query` (text or node-id), `n_hits`, `top_score` (float, optional) |

All four fields must be **non-fabricated**: pulled from the actual MCP tool response. On error, log `{"error": "<class>: <msg>", "n_hits": 0}` rather than dropping the entry. The hook lives wherever `retrieval.jsonl` is written today (a single point in the MCP bridge — `langgraph_engine/retrieval/...` or its webapp analog).

Doctrine layer change (lands in the *same* commit as the schema extension):

- `doctrine_validator.py` gains a `_check_r9_substance(retrieval_path)` helper that, for each `graph_*` entry, asserts `n_neighbors >= 1` (or `n_nodes >= 1` for summary, or `n_hits >= 1` for find_similar). If every graph call in a trace returned zero, R9 is **shape-passed but substance-failed** → emit `kind="incomplete"` with reason `"R9 graph-grounding: <N> graph_* calls but all returned 0 results"`.
- This is additive to A8's call-count check, not a replacement.

R9 in `CLAUDE.md` is updated from "≥1 graph_* tool call required per role" to "≥1 graph_* tool call required per role, **and at least one such call must return ≥1 neighbor/node/hit**."

## Risk

1. **Schema migration breaks readers of older `retrieval.jsonl` files** (Phase-0 traces, sprints 1–4). Tools that grep for `"tool": "graph_neighbors"` keep working; tools that destructure the JSON might not.
2. **n_neighbors / n_nodes might be unbounded** — `graph_summary` of a 10k-file repo could return 50k nodes, ballooning trace size. The log entry should record the count, not the payload.
3. **R9 substance check could create a new false-negative class** if a legitimate query genuinely has no neighbors (e.g., a leaf file with no graph edges). Need a small-graph escape hatch.
4. **Doctrine-meta itself depends on this schema going forward** — schema change must be backward-readable so historical sprints stay analyzable.

## Mitigations

1. **Make every new field nullable.** Readers that only care about `tool` + `ts` are unaffected. Old traces continue to be valid (missing fields read as `None`); the doctrine_meta-agent's per-rule frequency table treats `n_hits == None` as "unknown, do not count toward substance verdict."
2. **Log only counts, not payloads.** Never serialize the neighbor list into the JSONL — that's `claude-context`'s job, not the audit log's.
3. **R9 substance check exempts a call whose `node` argument is a path that does not exist in the graph index** (record this as `error: "node not found"`; don't count it against the agent — but DO require ≥1 other graph call that DID return results). The escape hatch is "no nodes at all in this BL's scope," which is rare in brownfield work and observable.
4. **doctrine-meta-agent SKILLS.md update**: explicitly handle `n_hits is None` and `n_results is None` cases as "schema pre-dates substance logging" — do not propose tightening based on pre-schema traces.

## Test

Synthetic harness invocation:

```bash
# In webapp/backend/, with a recently-archived run:
python -c "
from app.services.doctrine_validator import _check_r9_substance
from pathlib import Path
ok, missing = _check_r9_substance(Path('traces_archive/run-XXX/<some_engineer_trace>/retrieval.jsonl'))
print(ok, missing)
"
```

Three test fixtures:

1. **Substance-passing trace**: synthetic `retrieval.jsonl` with one `graph_neighbors` entry `{n_neighbors: 5}`. Expect `ok=True, missing=[]`.
2. **Substance-failing trace**: one `graph_neighbors` entry `{n_neighbors: 0}`, no other graph calls. Expect `ok=False, missing=["R9 graph-grounding: ..."]`.
3. **Pre-schema trace**: one `graph_neighbors` entry with no `n_neighbors` key (legacy). Expect `ok=True` with a warning log (do not fail on legacy shape).

All three must pass before this proposal is considered shipped.

## Rollback

The schema additions are additive — drop the validator helper and the prompt clause in `CLAUDE.md` to fully roll back. The `retrieval.jsonl` writer continues to emit the new fields harmlessly; readers that don't care continue to ignore them. No history rewrite needed.

Commit-revert is the operator path; the proposal lands as one commit on a feature branch and stays gated behind a flag (`enforce_r9_substance=False` initially) until two consecutive sprints show <5% false-positive rate, at which point the operator flips it to `True` and removes the gate in a follow-up commit.
