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
**Target commit message:** `orchestrator: honest outcomes + qa-doctrine-failed event + safer partial_resume (A2+A5+B12)`

| ID | Item | Status | Commit | Verification | Notes |
|---|---|---|---|---|---|
| A2 | QA-doctrine-failed event + `stop_on_qa_doctrine_failure` flag | pending | — | synthetic QA fail surfaces new event | opt-in flag preserves default behavior |
| A5 | `bl.done outcome` reflects worst role | pending | — | synthetic QA fail → outcome="merged_no_qa" | new outcome strings list |
| B12 | `partial_resume` cross-checks git log | pending | — | uncommitted QA file → QA runs | |

**Batch 3 gate verification:**
- [ ] Import smoke OK
- [ ] Synthetic QA fail produces expected event + outcome
- [ ] partial_resume safer-path test

---

## Batch 4 — Concurrency lock + idempotency

**Branch:** `sprint-2-orchestrator`
**Target commit message:** `concurrency: per-repo lock + brief idempotency on /run-brief (B2+B9)`

| ID | Item | Status | Commit | Verification | Notes |
|---|---|---|---|---|---|
| B2 | Per-repo asyncio.Lock | pending | — | parallel POST: 200 + 409 | single-worker assumption noted in comment |
| B9 | Brief-hash idempotency | pending | — | duplicate POST: 200 + 409 | bundled with B2 |

**Batch 4 gate verification:**
- [ ] Import smoke OK
- [ ] Parallel POST test (2 curls): one 200, one 409
- [ ] Duplicate POST test: 409

---

## Batch 5 — Disk-persisted state

**Branch:** `sprint-2-orchestrator`
**Target commit message:** `state: disk-persisted run checkpoints for restart resume (A7)`
**Depends on:** Batch 4 (B2 lock prevents concurrent state writes)

| ID | Item | Status | Commit | Verification | Notes |
|---|---|---|---|---|---|
| A7 | Run-state checkpoints at `.orchestrator-state/<run_id>.json` | pending | — | kill uvicorn mid-sprint → resume picks up | new `run_state.py` module |

**Batch 5 gate verification:**
- [ ] Import smoke OK
- [ ] State file structure validates with jq
- [ ] Manual kill-restart resumes at right BL

---

## Batch 6 — Recovery automations

**Branch:** `sprint-2-orchestrator`
**Target commit message:** `recovery: auto-rebase + milvus auto-restart + scorer backfill (A1+A3+A4)`
**Depends on:** Batch 3 (outcome labels exist)

| ID | Item | Status | Commit | Verification | Notes |
|---|---|---|---|---|---|
| A1 | Non-FF auto-rebase in agent worktree + re-run gate | pending | — | reproduce race scenario → recovers | gate re-run REQUIRED post-rebase |
| A3 | Milvus auto-restart in `_preflight_retrieval` | pending | — | `docker stop milvus` → preflight recovers | cooldown 60s |
| A4 | Document score-only path for backfill | pending | — | `/score-bl BL-0002` produces scorecard | doc-only |

**Batch 6 gate verification:**
- [ ] Import smoke OK
- [ ] Non-FF race repro test
- [ ] Milvus auto-restart test
- [ ] BL-0002 score backfill on v3 succeeds

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

---

## Sign-off

- [x] Batch 1 verified — sign here: claude (Opus 4.7)  date: 2026-05-23  notes: commits f1bb6b1 (pre-flight filter), 7919029 (B18), 5e652ce (A6), 7fce71b (B14), 01bb5b4 (B15). Unit smokes passed; full E2E deferred per tracker note.
- [x] Batch 2 verified — sign here: claude (Opus 4.7)  date: 2026-05-23  notes: commits b0b3914 (B1), ed80bec (B5). pgroup-kill confirmed against 3-process tree; idle_timeout default + math verified. Real disconnect test deferred to next live run.
- [ ] Batch 3 verified — sign here: ____  date: ____  notes:
- [ ] Batch 4 verified — sign here: ____  date: ____  notes:
- [ ] Batch 5 verified — sign here: ____  date: ____  notes:
- [ ] Batch 6 verified — sign here: ____  date: ____  notes:
- [ ] Batch 7 verified — sign here: ____  date: ____  notes:
- [ ] Batch 8 verified (quarantine + merge) — sign here: ____  date: ____  notes:
- [ ] **Full Sprint 4 dry-run with no previously-observed anomalies firing** — sign here: ____  date: ____  notes:

---

*Last updated: 2026-05-23. Edit only this file as work progresses; the plan is the spec.*
