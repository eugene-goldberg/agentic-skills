# Autonomy Hardening — Implementation Tracker

> Live status of `AUTONOMY_HARDENING_PLAN.md`. Update only this file as
> work lands. Plan authorized 2026-08-15 (decisions D1–D6 recorded in
> the plan header). Branch: `autonomy-hardening` off `architect-prereqs`
> @ `8745331`.

## Status legend

`pending` · `in_progress` · `done` · `blocked` · `deferred`

---

## Batch 0 — Preconditions

| ID | Item | Status | Notes |
|---|---|---|---|
| 0-1 | Memory symlink restored | done | `setup_memory_symlink.sh` → `~/.claude/projects/<enc>/memory` links to repo `.claude/memory` (2026-08-15) |
| 0-2 | venv + full suite green | done | uv-managed Python 3.12.12; `pytest tests/` → **208/208** (matches 2026-06-02 handoff posture) |
| 0-3 | Brownfield target restore | **done 2026-08-16 (C-0)** | Fresh upstream clone @ `75b4026` (prior sprint state unrecoverable — Journey 03 finding gone; C-5 re-creates on a new sprint). Branch `agentic-skills-work` with 9 harness commits: config, gate overlay, re-authored `regression_gate.sh` (A39a/A32/A28 contract), gitignore hygiene (A35). **Gate live-verified GREEN end-to-end**: 5 sentinels + 60 pytest + 62 playwright (4 workers, 11s), exit 0, zero leftover containers. Seven environment/template drifts found+fixed during verification: FASTAPI_ENV validator gate, no macOS coreutils `timeout` (perl-alarm shim), uv-image pip, `backend/tests` relocation, tests excluded from prod image (ro mount), pytest↔e2e DB-state contamination (phase reset). |
| 0-4 | Docker / Milvus / Ollama | **done 2026-08-16 (C-0)** | Milvus 3-container stack healthy (:19530 + /healthz OK); standalone ollama CLI at `~/.local/bin` serving bge-m3 (1024-dim probe verified); `webapp/.env` recreated; `bridge.js` regenerated from semantic.py via AST + npm deps installed; graphify in venv; end-to-end bridge index of target: **164 files → 1305 chunks**. PF-1..10 ALL GREEN (uvicorn + 4 A48 fixes loaded; suite 291/291; Docker.raw cap on this machine is 926G sparse — the old 60G ceiling is gone). |
| 0-5 | Ledger entries A49–A57 | done | Filed in `DESIGN_SHORTCOMINGS.md` with class + invariant back-refs, each cross-referencing its plan batch |

---

## Batch 1 — Detached runs (C1 / A34)

| ID | Item | Status | Commit | Verification |
|---|---|---|---|---|
| 1-1 | `run_registry.py` + background execution + `detached` flag + `/abort` | done | (this commit) | `test_run_registry.py` (8): disconnect-survival, abort-fires-finallys, replay, multi-consumer, never-started-task finalization |
| 1-2 | `GET /api/runs/{id}/events` replay+tail; `GET /api/runs/{id}` status | done | (this commit) | `test_runs_endpoints.py` (7): replay, Last-Event-ID resume, 404/409 |
| 1-3 | Startup orphan surfacing (`GET /api/runs?status=orphaned`) | done | (this commit) | `run_state.list_active()` + startup log + endpoint filter; D5: surfaced only |

**Batch 1 gate:**
- [x] Integration test: kill SSE consumer mid-run → run completes; events.jsonl carries `sprint_complete` (`test_consumer_disconnect_does_not_stop_run`, `test_detached_run_brief_returns_202_and_completes`)
- [x] `POST /abort` → task cancelled, cleanup finallys fire (`test_abort_cancels_and_generator_finally_fires`)
- [x] `detached=false` (default) behavior preserved: same data-only SSE frames, no id: lines, no terminal event, disconnect still aborts (`test_inline_*` ×2)
- [x] Full suite green — **223/223** (was 208)
- [ ] Live smoke (`curl --max-time 5` on a real 1-BL sprint) — blocked on 0-3/0-4 environment restore

---

## Batch 2 — Signal repair (C4)

| ID | Item | Status | Commit | Verification |
|---|---|---|---|---|
| 2-1 | A39a/b gate parser: `build_fail` kind, `gate_failure_class`, regressed⇒non-empty invariant, class-aware fix prompts, retry-predicate extension | done | (this commit) | `test_a39_gate_classifier.py` (9) incl. the 3 real-incident shapes; decision tree extracted to pure `classify_gate_outcome()`; bonus: ran-nothing post now `inconclusive`, never mass-regressed |
| 2-2 | A44 wiring: api_error = infra-retry (backoff, no budget burn) | done | (this commit) | `test_a44_api_error_retry.py` (4); all 8 role-flow spawn sites route through `_stream_role_attempt` (source-contract test) |
| 2-3 | A45: in-flight tool suspends idle clock; R14.4 SKILLS (engineer+QA) | done | (this commit) | `test_a45_idle_busy.py` (3) against a fake CLI: busy survives idle silence; genuine silence still killed; wall bounds busy. Wall timeout now enforced cumulatively (was per-readline) |
| 2-4 | Small defects A54 / A55 / A56 / A57 | done | (this commit) | `test_batch2_small_defects.py` (7) |

**Batch 2 gate:**
- [x] Property test: `kind=regressed` ⇒ `regressions+new_failures ≠ []` (`test_regressed_invariant_holds_across_shapes`)
- [x] Full suite green — **246/246**

---

## Batch 3 — Dependency gating + triage v1 (C2)

| ID | Item | Status | Commit | Verification |
|---|---|---|---|---|
| 3-1 | Dep-gated scheduling (`deferred_dep`, worst-wins sprint label) | done | (this commit) | planted-failure synthetic sprint: failed BL-0001 → BL-0002 `deferred_dep` (engineer never spawned), BL-0003 merges, `sprint_label=complete_with_deferrals` |
| 3-2 | Triage SKILLS.md + `_triage_flow` + R16 (enforcement + test) | done | (this commit) | `test_batch3_dep_gating_triage.py` (12): RETRY_REWRITE = exactly 1 guided retry with guidance injected; DEFER/ESCALATE record + continue; crash→DEFER fallback; enum-constrained validator; QA-context coercion; flag-OFF default verified. R16 added to CLAUDE.md R-rules table (I-2). Engineer-failure + QA-merge-failure hooks both wired |
| 3-3 | D1 default flip | deferred | — | after one clean triage-ON calibration sprint (blocked on 0-3/0-4 environment) |

---

## Batch 4 — Quality teeth (C3 / A50)

| ID | Item | Status | Commit | Verification |
|---|---|---|---|---|
| 4-1 | Scorer verdict/total into `bl.done`; Fail→triage routing | done | (this commit) | `extract_scorecard_summary` (reuses R7 parsers); Fail verdict → outcome `merged_score_failed` + `score_failed` event + scorer-context triage (DEFER/ESCALATE, R16); `bl.done` carries verdict+total |
| 4-2 | `revert_bl_span` + operator-gated `POST /revert-bl` | done | (this commit) | forward-revert only (R13 symmetry); conflict → structured error, agent_branch untouched (asserted by test); endpoint requires confirm=true, gates revert branch before FF; `test_batch4_score_teeth_revert.py` (8) |
| 4-3 | Pre-merge QA restructure | **declined (D3)** | — | revisit if reverts >1/sprint over 3 sprints |

---

## Batch 5 — Economics (C5) · Batch 6 — Sprint memory (M1) · Batch 7 — Hygiene (M2–M4)

| ID | Item | Status |
|---|---|---|
| 5-1 | A28 playwright workers (target-side) | done — baked into the re-authored gate (`--workers=4 --retries=1`); 62 e2e in 11s |
| 5-2 | A29 PRE-baseline cache | done — SHA+cmd-keyed, TTL 24h, infra-poisoned baselines never cached, `pre_cache_hit` auditable in gate events; second gate runs POST only |
| 5-3 | Cost aggregation | done — result-frame `total_cost_usd` → `bl.done cost_usd` + `sprint_complete total_cost_usd`/`cost_by_role` (all 7 passthrough sites) |
| 5-4 | `max_sprint_usd` cap | done — checked between BLs; over-cap → `deferred_budget` + `budget_exhausted` event + worst-wins label |
| 6-1 | `LESSONS.jsonl` + prompt injection block | done — resolved doctrine/gate retries append (engineer + qa/scorer sites); last 10 injected into engineer/QA task sections; empty file = zero prompt noise |
| 6-2 | Sprint-close lesson export | done — `sprint_complete` carries lessons_count/path; LESSONS.jsonl copied into `traces_archive/<run_id>/`; doctrine-meta prompt points at it when present |
| 7-1 | Checkout preflight + checked PO commit (A51) | done — PF-6 in code (wrong branch/dirty tracked → abort pre-spawn; lenient when agent_branch ref absent); PO commit verified via post-commit status of artifact paths; hook-blocked commit → structured `po_commit ok=false` + abort with honest reason |
| 7-2 | Indexer health check + mid-sprint Milvus restart (A53) | done — `_run_indexers_checked` (explicit ok=False fails; one `docker start milvus-standalone` + retry); initial-index failure aborts pre-spawn; mid-sprint reindex failure → loud `indexing_degraded` (+abort under stop_on_failure) |
| 7-3 | Agent env allowlist (A52) | done — `_agent_env()`: shell basics + git identity + claude auth (CLAUDE_/ANTHROPIC_/AWS_/GOOGLE_/VERTEX_) + proxies; AZURE_OPENAI_*/OPENAI_*/MILVUS_* excluded (MCP server config env unaffected); `AGENT_ENV_ALLOWLIST` extension + `AGENT_ENV_PASSTHROUGH_ALL=1` escape hatch; HARNESS.md §11 trust model |

---

## Calibration ladder (plan §9b)

### C-0 — environment restore ✅ 2026-08-16
PF-1..11 green; gate live-verified (5 sentinels + 60 pytest + 62 playwright, exit 0).

### C-1 — mechanics smokes ✅ 2026-08-16
Run `run-20260816T163240Z-55d69e` (1 BL, detached, ~50 min):

| Check | Result |
|---|---|
| Detached submit → 202 immediate | ✅ |
| Viewer disconnect mid-run (`curl --max-time 5`) | ✅ run continued to completion (verified on the earlier attempt) |
| `POST /abort` + cleanup contract | ✅ (verified on the aborted attempt: exit 143, 0 worktrees, lock released, state→done/) — **surfaced A58** |
| Event replay / `Last-Event-ID` resume | ✅ 820/820 replay; `Last-Event-ID: 815`→4; `from_index=818`→2 |
| Outcome | ✅ `merged_full`, scorer **Pass 93/100** |
| Gates | ✅ 2/2 green (engineer 75 passed, QA 88 passed — QA added 13 tests, 0 regressions) |
| Merges | ✅ 2 FF (`6709786` engineer, `a3d65b1` QA) |
| Cost aggregation (5-3) | ✅ **$10.12** total — po $1.43, engineer $2.28, qa $3.22, scorer $3.19; `bl.done cost_usd` $8.69 |
| Sprint memory (6-1) | ✅ `lessons_count=1` (scorer doctrine retry recorded) |
| Closure | ✅ 0 violations |
| Retrieval grounding | ✅ 6/5/5/8 calls across po/engineer/qa/scorer — **validates the A59 fix** |

**A59 (critical) found and fixed by this rung**: the retrieval MCP server
could not start at all, so the *first* C-1 attempt ran every agent with
ZERO retrieval tools; only Tier 1.5's `pre_grounding_violation` caught it.
That attempt's result is void as grounding evidence — this row records the
re-run after the fix.

**Correction — A29 (5-2) value was overstated.** Both gates in this run
show `pre_cache_hit=False`, and that is CORRECT: `target_ref` (the agent
branch) advances after each merge, so a QA gate never shares the
engineer gate's baseline SHA. The cache therefore hits only where the
baseline is genuinely unchanged — **gate retries within a role** (R10.2)
and post-rebase re-gates — not "~50% of gate wall-time after the first
BL" as the Batch-5 commit claimed. Real but narrower. Follow-up idea
(unbuilt): let a QA gate reuse the engineer gate's POST result as its
PRE baseline, since the just-merged, fully-tested tree *is* the new
baseline.

### C-2 — triage calibration sprint ⬜ next (operator reviews every triage.md)

## End-state test (plan §9)

- [ ] Live sprint: detached submit → disconnect → planted flaky BL defers with dependent → completes-with-deferrals under budget → reconnect replays history → closure_check 0 violations
  *(blocked on 0-3/0-4 target + Milvus/Ollama restore)*

## Issues log

| Date | Batch | Issue | Resolution |
|---|---|---|---|
| 2026-08-15 | 0 | Machine migration (`/Users/eugenegoldberg` → `/Users/egoldberg`) wiped venv, Docker state, Ollama, targets, memory symlink | 0-1/0-2 restored; 0-3/0-4 partially blocked on operator (backup or fresh-target decision) |

## Sign-off

- [x] Batch 0 — architect (Fable 5), 2026-08-15: 0-1/0-2/0-5 done; 0-3/0-4 operator-blocked items listed above
- [x] Batch 1 — architect, 2026-08-15: `f333e20`; suite 223/223
- [x] Batch 2 — architect, 2026-08-15: `1868229`; suite 246/246
- [x] Batch 3 — architect, 2026-08-15: `9728f0a`; suite 258/258
- [x] Batch 4 — architect, 2026-08-15: `f2ab112`; suite 266/266
- [x] Batches 5–7 — architect, 2026-08-16: `f5ab92c` (5), `9e33cfc` (6), + this commit (7); suite 291/291. 5-1 remains blocked on target restore.
- [ ] Live smokes + calibration sprints — **operator-blocked on 0-3/0-4 environment restore**
- [ ] Merge-back to `architect-prereqs` (or main) — operator's call after review
