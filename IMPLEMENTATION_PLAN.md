# Agentic Skills — Implementation Plan

> **Scope:** Decision (a) from `DESIGN_SHORTCOMINGS.md`'s matrix — "Now" set + easy wins.
> **Items:** A1, A2, A3, A4, A5, A6, A7 + B1, B2, B3, B4, B5, B7, B9, B12, B14, B15, B17, B18.
> **Authored:** 2026-05-23, after Sprint 3 BL-0005 abort + research-probe completion.
> **Process discipline:** every change must clear the bar — explicit risk, named test, named rollback. Probe findings already informed revised implementation choices (see DESIGN_SHORTCOMINGS.md §"Research findings").
> **Companion:** `IMPLEMENTATION_TRACKER.md` is the live checklist updated as each item lands.

---

## 0. Pre-flight checks (run before any code change)

These must all pass before Batch 1 starts:

| Check | Command | Required result |
|---|---|---|
| No orchestrator running | `pgrep -f run_orchestrator.py \|\| echo none` | `none` |
| No live agent claude subprocesses | `ps -ef \| grep -E "claude.*stream-json" \| grep -v claude-mem \| grep -v grep \| wc -l` | `0` |
| Uvicorn alive | `lsof -i :8000 -sTCP:LISTEN \| tail -1` | port listener present |
| No leftover worktrees | `cd target && git worktree list \| wc -l` | `1` (main only) |
| Milvus healthy | `docker ps --filter name=milvus --format '{{.Status}}'` | `Up … (healthy)` |
| v3 HEAD known | `cd target && git log --oneline -1 agentic-skills-work-v3` | `b46b4d6 BL-0005…` |
| Backend imports clean (baseline) | `cd webapp/backend && .venv/bin/python -c "from app.services import orchestrator, claude_agent, traces; print('OK')"` | `OK` |

---

## 1. Sequencing rationale

Eight batches, ordered lowest-risk → highest-risk. Each batch is independently revertible. Verification gates each batch before next begins.

| Batch | Theme | Risk | Touches | Independent? |
|---|---|---|---|---|
| 1 | Pure observability | Near-zero | Reader script + traces meta + log paths + trace archival | Yes |
| 2 | Subprocess hygiene | Low | `claude_agent.py` only | Yes |
| 3 | Orchestrator state honesty | Low | `orchestrator.py` BL loop | Yes |
| 4 | Concurrency + idempotency | Medium | `projects.py` endpoint wrapper | Yes |
| 5 | Disk-persisted state | Medium | New file + `orchestrator.py` checkpoints | Depends on Batch 4 |
| 6 | Recovery automations | Medium | `projects.py` + `orchestrator.py` | Depends on Batch 3 |
| 7 | UI surface for new events | Low | `AppV2.jsx` | Yes |
| 8 | Graphify cache refactor | **High** | `graph.py` + `indexing.py` (+ bridge.js test) | **Quarantine branch** |

---

## 2. Batch 1 — Pure observability (zero behavior change)

**Items:** A6 (full event dump on failure), B14 (harness_sha in trace meta), B15 (auto-archive traces on sprint_complete), B18 (logs out of `/tmp/`).

### A6 — Reader script dumps full event JSON on failure
**Goal:** Stop losing diagnostic data when a phase fails.
**Files:** `/tmp/run_orchestrator.py`.
**Change:** In the formatter, when `phase in {merge_to_target, regression_gate}` AND `ok=False`, OR when `phase == "orchestrator.aborted"`, append `json.dumps(evt)[:1500]` after the normal one-line summary.
**Risk:** Log file grows when failures occur. Bounded — only on failure.
**Test:** Trigger a failure case (e.g., delete `.agentic-skills.json` then POST `/run-brief`) and confirm full event JSON appears in `orchestrator_run.log`.
**Rollback:** Restore prior `run_orchestrator.py` from git or re-write 5 lines.

### B14 — `harness_sha` in trace meta
**Goal:** Forensically tag every trace with the agentic-skills repo SHA that ran it.
**Files:** `webapp/backend/app/services/traces.py` (TraceWriter init).
**Change:** On `TraceWriter.__init__`, run `git -C <agentic-skills repo> rev-parse HEAD` once and write to `meta.json` as `harness_sha`. Use `subprocess.run` with 1s timeout — fail-safe to `"unknown"` on error.
**Risk:** None — additive field.
**Test:** Start any agent run, inspect `traces/<repo>/<latest>/meta.json` for `harness_sha` key matching `git -C agentic-skills rev-parse HEAD`.
**Rollback:** Remove the field-write.

### B15 — Auto-archive traces on sprint_complete
**Goal:** Keep live traces directory clean — auto-move sprint's traces into `traces_archive/<run_id>/` when sprint finishes successfully.
**Files:** `webapp/backend/app/services/orchestrator.py` (in `run_brief` on sprint_complete emit).
**Change:** After emitting `sprint_complete`, move trace dirs created during this run (track via timestamps captured at run start) into `traces_archive/<run_id>/`. Use shutil.move atomically.
**Risk:** Race with concurrent trace writes from any still-finishing subprocess. Mitigation: only archive at end-of-run, after all role flows have closed.
**Test:** Run a 1-BL mini sprint, observe traces appear in `traces/<repo>/`, then on `sprint_complete` confirm they relocate to `traces_archive/<run_id>/`.
**Rollback:** Skip the archive step.

### B18 — Operational logs out of `/tmp/`
**Goal:** Logs survive reboots; co-located with traces.
**Files:** `/tmp/run_orchestrator.py` (log path target), `/tmp/milestone_watcher.sh` (input/output paths).
**Change:** Point logs to `webapp/backend/logs/orchestrator/<timestamp>/` instead of `/tmp/*`. Update reader + watcher to use new paths. Existing `/tmp/` logs left in place for reference.
**Risk:** Operator habits (`tail -f /tmp/orchestrator_milestones.log`) become stale. Mitigation: leave symlinks from `/tmp/` for one sprint.
**Test:** Start an orchestrator run; new log files appear under `webapp/backend/logs/orchestrator/<ts>/`.
**Rollback:** Revert path constants.

**Batch 1 verification:**
- Import smoke: `from app.services import orchestrator, claude_agent, traces`
- Restart uvicorn; hit `/openapi.json`; confirm endpoint list unchanged
- Run a 30-second decompose-brief on an empty repo; confirm new `harness_sha` field appears in trace meta; logs appear in new path

**Batch 1 commit:** `obs: full event dumps, harness_sha, trace auto-archive, logs out of /tmp/ (A6+B14+B15+B18)`

---

## 3. Batch 2 — Subprocess hygiene

**Items:** B1 (process-group-aware kill on cancellation), B5 (per-subprocess idle timeout).

### B1 — Process-group-aware subprocess kill
**Goal:** Eliminate orphan claude PIDs when SSE consumer disconnects.
**Files:** `webapp/backend/app/services/claude_agent.py`.
**Change:**
- `create_subprocess_exec(..., preexec_fn=os.setsid)` — spawns claude in its own process group.
- Wrap event loop in `try/finally`. In `finally`: if proc is alive, `os.killpg(proc.pid, SIGTERM)`, wait 10s, then `os.killpg(proc.pid, SIGKILL)` if still alive. Probe-confirmed pattern.
**Risk:** Too-aggressive kill mid-commit could leave worktree dirty. Mitigation: 10s grace period; check `git status -s` in worktree if cleanup happens during commit-active phase; log loudly.
**Test:**
1. Start `/decompose-brief`, kill the SSE reader script mid-flight.
2. Check `ps -ef | grep claude.*stream-json | grep -v claude-mem` returns 0.
3. Check no zombie MCP processes.
**Rollback:** Drop the `preexec_fn` + `finally` block.

### B5 — Idle timeout per subprocess
**Goal:** Detect hung claude calls earlier than the 40-minute wall timeout.
**Files:** `webapp/backend/app/services/claude_agent.py`.
**Change:** Add `idle_timeout=600` parameter (10 min default). Reset on every received frame (any type). If no frame for `idle_timeout` seconds, kill subprocess with the B1 mechanism, emit `_meta phase=idle_timeout`.
**Risk:** Killing legitimate slow processes. Mitigation: 10-min default (conservative); reset on ANY frame, not just assistant tokens; per-role configurable later.
**Test:** Set `idle_timeout=5` for one role flow, confirm kill fires after 5s of silence.
**Rollback:** Default `idle_timeout=None` → behavior identical to current.

**Batch 2 verification:**
- Import smoke
- Real cancellation test: start `/decompose-brief`, kill reader after 30s, count claude PIDs (must be 0 after 15s)
- Idle test: temporary `idle_timeout=5` in code, verify abort fires

**Batch 2 commit:** `subprocess: pgroup-aware kill on cancel + idle timeout (B1+B5)`

---

## 4. Batch 3 — Orchestrator state honesty

**Items:** A2 (QA-doctrine-failed surfaced), A5 (truthful `bl.done outcome`), B12 (partial_resume cross-check git log).

### A2 — QA doctrine give-up surfaced
**Goal:** When QA can't satisfy doctrine after 2 retries, treat as a real failure.
**Files:** `webapp/backend/app/services/orchestrator.py`.
**Change:** After `_qa_or_scorer_flow` returns for QA, check `qa_outcome.doctrine_ok`. If False AND `merged=False`, emit `orchestrator.qa_doctrine_failed` event with `validator_summary`. If new option `stop_on_qa_doctrine_failure=True`, abort the sprint.
**New request field:** add `stop_on_qa_doctrine_failure: bool = False` to `RunBriefRequest`. Default False → backwards-compatible.
**Risk:** Behavior change to existing summaries if not opt-in. Mitigation: opt-in flag, default off.
**Test:** Synthetic QA that always misses citations → expect new event + bl outcome reflects failure.
**Rollback:** Drop the new event emission.

### A5 — Truthful `bl.done outcome` label
**Goal:** Outcome reflects the WORST role result, not just engineer.
**Files:** `webapp/backend/app/services/orchestrator.py`.
**Change:** Compute outcome via:
```python
if eng_outcome.no_op and qa_skipped:     outcome = "no_op"
elif eng_outcome.merged and qa.merged and scorer.doctrine_ok: outcome = "merged_full"
elif eng_outcome.merged and not qa.merged:                    outcome = "merged_no_qa"
elif eng_outcome.merged and qa.merged and not scorer.doctrine_ok: outcome = "merged_no_score"
else:                                                          outcome = "engineer_unmerged"
```
**Risk:** UI consumers depend on `"merged"` string. Mitigation: keep `"merged"` for fully-clean case as `"merged_full"`; map old string in UI handler.
**Test:** Force a QA-fail scenario, verify outcome="merged_no_qa".
**Rollback:** Restore hard-coded `"merged"`.

### B12 — partial_resume cross-checks git log
**Goal:** Don't skip QA based on a stale `.agile-v/qa/<bl>.md` from a half-finished run.
**Files:** `webapp/backend/app/services/orchestrator.py`.
**Change:** In partial_resume check, additionally require `git log <agent_branch> -- .agile-v/qa/<bl>.md` to show a `qa(<bl>...)` commit. If file present but no commit, treat QA as missing.
**Risk:** False negative (file truly is from completed work but commit was amended). Mitigation: also accept any commit touching the file under message prefix `qa(`.
**Test:** Stage `.agile-v/qa/BL-0099.md` manually (no commit), then resume — orchestrator should run QA, not skip.
**Rollback:** Restore file-existence-only check.

**Batch 3 verification:**
- Import smoke
- Synthetic QA-fail test on a throwaway BL; observe new event + outcome label
- partial_resume test with un-committed QA file

**Batch 3 commit:** `orchestrator: honest outcomes + qa-doctrine-failed event + safer partial_resume (A2+A5+B12)`

---

## 5. Batch 4 — Concurrency lock + idempotency

**Items:** B2 (per-repo lock), B9 (idempotency on `/run-brief`).

### B2 — Per-repo asyncio lock
**Goal:** Refuse concurrent `/run-brief` for same repo.
**Files:** `webapp/backend/app/routers/projects.py`.
**Change:** Module-level dict `_run_locks: dict[str, asyncio.Lock]`. In `/run-brief`, acquire lock for `repo`. If already locked, return HTTP 409 with `{"error": "run-in-progress", "current_run_id": ...}`. Release on stream close.
**Hard assumption:** uvicorn single-worker. Document with code comment + a startup log line that warns if `WEB_CONCURRENCY > 1`.
**Risk:** Lock held forever if process is killed mid-stream. Mitigation: asyncio.Lock dies with the process; uvicorn restart auto-clears.
**Test:** Fire two `curl` POSTs to `/run-brief` for same repo within 1s; first gets 200, second gets 409.
**Rollback:** Drop the dict.

### B9 — Idempotency via brief hash
**Goal:** Same brief submitted twice doesn't spawn a duplicate run.
**Files:** `webapp/backend/app/routers/projects.py` (bundled with B2).
**Change:** Compute `brief_hash = sha256(brief + project_name + repo)`. Track active hashes alongside locks. On collision: 409 with same response shape as B2.
**Risk:** Hash collisions (negligible with sha256). Mitigation: none needed.
**Test:** Two POSTs with identical body — second returns 409.
**Rollback:** Drop the hash tracking.

**Batch 4 verification:**
- Import smoke
- Concurrent POST test (curl ×2 in parallel)
- Idempotent POST test

**Batch 4 commit:** `concurrency: per-repo lock + brief idempotency on /run-brief (B2+B9)`

---

## 6. Batch 5 — Disk-persisted state

**Items:** A7.

### A7 — Disk-persisted run state for resume
**Goal:** Survive uvicorn restart mid-sprint.
**Files:** New `webapp/backend/app/services/run_state.py`; checkpoints in `orchestrator.py`.
**Change:** Persist `{run_id, brief_hash, repo, started_at, current_bl, bl_outcomes: [...]}` at each milestone (`bl.start`, `bl.done`, `sprint_complete`). Atomic write: write tmp, fsync, rename. Stored at `webapp/backend/.orchestrator-state/<run_id>.json`. On `/run-brief` startup, scan state dir; if unfinished run for same `brief_hash` exists, resume from `current_bl`. Validate against git history: `current_bl` must be the next un-merged BL on `agent_branch`. Refuse to resume if validation fails.
**Risk:** Corrupted state file blocks resume. Mitigation: validation step + clear error message + explicit `?force_resume=true` override.
**Test:** Start a sprint, kill uvicorn after BL-0001 merges, restart, verify resume picks up at BL-0002.
**Rollback:** Drop the state writes; resume falls back to existing skip_po+R11 reconstruction (already proven to work).

**Batch 5 verification:**
- Import smoke
- Kill-restart test (manual)
- Validate state file structure with `cat .orchestrator-state/<id>.json | jq`

**Batch 5 commit:** `state: disk-persisted run checkpoints for restart resume (A7)`

---

## 7. Batch 6 — Recovery automations

**Items:** A1 (non-FF auto-rebase), A3 (Milvus auto-restart preflight), A4 (score-only convenience).

### A1 — Auto-rebase agent branch on non-FF
**Goal:** Recover gracefully from operator commits racing agent worktrees.
**Files:** `webapp/backend/app/services/orchestrator.py` (engineer + QA flows).
**Change:** When `fast_forward_target` returns `kind="non_ff"`:
1. `cd wt.path && git rebase target_ref` — probe-confirmed safe inside worktree
2. Re-run `fast_forward_target`
3. On rebase conflict: do NOT auto-resolve. Emit `orchestrator.merge_rebase_failed` + fall through to awaiting_review.
4. After successful rebase, **re-run the gate** (the new SHA was not tested by the previous gate run).
**Risk:** Re-running gate adds ~15 minutes. Conflict resolution is human work. Mitigation: gate re-run is correctness-required; conflicts surface clearly.
**Test:** Reproduce the scenario: commit on agent_branch while a worktree exists; trigger merge; verify auto-rebase + gate re-run + success.
**Rollback:** Drop the rebase block.

### A3 — Milvus auto-restart preflight
**Goal:** Self-heal one common cause of mid-sprint aborts.
**Files:** `webapp/backend/app/routers/projects.py` (`_preflight_retrieval`).
**Change:** When port 19530 is unreachable, attempt `docker start milvus-standalone` once, wait up to 30s for healthy (poll port), then re-probe. Only raise `RetrievalUnavailable` if restart fails. Add 60-second cooldown per process — don't restart-loop.
**Risk:** Repeatedly auto-restarting a Milvus that's broken-by-config. Mitigation: cooldown + log loudly + abort after second failure.
**Test:** `docker stop milvus-standalone`, trigger `/decompose-brief`, observe auto-restart + run continues.
**Rollback:** Drop the docker start block.

### A4 — Score-only resumption path
**Goal:** Backfill scores for BLs where scorer aborted (e.g., BL-0002 from Sprint 3).
**Files:** `webapp/backend/app/routers/projects.py` doc + minor.
**Change:** `/score-bl` endpoint already exists. Document the recovery procedure in `PIPELINE.md`. Optionally add `--start-bl <id>` param to `/run-brief` body that skips earlier BLs even when no_op detection might be wrong.
**Risk:** None — uses existing endpoint.
**Test:** Manually call `/score-bl` for BL-0002 on v3 (verify it works against existing engineer+QA commits).
**Rollback:** Doc-only revert.

**Batch 6 verification:**
- Import smoke
- Simulated non-FF (manual git operation, then `/run-brief`)
- Milvus stop → preflight test
- `/score-bl` on BL-0002 → expect scorecard

**Batch 6 commit:** `recovery: auto-rebase + milvus auto-restart + scorer backfill (A1+A3+A4)`

---

## 8. Batch 7 — UI surface for new events

**Items:** B4 (AppV2 renders new fields), B17 (Stop kills server-side — subsumed by B1).

### B4 — AppV2 handles new event fields
**Goal:** Operator sees `partial_resume`, `qa_doctrine_failed`, `merge_to_target kind/error`, new outcome labels.
**Files:** `webapp/frontend/src/AppV2.jsx`.
**Change:**
- New handler for `orchestrator.partial_resume` → render as sub-step badge "resume" on the BL row.
- New handler for `orchestrator.qa_doctrine_failed` → red badge on QA sub-step + error in detail rail.
- Extend `merge_to_target` handler: when `ok=false`, surface `kind`/`error` in detail rail.
- New outcome strings (`merged_full`, `merged_no_qa`, `merged_no_score`) get color-coded badges.
**Risk:** Visual regression on existing handlers. Mitigation: additive case-handling only; old strings still mapped.
**Test:** `npm run build`; open `localhost:8000`; trigger a synthetic event sequence and verify rendering.
**Rollback:** Restore prior `ingest()` function.

**Batch 7 verification:**
- `npm run build` clean
- Visual smoke

**Batch 7 commit:** `ui: AppV2 surfaces partial_resume + qa_doctrine_failed + merge error (B4+B17)`

---

## 9. Batch 8 — Graphify cache refactor (QUARANTINE)

**Items:** B3 (graphify writes to shared cache, not worktree). Implicitly closes B7 (`.gitignore` hygiene) and B8 (cache reuse).

### B3 — Graphify shared content-addressed cache
**Goal:** Bridge.js and graphify never write into the target repo. Permanent fix for the Sprint 2 .gitignore class of bugs.
**Files:**
- `langgraph_engine/retrieval/graph.py` — `ensure_indexed()` writes to `~/.cache/agentic-skills/graphify/<sha256(repo_path)>-<commit>/graph.json`
- `webapp/backend/app/services/indexing.py` — read path matches new location
- Update `Graph.load()` consumers if path is hardcoded
- `.spike-node/bridge.js` — graphify_root path arg, read+write
- (Skip lists in `brownfield.py` + `retrieval_server.py` — keep as defense in depth)
**Quarantine:** This batch lands on a **separate branch** off `sprint-2-orchestrator`. Name: `sprint-2-orchestrator-b3-graphify-cache`. Smoke test isolated before merging back.
**Risk:** **High.** If any consumer breaks, all graph_* MCP tools fail → R9 grounding floor fails → cascading doctrine failures. Mitigation: branch isolation + smoke test against a single `/decompose-brief` call before merging.
**Test:**
1. On branch, run `/decompose-brief` against a tiny throwaway repo
2. Verify `~/.cache/agentic-skills/graphify/...` is created
3. Verify the target repo's working tree has NO `graphify-out/` directory
4. Verify the agent successfully made graph queries (check trace's `n_retrieval_calls > 0`)
5. Run a single `/execute-bl` and verify QA `git add -A` does NOT pick up graphify-out
**Rollback:** Merge `sprint-2-orchestrator` back over, discard the quarantine branch.

**Batch 8 verification:**
- All quarantine-branch tests above
- After merge: re-run import smoke + a tiny end-to-end

**Batch 8 commit:** `retrieval: graphify writes to shared content-addressed cache (B3 — closes B7, B8 implicit)`

---

## 10. Items deferred (not in this plan)

Per `DESIGN_SHORTCOMINGS.md`, these are deferred to later sprints:

- B6 — Engineer re-spawn on QA findings (state-machine change, own scoping)
- B8 — Graphify content-addressed cache reuse (performance, falls out of B3 partially)
- B10 — Cost telemetry aggregation (ABL-0013)
- B11 — Parallel BL execution (ABL-0011)
- B13 — Triage agent (ABL-0002)

Tracker also includes them with status `deferred` so they're not forgotten.

---

## 11. Risk register

| Risk | Mitigation | Detection |
|---|---|---|
| Batch N regression breaks Batch (N-1) verification | Each batch is independently revertible via `git revert <sha>` | Import smoke + endpoint health post-batch |
| Subprocess-kill kills legitimate work | 10s grace + log + check worktree status | Trace meta `kill_was_clean` flag if added |
| Auto-rebase produces non-reviewed code | Always re-run gate post-rebase | Gate failure detection |
| Disk state file desyncs from git | Validate `current_bl` against git log on resume | Refuse-to-resume with clear error |
| Concurrency lock held forever | asyncio.Lock dies with process | Lock auto-clears on uvicorn restart |
| B3 misses a graphify-out consumer | Quarantine branch + smoke test | Agent's graph_* tool calls fail visibly |

---

## 12. Done criteria for this plan

This plan is **complete** when:

- [ ] All Batch 1–7 commits land on `sprint-2-orchestrator`
- [ ] Batch 8 lands on quarantine branch and is merged back after smoke test
- [ ] `IMPLEMENTATION_TRACKER.md` shows all in-scope items `done`
- [ ] A full Sprint 4 run (next feature) completes without any of the previously observed anomalies firing as bugs:
  - No orphan claude PIDs after stop
  - No gitignore-pollution merge collisions
  - No silent QA-doctrine give-ups marked "merged"
  - No non-FF aborts from operator commits
  - No Milvus-crash mid-sprint aborts
  - No `aborted` event with empty reason
  - Logs in `webapp/backend/logs/`, not `/tmp/`

---

*Authored 2026-05-23. Companion: `IMPLEMENTATION_TRACKER.md`. Source-of-truth shortcoming ledger: `DESIGN_SHORTCOMINGS.md`.*
