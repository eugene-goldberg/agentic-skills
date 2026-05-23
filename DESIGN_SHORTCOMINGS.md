# Agentic Skills — Design Shortcomings Ledger

> **Status:** Open audit, written after the Sprint 3 (Notifications & Activity System) mid-flight abort on 2026-05-23.
>
> **Purpose:** Single source of truth for every anomaly and design weakness observed during Sprint 2 (Team Collaboration on `agentic-skills-work-v2`) and Sprint 3 (Notifications on `agentic-skills-work-v3`). Each entry is severity-classified, sized, and linked to evidence. Use this as a tracking checklist as fixes land.
>
> **State at time of writing:**
> - All claude subprocesses killed
> - All worktrees pruned
> - Orchestrator script not running
> - Backend uvicorn alive (PID 34768)
> - v3 HEAD: `b46b4d6` (BL-0005 engineer merged, recovered via manual rebase after operator commit `090d177` raced the agent worktree)
> - BL-0004 QA never merged (`doctrine_ok=false` after 2 retries — same pattern as Sprint 2 BL-0004)
> - BL-0002 has no scorer (orchestrator aborted when Milvus crashed mid-flight)

---

## Tier A — known anomalies with mechanical fixes

These are bugs we have directly observed. Each has a clear fix and a clear test for "works."

### A1 — `fast_forward_target` non-FF on operator-side commits

**Evidence:** Sprint 3 abort at 10:18:25 with `non_ff: agentic-skills-work-v3 (090d177f) is not an ancestor of agent/f52b55282296 (60951fbf)`.

**Cause:** Operator committed `090d177` (M1 fix) on v3 while BL-0005's worktree was already forked from the older `a08b92d`. Agent's branch became a sibling, not a descendant.

**Fix:** in `orchestrator.py`'s engineer + QA merge paths, when `merge.get("kind") == "non_ff"`, attempt `git rebase <target_ref> <agent_branch>` before retrying `fast_forward_target`. Mirror what the operator did manually.

**Effort:** ~15 LOC. **Risk:** low (rebase of a single branch with one commit on top).

---

### A2 — QA doctrine give-up is silent and misleading

**Evidence:** Sprint 3 BL-0004 logged `qa.done {merged:false, doctrine_ok:false}` then `bl.done {outcome: "merged"}`. QA gave up after 2 doctrine retries; no tests landed; the BL was reported as `merged`. Same pattern as Sprint 2 BL-0002 and BL-0004.

**Cause:** Current BL loop only honors `stop_on_failure` for engineer failures, not QA-doctrine failures. The bl.done outcome string is hard-coded to "merged" once engineer merged.

**Fix:** in `orchestrator.py` per-BL loop:
- Emit `orchestrator.qa_doctrine_failed` event with the validator's summary
- If `stop_on_failure`, abort the sprint
- Else, mark `bl.done outcome="merged_no_qa"` (or similar) so it shows up in summary

**Effort:** ~20 LOC. **Risk:** low.

---

### A3 — Milvus dies mid-sprint with no auto-recovery

**Evidence:** Sprint 3 first run aborted at 00:55:13 with `claude_context: ok=false, node exit 1`. Docker inspection showed `milvus-standalone` had exited. Manual `docker start` restored it.

**Cause:** `_preflight_retrieval` raises `RetrievalUnavailable` and the orchestrator aborts. No restart attempt.

**Fix:** in `_preflight_retrieval`, when port 19530 is unreachable, attempt `docker start milvus-standalone` once + wait up to 30s for healthy. Only raise if restart fails.

**Effort:** ~20 LOC. **Risk:** low (idempotent, only triggers when already down).

---

### A4 — Score-only backfill needs operator path

**Evidence:** BL-0002 in Sprint 3 has no scorecard because the orchestrator aborted mid-scorer. Branch artifacts intact, scoring history gone.

**Cause:** Sprint completion is binary — there's no clean way to backfill a single missing role outcome.

**Fix:** `/api/projects/{repo}/score-bl` endpoint already exists. Document the recovery procedure and add a convenience: `/run-brief` accepts `--start-bl <id>` to resume from a specific BL.

**Effort:** ~5 LOC + doc. **Risk:** trivial.

---

### A5 — `bl.done outcome` lies when only engineer merged

**Evidence:** Sprint 2 BL-0004 + Sprint 3 BL-0004 both reported `outcome=merged` despite QA never landing.

**Cause:** Hard-coded string after engineer merge.

**Fix:** Compute outcome from `min(engineer.merged, qa.merged, scorer.doctrine_ok)`. Possible values: `merged_full`, `merged_no_qa`, `merged_no_score`, `engineer_unmerged`, `partial_resume_qa_only`, `no_op`.

**Effort:** ~5 LOC. **Risk:** trivial. **Couples with A2.**

---

### A6 — Reader script's per-field formatter is fragile observability

**Evidence:** Every new SSE event field (`kind`, `error`, `branch`, `doctrine_ok`, `no_op`, `merged_sha=None`) required formatter updates. The `orchestrator.aborted` reason almost got lost because no `extra` case existed.

**Cause:** `/tmp/run_orchestrator.py` hand-picks fields per phase.

**Fix:** when `ok=False` on `merge_to_target` / `regression_gate`, or for any `orchestrator.aborted` event, dump the full event JSON to the log. Belongs in the reader, not the orchestrator.

**Effort:** ~3 LOC. **Risk:** zero.

---

### A7 — Orchestrator state is in-memory only

**Evidence:** Twice in Sprint 3, the orchestrator process died (Milvus crash → endpoint exception, then operator-induced abort after M1 commit) and we lost queue position. Recovery relied on `skip_po + R11 no-op + partial_resume` to reconstruct from git history.

**Cause:** PIPELINE.md specified disk-persisted state at `webapp/backend/.orchestrator-state/<run_id>.json`. Never implemented.

**Fix:** Write `{run_id, brief_hash, started_at, current_bl, bl_outcomes[]}` to disk at every milestone. On `/run-brief` startup, if an unfinished run for the same `brief_hash` exists, resume from `current_bl`. Doesn't replace `skip_po`, complements it.

**Effort:** ~40 LOC. **Risk:** medium (concurrency on writes if two runs ever overlap — but B2 will prevent that).

---

## Tier B — design shortcomings not previously surfaced

These are deeper than Tier A. Numbered by severity (HIGH first within tier).

### B1 — Orphan claude subprocesses on SSE disconnect (HIGH)

**Evidence:** When `/tmp/run_orchestrator.py` crashed at 23:08:09 on a `merged_sha=None` formatter exception, FastAPI cancelled the SSE generator. Two `claude --stream-json` PIDs (5602, 5777, 5798) kept running — each ~200-500 MB resident, each burning Anthropic API tokens, each writing to traces.

**Cause:** `stream_agent_task` spawns a subprocess but doesn't track it for cleanup on cancellation. No `try/finally` chain killing the PID.

**Fix:** Wrap subprocess lifecycle in `try/finally` that sends SIGTERM (then SIGKILL after grace) when the async generator is cancelled.

**Effort:** ~10 LOC `claude_agent.py`. **Risk:** low.

---

### B2 — No concurrency lock on `/run-brief` (HIGH)

**Evidence:** Sprint 2 day 1, the open v2 UI tab + a separate CLI POST hit `/run-brief` near-simultaneously. Both spawned full orchestrator generators. They fought over `agent_branch` updates and worktree slots. Resulted in two parallel BL-0001 engineers and corrupted state until I manually killed one.

**Cause:** No mutual exclusion. Endpoint is a pure async generator factory.

**Fix:** Per-repo `asyncio.Lock` held for the lifetime of a `/run-brief` call. Second concurrent POST gets HTTP 409 with `"already running, current_bl=BL-XXXX, run_id=…"`. Optionally upgrade to a filesystem lock so it survives uvicorn restarts.

**Effort:** ~25 LOC. **Risk:** low. **Pairs naturally with A7.**

---

### B3 — `bridge.js` writes `graphify-out/` INTO the worktree (HIGH)

**Evidence:** Sprint 2 BL-0002 and BL-0004 QA branches committed 178 graphify AST cache files each because QA's `git add -A` swept them up. Cost: 90+ minutes of debugging + post-hoc `.gitignore` patches on every target.

**Cause:** `ensure_indexed(repo_root)` in `langgraph_engine/retrieval/graph.py` runs `graphify update <repo_root>` which writes `<repo_root>/graphify-out/`. The bridge passes `target_repo=wt.path` (the worktree path) → graphify pollutes the worktree.

**Fix:** Write graphify output to a content-addressed shared cache at `~/.cache/agentic-skills/graphify/<sha256(repo_root)>-<branch_sha>/`. Update `ensure_indexed` + `Graph.load` accordingly. Permanently eliminates the entire bug class — no target repo will ever need a `graphify-out/` ignore line again.

**Effort:** ~25 LOC across `graph.py` + `bridge.js`. **Risk:** medium (must verify `Graph.load` consumers still work).

---

### B4 — AppV2.jsx ignores new event fields (MEDIUM)

**Evidence:** I added `partial_resume`, `merge_to_target kind/error/branch`, and proposed `qa_doctrine_failed` events. None of them render in the UI. Operators using the UI see incomplete state and don't know about gate retries or resume paths.

**Cause:** Event handlers in `AppV2.jsx`'s `ingest()` are hand-coded per phase prefix and don't know about new fields.

**Fix:** Extend `ingest()` to recognize `orchestrator.partial_resume`, render `qa_doctrine_failed` as a distinct sub-step badge, and surface `merge_to_target` error in the detail rail.

**Effort:** ~25 LOC AppV2.jsx. **Risk:** low.

---

### B5 — No per-subprocess idle timeout (MEDIUM)

**Evidence:** Claude can hang silently (rate limit lockout, network stall) for up to 40 min (total `timeout_seconds=2400`) before the orchestrator notices. This happened at least twice in Sprint 2.

**Cause:** Only a total wall-clock timeout exists. No "no event in N seconds" check.

**Fix:** Add `idle_timeout=180` to `stream_agent_task`. If no SSE frame from claude in 3 minutes, kill the subprocess and treat as failure. Lets the retry loop kick in much earlier.

**Effort:** ~10 LOC `claude_agent.py`. **Risk:** low.

---

### B6 — Engineer never re-spawned on QA-revealed bugs (MEDIUM)

**Evidence:** Sprint 2 BL-0007 QA flagged UI flake but produced PASS-W/R because the test infra worked. The actual code issue was never sent back to the engineer for a fix. The Pass-W/R 82/100 score reflects this.

**Cause:** Workflow ends at QA's PASS-W/R verdict. No mechanism for QA to demand engineer revisit.

**Fix:** New event type `qa_demands_engineer_rerun` with a focused fix-prompt. Orchestrator re-spawns engineer once with QA's findings, then re-runs QA. Bounded by `max_engineer_reruns_per_bl=1`.

**Effort:** ~30 LOC. **Risk:** medium (changes the BL state machine).

---

### B7 — `.gitignore` hygiene is per-target ad-hoc (MEDIUM)

**Evidence:** Sprint 2 ended with us adding `graphify-out/` to v3's `.gitignore`. Any future brownfield target will repeat the discovery if B3 isn't done first.

**Cause:** No harness-level preflight that asserts critical paths are ignored.

**Fix:** PO doctrine adds a preflight step: "before generating backlog, verify `.gitignore` contains `graphify-out/`, `_brownfield/.tmp/`, etc. If not, propose a doctrine commit." Or just always do B3 instead.

**Effort:** ~10 LOC. **Risk:** low. **Becomes moot if B3 lands.**

---

### B8 — Every worktree triggers a full graphify rebuild (MEDIUM)

**Evidence:** Sprint 2: 8 BLs × ~3 role-worktrees × ~60s graphify = ~24 min pure indexing. Sprint 3 will be similar.

**Cause:** `ensure_indexed` keys only on path existence (`graphify-out/graph.json`). Fresh worktree = no prior graph = full rebuild. Even though the source tree is identical to a tree we just indexed in main.

**Fix:** Cache by `(repo_remote, commit_sha)`. Restore from `~/.cache/agentic-skills/graphify/<key>/` if available, otherwise build then cache. Couples cleanly with B3.

**Effort:** ~20 LOC. **Risk:** low.

---

### B9 — No idempotency on POST `/run-brief` (LOW)

**Evidence:** Same as B2. Same brief twice = two parallel runs.

**Fix:** Compute `brief_hash = sha256(brief + project_name + repo)`. If an in-flight run exists with the same hash, return 409 with `Location:` of its SSE endpoint instead of starting a new one.

**Effort:** ~10 LOC. **Risk:** low. **Bundles with B2.**

---

### B10 — No cost telemetry aggregation (LOW)

**Evidence:** Every result frame in trace metadata has `total_cost_usd`. We have zero visibility into total spend per BL/sprint.

**Cause:** ABL-0013 in `BACKLOG.md`, intentionally deferred.

**Fix:** Aggregate per-BL costs from trace `meta.json.final_result_frame.total_cost_usd` and emit in `bl.done` event. Add `/api/telemetry/sprint/{id}` endpoint.

**Effort:** ~30 LOC. **Risk:** low. **Belongs in a telemetry sprint.**

---

### B11 — No parallel BL execution (LOW)

**Evidence:** BL-0006, BL-0007, BL-0008 in Sprint 3 have no inter-deps. Sprint runs serially anyway. ~6 hours of wall time could become ~2 hours.

**Cause:** ABL-0011 in `BACKLOG.md`, deferred to Sprint 5.

**Fix:** Build a wave-based scheduler over the dep DAG. Each wave runs independent BLs in parallel (with worktree slot limit, default 2). Merge serializes per ff-only convention.

**Effort:** ~80 LOC orchestrator + worktree coordination. **Risk:** high (resource contention, race conditions on agent_branch). **Defer.**

---

### B12 — `partial_resume` proxy is fragile (LOW)

**Evidence:** `partial_resume` triggers when engineer is no_op AND `.agile-v/qa/<bl>.md` is absent. A QA that crashed mid-write could leave a partial file → false positive → skips real QA.

**Cause:** Single existence check, no content check, no cross-reference with git log.

**Fix:** Additionally require a `qa(<bl>...)` commit message in `git log agent_branch -- .agile-v/qa/<bl>.md`. Belt + suspenders.

**Effort:** ~5 LOC. **Risk:** trivial.

---

### B13 — `stop_on_failure` is binary, no Triage (LOW)

**Evidence:** Every failure currently aborts the sprint. No mechanism to defer/split/escalate.

**Cause:** ABL-0002 in `BACKLOG.md`, blocked on ABL-0001 (this) being done.

**Fix:** Implement Triage agent (new role) that takes an aborted BL's full trace + scorer rubric and decides one of: `RETRY_REWRITE` / `DEFER` / `SPLIT` / `ESCALATE`. This is its own sprint.

**Effort:** large. **Defer.**

---

### B14 — No doctrine versioning (LOW)

**Evidence:** During Sprint 2 I patched `doctrine_validator.py` multiple times. BL-0001 ran on one version, BL-0008 on another. No way to forensically determine "which doctrine version evaluated BL-0004?"

**Cause:** Trace meta doesn't capture the agentic-skills repo's git SHA at run time.

**Fix:** At `stream_agent_task` startup, capture `git -C agentic-skills rev-parse HEAD` and write to trace `meta.json` as `harness_sha`.

**Effort:** ~5 LOC. **Risk:** zero. **High forensic value.**

---

### B15 — Trace dirs accumulate forever (LOW)

**Evidence:** Pre-archiving: 101 dirs in `webapp/backend/traces/full-stack-fastapi-template/`.

**Fix:** On `sprint_complete`, auto-move all traces from this run into `traces_archive/sprint-N-<feature>/`. Drop a tombstone with the final summary.

**Effort:** ~15 LOC. **Risk:** trivial.

---

### B16 — No dry-run / plan-only mode (LOW)

**Evidence:** Operator can't preview a PO decomposition without committing to a full run (cost + time).

**Fix:** Already partly exists via `/decompose-brief` endpoint. Document it as the canonical preview. Optionally add `--plan-only` flag to `/run-brief` that runs index → PO → emit backlog and exits.

**Effort:** ~5 LOC + doc. **Risk:** zero.

---

### B17 — UI Stop button doesn't kill server-side (LOW)

**Evidence:** AppV2's Stop uses `AbortController` on the client fetch. Server-side, the SSE generator gets cancelled, but the spawned claude subprocess is orphaned (see B1).

**Fix:** Couples with B1 (subprocess cleanup on cancellation). Once B1 is in, Stop works end-to-end.

**Effort:** 0 (subsumed by B1).

---

### B18 — Operational logs live in `/tmp/` (LOW)

**Evidence:** `/tmp/orchestrator_run.log`, `/tmp/orchestrator_milestones.log`, `/tmp/sprint_brief.md`, `/tmp/run_orchestrator.py`. All ephemeral.

**Fix:** Move to `webapp/backend/logs/orchestrator/<run_id>/` so they survive reboots and are co-located with trace dirs.

**Effort:** ~5 LOC (path changes). **Risk:** trivial.

---

## Decision matrix — what to apply now

| Set | Items | Why |
|---|---|---|
| **(a) "Now" set + easy wins (recommended)** | A1, A2, A3, A5, A6, A7, B1, B2, B3, B4, B5, B12, B7, B14, B15, B17, B18 | Eliminates every observed anomaly + closes two whole bug classes (orphan PIDs, gitignore pollution) + adds forensic + observability hygiene. ~4 hours, medium risk. |
| **(b) "Now" set only** | A1, A2, A3, A5, A6, A7, B1, B2, B3, B4, B5, B12 | Fixes only what we've directly observed. ~3 hours, lower risk. |
| **(c) Everything** | All of Tier A + Tier B except B6, B8, B10, B11, B13 | Largest blast radius, matches "every single fix" literally. ~5 hours, medium risk. Includes some prefetch of future sprint work. |
| **(d) Tier A only** | A1, A2, A3, A5, A6, A7 + A4 doc | Minimum viable. ~1.5 hours, low risk. Leaves Tier B for later. |

**Deferred regardless of choice:**
- B6 (engineer re-spawn on QA findings) — state-machine change, deserves own scoping
- B8 (graphify content-addressed cache) — performance optimization, not correctness
- B10 (cost telemetry) — own sprint (ABL-0013)
- B11 (parallel BL execution) — own sprint (ABL-0011)
- B13 (Triage agent) — own sprint (ABL-0002)

---

## Tracking checklist (update as fixes land)

- [x] A1 — non-FF auto-rebase — `ad7a335`
- [x] A2 — QA doctrine failure surfaced — `6a1a40c`
- [x] A3 — Milvus auto-restart preflight — `cbc2966`
- [x] A4 — score-only convenience path — `20c5476` (+ RECOVERY.md)
- [x] A5 — truthful `bl.done outcome` — `4fcd430`
- [x] A6 — reader dumps full event on failure — `5e652ce`
- [x] A7 — disk-persisted state — `a0deed3`
- [x] B1 — kill subprocess on cancellation — `b0b3914`
- [x] B2 — per-repo concurrency lock — `fe0a83b`
- [x] B3 — graphify writes to shared cache (not worktree) — `0bf3afb` (+ target `418ed91`)
- [x] B4 — AppV2 renders new event fields — `c73a2ad`
- [x] B5 — per-subprocess idle timeout — `ed80bec`
- [x] B7 — `.gitignore` preflight check (closed by B3 + target gitignore fix)
- [x] B9 — `/run-brief` idempotency — `4960c17`
- [x] B12 — `partial_resume` cross-check git log — `4305870`
- [x] B14 — harness SHA in trace meta — `7fce71b`
- [x] B15 — auto-archive traces on sprint_complete/aborted — `01bb5b4`
- [x] B16 — document `/decompose-brief` as plan-only path — covered in RECOVERY.md (`20c5476`)
- [x] B17 — UI Stop end-to-end (subsumed by B1) — `b0b3914`
- [x] B18 — operational logs out of `/tmp/` — `7919029`
- [ ] B6 — engineer re-spawn on QA findings (deferred)
- [ ] B8 — graphify cache reuse beyond path move (deferred)
- [ ] B10 — cost telemetry aggregation (deferred — ABL-0013)
- [ ] B11 — parallel BL execution (deferred — ABL-0011)
- [ ] B13 — Triage agent (deferred — ABL-0002)

---

*Authored: 2026-05-23, after Sprint 3 BL-0005 abort. Update this file as the ledger is worked through.*
