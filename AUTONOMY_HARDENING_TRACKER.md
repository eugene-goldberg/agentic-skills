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
| 0-3 | Brownfield target restore | **blocked (operator)** | `~/dev/ai-projects/brownfield-targets/` absent on migrated machine (`/Users/egoldberg`). Prior sprint state (branches `agentic-skills-work*`, Journey 03 findings ledger) recoverable only from old-machine backup; fallback = fresh upstream clone + `RUNBOOK_clean_brownfield_reset.md`. Not needed for Batches 1–4 unit-tested code. |
| 0-4 | Docker / Milvus / Ollama | **partial** | Docker Desktop present, daemon started this session. Milvus stack not yet recreated (needs volumes/compose — old state gone). Ollama not installed (no brew; GUI app install → operator). Needed for live smokes only. |
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
| 4-1 | Scorer verdict/total into `bl.done`; Fail→triage routing | pending | — | fixture Fail scorecard → `score_failed` |
| 4-2 | `revert_bl_span` + operator-gated `POST /revert-bl` | pending | — | revert branch gated green before FF; conflict → structured error |
| 4-3 | Pre-merge QA restructure | **declined (D3)** | — | revisit if reverts >1/sprint over 3 sprints |

---

## Batch 5 — Economics (C5) · Batch 6 — Sprint memory (M1) · Batch 7 — Hygiene (M2–M4)

| ID | Item | Status |
|---|---|---|
| 5-1 | A28 playwright workers (target-side) | blocked on 0-3 |
| 5-2 | A29 PRE-baseline cache | pending |
| 5-3 | Cost aggregation | pending |
| 5-4 | `max_sprint_usd` cap | pending |
| 6-1 | `LESSONS.jsonl` + prompt injection block | pending |
| 6-2 | Sprint-close lesson export | pending |
| 7-1 | Checkout preflight + checked PO commit (A51) | pending |
| 7-2 | Indexer health check + mid-sprint Milvus restart (A53) | pending |
| 7-3 | Agent env allowlist (A52) | pending |

---

## End-state test (plan §9)

- [ ] Live sprint: detached submit → disconnect → planted flaky BL defers with dependent → completes-with-deferrals under budget → reconnect replays history → closure_check 0 violations
  *(blocked on 0-3/0-4 target + Milvus/Ollama restore)*

## Issues log

| Date | Batch | Issue | Resolution |
|---|---|---|---|
| 2026-08-15 | 0 | Machine migration (`/Users/eugenegoldberg` → `/Users/egoldberg`) wiped venv, Docker state, Ollama, targets, memory symlink | 0-1/0-2 restored; 0-3/0-4 partially blocked on operator (backup or fresh-target decision) |

## Sign-off

- [ ] Batch 0 — architect note: 0-1/0-2/0-5 done; 0-3/0-4 operator-blocked items listed above
- [ ] Batch 1 —
- [ ] Batch 2 —
- [ ] Batch 3 —
- [ ] Batch 4 —
- [ ] Batches 5–7 —
