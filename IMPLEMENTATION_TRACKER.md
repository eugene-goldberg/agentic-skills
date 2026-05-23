# Agentic Skills — Implementation Tracker

> **Live status of the work described in `IMPLEMENTATION_PLAN.md`.**
> Update this file as each item lands.
>
> **Plan version:** 2026-05-23 v1 (Decision (a) from DESIGN_SHORTCOMINGS.md)
> **Sprint state at tracker start:** Sprint 3 aborted at BL-0005 merge (operator-commit/agent-worktree race). v3 HEAD: `b46b4d6`. Backend uvicorn alive (PID 34768). No live orchestrator/agents.

---

## Status legend

- `pending` — not started, blocked only by ordering
- `in_progress` — actively being implemented
- `done` — landed + verified + committed
- `blocked` — needs a decision or upstream fix
- `deferred` — intentionally out-of-scope per plan §10
- `reverted` — landed then rolled back (note reason)

---

## Pre-flight gate

| Check | Status | Notes |
|---|---|---|
| No orchestrator running | ☑ | verified 2026-05-23 12:14 |
| No live agent claude subprocesses | ☑ | filter patched to exclude claude-mem daemon's children by PPID (commit `f1bb6b1`); 0 strays after patch |
| Uvicorn alive | ☑ | PID 44107 after restart for Batch 1 verification |
| No leftover worktrees | ☑ | 1 stale worktree `e9e0baedae01` + 18 `agent/*` branches cleaned |
| Milvus healthy | ☑ | Up 5h |
| v3 HEAD known | ☑ | `b46b4d6` ✓ |
| Backend imports clean baseline | ☑ | |

---

## Batch 1 — Pure observability (zero behavior change)

**Branch:** `sprint-2-orchestrator`
**Commit style:** atomic per item (operator direction); 4 commits land in this batch.

| ID | Item | Status | Commit | Verification | Notes |
|---|---|---|---|---|---|
| B18 | Logs out of `/tmp/` → `webapp/backend/logs/orchestrator/` + scripts in repo | done | `7919029` | py + sh syntax OK; symlinks at /tmp/ for habit-compat | scripts moved to `webapp/backend/scripts/`; new env-knob overrides; gitignore: `backend/logs/orchestrator/*` |
| A6 | Reader script dumps full event JSON on failure | done | `5e652ce` | failure-shape detection covers `aborted`, `_error` suffix, and `merge_to_target/regression_gate` with `ok=false` | bounded by 1500-char JSON dump |
| B14 | `harness_sha` field in trace `meta.json` | done | `7fce71b` | meta.json contains harness_sha matching `git rev-parse HEAD` ✓ | resolved once per process; 1s subprocess timeout; defaults to "unknown" |
| B15 | Auto-archive traces on `sprint_complete` AND `aborted` | done | `01bb5b4` | synthetic 3-dir smoke moves only finished+after-start trace | per operator direction #3 — aborted runs also archive; `run_id` emitted in `orchestrator.start` |

**Batch 1 gate verification:**
- [x] Import smoke OK (`from app.services import orchestrator, claude_agent, traces`)
- [x] uvicorn restart OK (new PID 44107 listening :8000)
- [x] `/openapi.json` returns 200 with 15 paths including `/run-brief`
- [x] B14 unit smoke: TraceWriter created in tmpdir → meta.harness_sha matches `git rev-parse HEAD`
- [x] B15 unit smoke: only finished+after-start trace archived (old/finished + new/active untouched)
- [ ] Real end-to-end 30s `/decompose-brief` smoke (deferred — orchestrator path tested via unit smoke; full E2E reserved for post-Batch-3 when state-honesty is in)

---

## Batch 2 — Subprocess hygiene

**Branch:** `sprint-2-orchestrator`
**Commit style:** atomic per item.

| ID | Item | Status | Commit | Verification | Notes |
|---|---|---|---|---|---|
| B1 | `start_new_session=True` + `_kill_pgroup` helper; 4 `proc.kill()` sites converted; inner-finally cancellation-aware | done | `b0b3914` | spawned 2-child tree in own pgroup → `_kill_pgroup` reaped all 3 in <0.5s | exit yield wrapped in `try/except GeneratorExit` per PEP 525 |
| B5 | `idle_timeout: int \| None = 600` param; readline wait = `min(idle, wall)`; emits `kind=idle_timeout` on fire | done | `ed80bec` | param default 600 ✓; effective_timeout math correct at None / idle<wall / idle>wall boundaries | backward-compat: `idle_timeout=None` = prior behavior |

**Batch 2 gate verification:**
- [x] Import smoke OK
- [x] B1 pgroup mechanism smoke (helper reaps descendants)
- [x] B5 parameter wired through; math verified
- [x] uvicorn restart OK (new PID 94645, 15 endpoints)
- [ ] Real disconnect test against running claude subprocess (deferred — requires live brief run; orchestrator path tested in Batch 3 will exercise B1 naturally)

---

## Batch 3 — Orchestrator state honesty

**Branch:** `sprint-2-orchestrator`
**Commit style:** atomic per item.

| ID | Item | Status | Commit | Verification | Notes |
|---|---|---|---|---|---|
| A2 | `qa_doctrine_failed` event + `doctrine_summary` pass-through + `stop_on_qa_doctrine_failure` flag | done | `6a1a40c` | OpenAPI schema shows new field with default=False | opt-in flag preserves default behavior |
| A5 | `bl.done` outcome reflects worst role: `merged_full` / `merged_no_qa` / `merged_no_score` | done | `4fcd430` | 6-case truth matrix verified | UI mapping comes in Batch 7 (B4) |
| B12 | `_qa_commit_landed` git-log cross-check before R11 no_op short-circuit | done | `4305870` | 4-case smoke (no-commit/qa-commit/historical/bogus-branch) | reasons distinguish file-missing vs file-uncommitted |

**Batch 3 gate verification:**
- [x] Import smoke OK
- [x] A2 OpenAPI surface: `stop_on_qa_doctrine_failure` present, default `false`
- [x] A5 outcome-matrix math verified across 6 cases
- [x] B12 4-case functional smoke in synthetic git repo
- [x] uvicorn restart OK (new PID 97432, 15 endpoints)

---

## Batch 4 — Concurrency lock + idempotency

**Branch:** `sprint-2-orchestrator`
**Commit style:** atomic per item.

| ID | Item | Status | Commit | Verification | Notes |
|---|---|---|---|---|---|
| B2 | Per-repo `asyncio.Lock`; 409 on concurrent; WEB_CONCURRENCY warning | done | `fe0a83b` | unit: lock idempotent per repo; 409 detail carries run_id+started_at+current_bl; release clean | single-worker assumption stated in comment |
| B9 | sha256 brief_hash → `duplicate-brief` 409 vs B2's `run-in-progress` 409 | done | `4960c17` | unit: same brief → duplicate-brief; different brief while running → run-in-progress; hash determinism + 3-input sensitivity | bundled in plan §5; committed atomically |

**Batch 4 gate verification:**
- [x] Import smoke OK
- [x] B2 unit test (lock + 409 detail shape)
- [x] B9 unit test (duplicate vs in-progress error distinction; hash properties)
- [x] uvicorn restart OK (15 endpoints intact)
- [ ] Real two-curl race deferred — would require live orchestrator burning API tokens; unit coverage validates the only logic that changed

---

## Batch 5 — Disk-persisted state

**Branch:** `sprint-2-orchestrator`
**Depends on:** Batch 4 (B2 lock prevents concurrent state writes)

| ID | Item | Status | Commit | Verification | Notes |
|---|---|---|---|---|---|
| A7 | `run_state.py` module + 5 checkpoint sites + orphan-detection 409 in router | done | `a0deed3` | round-trip write/find/update/terminate; hash+repo filter; atomic tmp; idempotent mark_terminated; router 409 shape | run_id now flows router→orchestrator; reuses orphan's run_id on `skip_po=true` |

**Batch 5 gate verification:**
- [x] Import smoke OK (`run_state`, `orchestrator`, `projects`)
- [x] State file round-trip (write → find_active → mark_terminated → done/ move)
- [x] Atomic write: no `.json.tmp` leftovers
- [x] Hash/repo mismatch correctly returns None from find_active
- [x] Router 409 shape verified: `orphaned-run-detected` with completed_bls + current_bl + hint
- [x] uvicorn restart OK (15 endpoints intact)
- [ ] Real kill-restart-mid-sprint deferred to next live run

**Out of scope (deferred per A7 commit):**
- Git-history validation of `current_bl` against agent_branch HEAD
- DELETE endpoint to discard a state file (operator rm's manually)
- Automatic force_resume override (current design: explicit `skip_po=true` to opt in)

---

## Batch 6 — Recovery automations

**Branch:** `sprint-2-orchestrator`
**Commit style:** atomic per item.
**Depends on:** Batch 3 (outcome labels exist)

| ID | Item | Status | Commit | Verification | Notes |
|---|---|---|---|---|---|
| A1 | `_rebase_in_worktree` helper + non-FF auto-rebase in both engineer and qa/scorer flows + post-rebase gate re-run | done | `ad7a335` | synthetic 3-commit race: rebase succeeds, main becomes ancestor; conflict case: --abort cleans worktree | new event phases: merge_rebase_attempt, merge_rebase_succeeded, merge_rebase_failed; new merge kind `non_ff_gate_failed_post_rebase` |
| A3 | `_try_milvus_restart` + 60s cooldown wired into `_preflight_retrieval` | done | `cbc2966` | live `docker stop milvus-standalone` → auto-restart returns ok=True in 1.4s; cooldown gate refuses second restart | env knob `MILVUS_CONTAINER_NAME` overrides default `milvus-standalone` |
| A4 | `start_bl` request field + `bl.skipped` events + RECOVERY.md playbook | done | `20c5476` | OpenAPI shows `start_bl: str \| null`; new top-level RECOVERY.md doc | covers crash-restart, score-only, start-from-BL, conflict, Milvus paths |

**Batch 6 gate verification:**
- [x] Import smoke OK
- [x] A1 rebase helper smoke: success + conflict+abort cases
- [x] A3 live Milvus restart test (took 1.4s; cooldown gates active)
- [x] A4 OpenAPI surface: `start_bl` present with null default
- [x] uvicorn restart OK (PID 6506, 15 endpoints intact)
- [ ] Real non-FF auto-rebase on the brownfield target deferred — would require an artificial operator-commit race; helper-level + path-integration coverage in place

---

## Batch 7 — UI surface for new events

**Branch:** `sprint-2-orchestrator`
**Target commit message:** `ui: AppV2 surfaces partial_resume + qa_doctrine_failed + merge error (B4+B17)`

| ID | Item | Status | Commit | Verification | Notes |
|---|---|---|---|---|---|
| B4 | AppV2 handlers for new events + outcome labels | pending | — | `npm run build` + visual smoke | |
| B17 | UI Stop kills server-side | done-by-B1 | — | follows automatically once B1 lands | subsumed |

**Batch 7 gate verification:**
- [ ] `npm run build` OK
- [ ] Visual smoke at `localhost:8000`

---

## Batch 8 — Graphify cache refactor (QUARANTINE)

**Branch:** `sprint-2-orchestrator-b3-graphify-cache` (separate from sprint-2-orchestrator)
**Target commit message:** `retrieval: graphify writes to shared content-addressed cache (B3 — closes B7, B8 implicit)`

| ID | Item | Status | Commit | Verification | Notes |
|---|---|---|---|---|---|
| B3 | graphify writes to `~/.cache/agentic-skills/graphify/...` | pending | — | full quarantine test plan in PLAN §9 | **HIGH risk; isolated branch** |
| B7 | `.gitignore` preflight | closed-by-B3 | — | moot once B3 lands | |
| B8 | Cache reuse across worktrees | partial-by-B3 | — | full caching is later sprint | only the path move lands here |

**Batch 8 gate verification:**
- [ ] On quarantine branch: tiny `/decompose-brief` succeeds
- [ ] Cache dir created at expected location
- [ ] Target working tree has no `graphify-out/`
- [ ] Agent's `n_retrieval_calls > 0`
- [ ] QA `git add -A` does NOT include cache
- [ ] Quarantine branch merged back to `sprint-2-orchestrator`

---

## Deferred items (per PLAN §10)

| ID | Item | Status | Reason |
|---|---|---|---|
| B6 | Engineer re-spawn on QA findings | deferred | State-machine change, own scoping needed |
| B8 (cache reuse) | Cache reuse logic beyond path move | deferred | Performance optimization, not correctness |
| B10 | Cost telemetry aggregation | deferred | ABL-0013, own sprint |
| B11 | Parallel BL execution | deferred | ABL-0011, own sprint |
| B13 | Triage agent | deferred | ABL-0002, own sprint |

---

## Issues log

(Append entries here as they're encountered during implementation.)

| Date | Batch | Issue | Resolution |
|---|---|---|---|
| 2026-05-23 | — | Plan + tracker created | Awaiting operator go-ahead for Batch 1 |
| 2026-05-23 | pre-1 | Pre-flight check #2 false-positived: claude-mem daemon's child `claude` processes don't contain "claude-mem" in their own argv | Patched filter to exclude by parent-PID argv match; committed as `f1bb6b1` |
| 2026-05-23 | pre-1 | Pre-flight check #4 failed: 1 stale worktree (`e9e0baedae01` at v3 HEAD, clean) + 18 orphan `agent/*` branches in target | Removed with `git worktree remove --force` + `git branch -D`; operator approved |
| 2026-05-23 | 1 | B15 initially yielded from finally clause | Removed yield (PEP 525 prohibits yielding during async-generator aclose); archive now silent; operators inspect `traces_archive/<run_id>/` |
| 2026-05-23 | 3 | A2+A5 accidentally bundled into single commit `f50b2d4` (atomicity violation) | `git reset --soft HEAD~1`; Edit-reverted A5 hunk; re-committed A2 alone as `6a1a40c`; Edit-restored A5 hunk; committed as `4fcd430` |

---

## Sign-off

- [x] Batch 1 verified — sign here: claude (Opus 4.7)  date: 2026-05-23  notes: commits f1bb6b1 (pre-flight filter), 7919029 (B18), 5e652ce (A6), 7fce71b (B14), 01bb5b4 (B15). Unit smokes passed; full E2E deferred per tracker note.
- [x] Batch 2 verified — sign here: claude (Opus 4.7)  date: 2026-05-23  notes: commits b0b3914 (B1), ed80bec (B5). pgroup-kill confirmed against 3-process tree; idle_timeout default + math verified. Real disconnect test deferred to next live run.
- [x] Batch 3 verified — sign here: claude (Opus 4.7)  date: 2026-05-23  notes: commits 6a1a40c (A2), 4fcd430 (A5), 4305870 (B12). One initial bundle (A2+A5) was unwound via `git reset --soft HEAD~1` + edit-revert-then-redo so atomic-per-item is preserved.
- [x] Batch 4 verified — sign here: claude (Opus 4.7)  date: 2026-05-23  notes: commits fe0a83b (B2), 4960c17 (B9). Unit tests on lock + hash both pass; real concurrent-curl race deferred to next live run.
- [x] Batch 5 verified — sign here: claude (Opus 4.7)  date: 2026-05-23  notes: commit a0deed3. State-module unit tests + router orphan-detection unit tests pass. Live kill-restart test deferred.
- [x] Batch 6 verified — sign here: claude (Opus 4.7)  date: 2026-05-23  notes: commits ad7a335 (A1), cbc2966 (A3), 20c5476 (A4). A1 helper unit smoke + A3 live Milvus restart smoke both green. A4 adds RECOVERY.md as top-level playbook.
- [ ] Batch 7 verified — sign here: ____  date: ____  notes:
- [ ] Batch 8 verified (quarantine + merge) — sign here: ____  date: ____  notes:
- [ ] **Full Sprint 4 dry-run with no previously-observed anomalies firing** — sign here: ____  date: ____  notes:

---

*Last updated: 2026-05-23. Edit only this file as work progresses; the plan is the spec.*
