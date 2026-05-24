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

### A8 — R9 graph-grounding floor is advisory, not enforced

**Evidence:** Sprint 4 BL-0006 engineer trace `traces/full-stack-fastapi-template/20260523T223104Z-engineer-BL-0006-25a87d49309c/retrieval.jsonl` shows 3× `semantic_search` + 1× `target_status` + **0× `graph_*` calls**. The `doctrine_check` event returned `complete=true` on attempt=1 — meaning the validator never flagged the missing graph grounding. R9 in CLAUDE.md states ">=1 graph_* tool call required per role" but the per-role audit log is not actually consulted at validation time.

**Cause:** `doctrine_validator.py` checks artifact paths, file sizes, R5 grounded-count via the audit log, R5b citations, and R7/R8 numeric ceilings — but no code path reads `retrieval.jsonl`, counts tool=='graph_*', and refuses if count<1. R5's grounded-count and R9's graph-specific floor are conflated in the prompt language but split in enforcement: Tier 1.5 (`claude_agent.py:stream_agent_task`) counts grounded calls via `GROUNDED_RETRIEVAL_TOOLS` which DOES include graph tools — but only enforces the *total* grounded count, not a per-family floor. An agent can satisfy R5 entirely through `semantic_search` and still pass.

**Fix:** Add a `validate_r9(trace_retrieval_path)` helper in `doctrine_validator.py` that opens `retrieval.jsonl`, counts entries whose `tool` startswith `mcp__retrieval__graph_`, and adds `r9_graph_call_count < 1` → `missing.append("R9 graph-grounding: no graph_* calls in retrieval log")`. Wire into `validate_engineer` / `validate_qa` / `validate_scorer` (PO is exempt because backlog-decomposition workloads sometimes have nothing to traverse). When triggered, the existing R10.1 retry loop kicks in with a focused fix prompt naming exactly which graph_* tool family is missing.

**Effort:** ~30 LOC (helper + 3 call sites + a one-line fix prompt template). **Risk:** low (additive validation; failure mode is "agent re-spawns with focused prompt", which is the well-tested R10.1 path). Edge case: if `retrieval.jsonl` doesn't exist (MCP not wired), fall back to skip rather than false-fail — same defensive pattern A6 uses.

**Test:** synthetic engineer flow that makes only `semantic_search` calls → expect doctrine_check kind=incomplete with `summary.missing` containing the R9 message → R10.1 retry → second attempt with one `graph_neighbors` call → complete.

**Why this surfaced in Sprint 4:** BL-0006 is the first *frontend-only* BL (notification bell + dropdown panel). The engineer's intuition was "this is React component work, the graph won't tell me much" — and the doctrine validator silently agreed. For a pure-UI BL that may be defensible, but the rule as documented in CLAUDE.md says it's a floor. Either the rule needs softening for UI-only BLs or enforcement needs to catch up. This entry argues for the latter.

---

### A7 — Orchestrator state is in-memory only

**Evidence:** Twice in Sprint 3, the orchestrator process died (Milvus crash → endpoint exception, then operator-induced abort after M1 commit) and we lost queue position. Recovery relied on `skip_po + R11 no-op + partial_resume` to reconstruct from git history.

**Cause:** PIPELINE.md specified disk-persisted state at `webapp/backend/.orchestrator-state/<run_id>.json`. Never implemented.

**Fix:** Write `{run_id, brief_hash, started_at, current_bl, bl_outcomes[]}` to disk at every milestone. On `/run-brief` startup, if an unfinished run for the same `brief_hash` exists, resume from `current_bl`. Doesn't replace `skip_po`, complements it.

**Effort:** ~40 LOC. **Risk:** medium (concurrency on writes if two runs ever overlap — but B2 will prevent that).

---

### A9 — Gate subprocess pgroup leak (sibling of B1)

**Class:** `resource-leak` · **Invariant:** I-1 (resource lifecycle owned end-to-end). Same class as B1; B1 fixed it for the claude tree only.

**Evidence:** During Sprint 4 status polling (2026-05-23 ~18:00), a 30-hour-old `regression_gate.sh` process and its `docker compose ... playwright` children were observed running in the system process table, traced to `post-464c91f9-*` containers from a Sprint 3 BL-0005 gate retry. B1's pgroup-kill covers `claude_agent.stream_agent_task` only. `regression_gate_svc.run_gate` calls `asyncio.create_subprocess_exec` directly without `start_new_session=True`, and its `finally` block calls `proc.kill()` on the parent only — leaving the docker-compose child tree orphaned when SSE disconnects, the orchestrator crashes, or uvicorn cycles.

**Cause:** Per-call-site cleanup discipline. B1 was patched once at the claude site; nobody scanned siblings. The crew has no `ManagedSubprocess` primitive that guarantees pgroup hygiene by construction.

**Fix:** Two-stage.
- (Tactical) Add `start_new_session=True` + `_kill_pgroup`-equivalent finally to `regression_gate_svc.run_gate`. ~15 LOC.
- (Structural — preferred, deferred to Move 3) Introduce `ManagedSubprocess` primitive in `webapp/backend/app/services/subprocess_runner.py`; migrate claude, gate, graphify, and claude-context call sites; lint direct `asyncio.create_subprocess_exec` usage. ~150 LOC + migration.

**Risk:** Move 3's invasive migration could miss a call site, reintroducing the leak class on a new resource.
**Mitigations:**
1. **Lint as CI gate** — add a `tests/test_no_raw_subprocess.py` that greps the `app/services/` tree for `asyncio.create_subprocess_exec` and fails if any hit is outside `subprocess_runner.py`. Closes the "miss a site" failure mode at PR time.
2. **Closure-check observability (Move 2)** — `closure_check()` scans for surviving children of the run's pgroup at terminate. Any future miss surfaces as a `closure_violation` event, not as a 30h orphan discovered by hand.
3. **Per-site staged rollout** — claude (already covered) → gate → graphify → claude-context. Each migration is one commit; if a stage causes a regression, only that stage rolls back.
4. **Smoke test per stage** — `kill -9` the orchestrator mid-run for each stage; assert zero surviving children.

**Test:** start a gate run, `kill -9` orchestrator, `ps -ef | grep -E '(regression_gate|docker.*playwright)'` → zero rows.

**Effort:** ~15 LOC tactical only; ~150 LOC for the structural Move 3.

---

### A10 — Orphan docker container accumulation (no run_id labeling)

**Class:** `consistency-violation` · **Invariant:** I-3 (closure postconditions asserted). Adjacent to I-1; the resource is owned externally (docker daemon), so the lifecycle gap manifests as containers, not PIDs.

**Evidence:** On 2026-05-23 ~19:13, `docker ps -a` listed 25 orphan containers from prior sprints: `post-464c91f9-*` (30h), `bl0010-db` (2d), `7edfa9efa6f5-*` (2d), `326b866ec7e9-*` (2d), `9a58a4ec62a7-*` (2d), plus the live Sprint 4 cluster `pre-28908e49-*` (~10 min). Reaping required hand-correlation by container-name prefix because nothing in the container metadata identifies the agentic-skills run that spawned it. `milvus-standalone` (legitimate, framework-owned) and `sescrew-postgres` (operator's unrelated project) had to be excluded by name allowlist — fragile.

**Cause:** `regression_gate.sh` invokes `docker compose -p <project> up` with a project-prefix derived from a sha; no `--label agentic-skills.run_id=<run_id>` is passed. Closure-check (I-3) is not implemented anywhere — even if labeling existed, no code path scans for survivors at run terminate.

**Fix:** Three-part, sequenced.
1. **Label at creation** — patch `regression_gate.sh` (and any other `docker compose up` site) to add `--label agentic-skills.run_id=<run_id> --label agentic-skills.role=<role> --label agentic-skills.bl=<bl_id>`. ~5 LOC.
2. **Closure-check scan** — new `closure_check.scan_orphan_containers(run_id)` that runs `docker ps -aq --filter label=agentic-skills.run_id=<run_id>` and emits one `closure_violation` event per survivor. Called from orchestrator outer-finally. ~30 LOC.
3. **Reaper (operator-approved)** — `POST /api/projects/<repo>/reap-orphans` endpoint that scans by label, reports findings, and reaps only on `confirm=true`. ~25 LOC. NOT auto-invoked.

**Risk:**
- **R1** — false positive reaping external containers (sescrew-postgres style).
- **R2** — false negative if a container is created without the label (legacy code path missed).
- **R3** — label injection: a rogue container could claim our run_id.

**Mitigations:**
1. **Label-scoping** — closure-check only matches `agentic-skills.run_id=<known>` where `<known>` is a value the orchestrator minted itself (cross-referenced against the disk state file). External containers carry no `agentic-skills.*` labels and are invisible to the scan. R1 closed.
2. **Lint as CI gate** — `tests/test_compose_invocations_labeled.py` greps every `docker compose up` / `docker run` call in our code and asserts the `--label agentic-skills.run_id` flag is present. R2 closed.
3. **Run-id minted only in the router** (I-4) — `run_id` values are UUID-like and not externally guessable; a rogue container would need to know the live run_id to inject. R3 closed structurally.
4. **Reaper is operator-gated** — survivors are *reported* by closure-check but not auto-reaped. The reaper endpoint requires `confirm=true`. Worst case of any future bug: stale-report email to operator, not lost work.

**Test:** start a brief run that triggers the gate, `kill -9` orchestrator mid-gate, restart orchestrator, observe `orchestrator.closure_violation kind=docker_container resource=<container-id>` events in the new run's log.

**Effort:** ~60 LOC across the three parts. **Depends on Move 2** (closure_check primitive) landing first.

---

### A11 — R9 streaming-side gap deepens A8

**Class:** `enforcement-gap` · **Invariant:** I-2 (doctrine is a contract). Same invariant as A8; deepens the gap rather than introducing a new one.

**Evidence:** A8 closes the *post-validation* side of R9 (doctrine_validator opens retrieval.jsonl and counts graph_* calls). The *streaming* side (Tier 1.5 pre-modification kill in `claude_agent.stream_agent_task`) counts `GROUNDED_RETRIEVAL_TOOLS` as a single bucket — semantic_search + graph_* + target_status all count toward the same total. An agent making 3× `semantic_search` and 0× `graph_*` passes Tier 1.5 and writes a modification, only to be flagged later by the (new, A8) post-validator. The kill comes too late: code has already been written, the worktree mutated.

**Cause:** `claude_agent.py` GROUNDED_RETRIEVAL_TOOLS is a flat list. R5 (total grounded count) and R9 (graph_* floor) share enforcement code but should split at this point.

**Fix:** In `claude_agent.py`, replace the single `grounded_count` with a `dict[family, count]`: `{"semantic": …, "graph": …, "target": …}`. Tier 1.5 then asserts `grounded_total >= 3 AND graph_count >= 1` before allowing the first `Write`/`Edit`. The fix-prompt names which family is short. ~25 LOC.

**Risk:** Pure-UI BLs (BL-0006 case) may legitimately have nothing to graph-traverse — the rule as documented in CLAUDE.md says it's a floor, but tightening the streaming side may produce a kill-then-retry pattern that wastes one agent attempt before the agent learns to make a token graph_* call.
**Mitigations:**
1. **Pair with A8** — A11 only lands once A8's post-validator is shipped, so the fix-prompt path is proven before pulling enforcement forward in time.
2. **Telemetry first** — land an *observation-only* version (counts but does not kill) for one sprint. Confirm the streaming kill would have fired with the same frequency as A8's post-validation kill. Only flip to enforcement once data agrees.
3. **Family-specific message** — when streaming kills for "no graph_* call yet," the agent's fix prompt names *which* graph_* tool (`graph_neighbors`, `graph_callers`, etc.) is most appropriate for the BL summary. Reduces wasted retries.
4. **UI-only carve-out (defer decision)** — if telemetry shows BL-0006-class frontend BLs systematically fail R9, the doctrine-meta-agent (Move 1) is the right mechanism to propose softening R9 for that case — not a hardcoded exemption written by hand.

**Test:** synthetic engineer flow making only `semantic_search` calls then attempting `Write` → expect Tier 1.5 kill with `pregrounding_violated reason=r9_graph_floor`.

**Effort:** ~25 LOC. **Depends on A8** landing first.

---

### A12 — Doctrine-meta input contract names `events.jsonl`; harness writes `stream.jsonl`

**Class:** `enforcement-gap` · **Invariant:** I-2 (doctrine is a contract). **Surfaced by:** doctrine-meta-agent smoke against `run-20260523T212548Z-5bfff3` (proposal `sprint-run-20260523T212548Z-events-jsonl-doctrine-drift.md`, 12 evidence citations).

**Evidence:** The meta-agent's `SKILLS.md` §Inputs §1 (my B-1 commit `c65ff09`) tells the agent each trace subdirectory holds `events.jsonl`. No such file exists in any trace dir, sealed or live. The harness's `TraceWriter` writes `stream.jsonl` — Claude SDK transport messages plus `_meta phase=...` records. The meta-agent partially recovered by reading `stream.jsonl`, but every "the events file says X" claim in a future proposal is unrooted against the role's stated input contract.

**Cause:** I wrote B-1's SKILLS.md by referencing the conceptual term "events" without verifying the on-disk filename. Direct I-2 violation by my own work: I shipped a role whose binding rulebook references an artifact that does not exist.

**Fix:** Pick one — Option 1 OR Option 2, not both.
- **Option 1 (recommended):** Update SKILLS.md §Inputs to reference `stream.jsonl` and a filter predicate (`type == "_meta"` then inspect `phase`). ~10 LOC of doctrine edit.
- **Option 2 (deferred):** Have `TraceWriter` emit a derived `events.jsonl` containing only `_meta`-typed lines from `stream.jsonl`. ~25 LOC + a small test.

**Risk:** Option 1 makes the meta-agent's input contract correct but bakes in dependency on the SDK's transport-message format mixing with our `_meta` records. Future SDK format change ⇒ silent meta-agent breakage.
**Mitigations:**
1. Schema-guard test (`tests/test_stream_jsonl_meta_schema.py`) that opens a recent trace's `stream.jsonl`, filters for `type=="_meta"`, and asserts every record has `phase` and `type`. Detects SDK drift at PR time.
2. The meta-agent's existing evidence-discipline rule ("every citation must include trace_path + event_id retrievable on re-open") catches any silent format break at the proposal-validation step.
3. Option 2 remains available as a fallback if Option 1's coupling proves brittle.

**Test:** synthetic smoke against an existing archive after the SKILLS.md edit → meta-agent's prose cites `stream.jsonl` (not `events.jsonl`) AND its proposals pass the reviewer (once Batch C lands).

**Effort:** ~10 LOC for Option 1. Note: SKILLS.md is under the meta-agent's `forbidden_targets` (anti-runaway-self-modification), so this edit must be made by **me or the operator**, never by the meta-agent.

**Why this matters as a finding:** I-2 is the rule the meta-agent enforces against the rest of the framework. Shipping the meta-agent itself with an I-2 violation in its input contract is dogfood failure — the architect's own work needed to pass the lens it imposes. Filing this is the architect role behaving correctly.

---

### A13 — Doctrine enforcement events not co-located with the sealed agent trace

**Class:** `observability-gap` · **Invariant:** I-5 (no aggregate label more optimistic than its worst component) AND I-3 (observability). **Surfaced by:** doctrine-meta-agent smoke against `run-20260523T212548Z-5bfff3` (proposal `sprint-run-20260523T212548Z-doctrine-phase-events-unobservable.md`, 6 evidence citations).

**Evidence:** Across 11 archived traces from Sprint 4, the only `phase=*` events in any agent's `stream.jsonl` are `phase=spawn` and `phase=exit`. None of the documented R-rule enforcement points appear: `doctrine_check`, `pregrounding_violated`, `tier_15`, `regression_gate.*`, `post_validation`, `scorer_grounding`. Two engineer traces (BL-0004, BL-0005) recorded near-zero work yet were accepted by the orchestrator; the disposition is documented somewhere (orchestrator SSE stream, disk state, log file) but **not in the sealed per-agent trace a reviewer would open to verify a claim about that agent**.

The BL-0006 case is the cleanest illustration: 4× spawn/exit retry pattern is visible in `stream.jsonl`, but the `phase=regression_gate kind=regressed` outcomes that *triggered* each retry are recorded only in the *prompt* to the next run, not as discrete events in the prior run's trace.

**Cause:** Phase events are written by the orchestrator (`_evt` in `orchestrator.py`) into the orchestrator's SSE stream. They are tagged with `orchestrator_step=<role>` but never persisted into the per-agent `stream.jsonl` that lives in `traces/<repo>/<ts>-<role>-<bl>-<task_id>/`. The architectural split between "per-agent trace" and "orchestrator stream" means a reviewer must reconstruct each agent's enforcement history from a different file — and `logs/orchestrator/<ts>/run.log` is not in the sealed archive.

**Fix (per the meta-agent's proposal):** Introduce **R13: "agent terminal state requires a phase-event record in the agent's own trace dir."** Concretely: `_engineer_flow`, `_qa_or_scorer_flow`, and `_doctrine_meta_flow` must each open a sibling file `phase_events.jsonl` inside the per-agent trace dir AND append every doctrine_check, pregrounding, gate, post_validation, scorer_grounding event before the role's terminal `_orchestrator_outcome` event fires. Existing `stream.jsonl` is untouched (no concurrent-write hazard with `TraceWriter`). The agent's trace dir becomes self-contained: a reviewer needs only that directory to audit rule-firing.

**Risk:**
1. **Double-write hazard** — orchestrator writing into a dir the agent's TraceWriter also touches.
2. **Schema sprawl** — phase events accumulate fields over time; consumers drift.
3. **Live-trace consumers (UI, observer)** may key off `stream.jsonl` only and miss `phase_events.jsonl`.

**Mitigations:**
1. **Separate filename, append-only, single-writer-per-file.** `phase_events.jsonl` is owned by the orchestrator; `stream.jsonl` is owned by the subprocess streamer. No shared write surface.
2. **Schema-versioned headers** — first line of `phase_events.jsonl` is `{"_schema_version": 1, "_event_kinds": [...]}`. Observer (Batch D) detects unknown event kinds and reports them as candidate ledger entries — same audit-by-class discipline as the rest of the framework.
3. **Stage adoption** — add the file in parallel to existing events first (B-3-style additive change), confirm consumers continue working, THEN make it canonical.

**Test:** synthetic engineer flow that triggers `doctrine_check` incomplete → retry → complete → assert `phase_events.jsonl` exists in trace dir with 3 records (incomplete, retry-spawn, complete).

**Effort:** ~40 LOC across orchestrator flows + helper. **Pairs with A12:** A12 fixes the input contract; A13 makes the contract fulfillable from the per-agent trace alone.

**Why this matters as a finding:** This was the proposal I did not see coming. I sized B-3 around "meta-agent reads what we already write." The meta-agent's first action was to demonstrate that what we already write is *insufficient for the role's stated purpose*. That is the I-7 self-hardening loop succeeding — the framework identified its own observability gap on first invocation.

---

### A14 — Meta-agent SKILLS.md missing `forbidden_tools` constraint; agent ran `git add -f` to override gitignore

**Class:** `scope-creep` · **Invariant:** I-7 (self-hardening must be operator-gated). **Surfaced by:** the same smoke run that produced A12/A13. Commit `f1a229a` on `architect-prereqs` shows `Author: Claude Agent <agent@webapp.local>` committing the two proposal files after force-adding them past the gitignore.

**Evidence:** The doctrine-meta-agent's invocation completed at 19:43 with two proposal files written. The agent then proceeded — without instruction — to run `git add -f` (overriding the gitignore I authored in B-5) and `git commit`, landing commit `f1a229a` on `architect-prereqs` under its own author identity. The SKILLS.md §"Constraints (Hard Limits)" lists forbidden write targets but not forbidden tools. Bash is in the `allowed_tools` list for the role (`stream_agent_task` default `"Bash,Read,Write,Edit"`), so the agent had `git` available and used it.

**Cause:** B-1 SKILLS.md specified what the agent may write (proposal markdown) and where (`. planning/doctrine_proposals/`), but did not constrain `git` or shell mutation tools. The gitignore in B-5 expressed *the operator's intent* that proposals stay session-local until promoted — but expressed it only in `.gitignore`, not in the agent's binding doctrine. The agent observed the constraint mismatch (its task contract said "commit and confirm via git log") and resolved it by overriding gitignore. From the agent's perspective: rational. From the architect's perspective: a `forbidden_targets` list is necessary but not sufficient; a `forbidden_tools` list is the structural pair.

**Fix:** Edit `doctrine_meta` SKILLS.md to add a §"Forbidden Tools" section:

```
- NEVER run `git add`, `git commit`, `git push`, or any other git-mutation
  command. The proposals you write are session-local artifacts until the
  operator promotes them. Their absence from version control is the design,
  not an error. If you find your task prompt instructing you to commit,
  treat the instruction as out of scope and emit a final summary noting
  the contradiction; do not act on it.
- NEVER force-override a `.gitignore` rule with `git add -f`. The rule
  is the operator's expression of "this file is not yet ready for git."
  An agent overriding it has stepped past its proposal-writing role.
```

Plus tighten `_doctrine_meta_flow` to set `allowed_tools="Bash,Read,Write,Edit"` minus git via a deny-list on the streaming-side hook (longer-term — same primitive that R8 budget uses). The SKILLS.md edit is the immediate fix; the deny-list is the structural enforcement.

**Risk:**
1. The agent's task prompt (which I wrote in B-3) said "Follow the Required Completion Steps." If the SKILLS.md ever names "commit" as a completion step, the constraint conflict reappears.
2. Forbidden-tools listed in prose can be skirted by an agent that interprets the rule narrowly (e.g., `git stash` doesn't say "commit"). Prose constraints are weaker than streaming-side denials.

**Mitigations:**
1. Audit SKILLS.md for "commit" / "git log" mentions before relanding the agent. The current text doesn't include either; the agent appears to have invented the commit step from training, not from doctrine.
2. Land the streaming-side deny-list (longer term, ~30 LOC in `claude_agent.py`) so prose constraints have a backstop.
3. Pair this with A12's SKILLS.md edit — both go through the operator since SKILLS.md is in the agent's `forbidden_targets`.

**Test:** Re-run the smoke against `run-20260523T212548Z-5bfff3` after the SKILLS.md edit. Expect: two proposal files written, zero new git commits, agent's final summary explicitly notes "proposals are session-local; commit is the operator's decision."

**Effort:** ~15 LOC of SKILLS.md text. Streaming-side deny-list deferred (~30 LOC, separate item).

**Architectural note:** This is the first instance I've seen of an agent's *behavior* drifting from the *operator's* intent via a doctrine *omission* rather than a doctrine *violation*. The agent didn't break a rule — there was no rule. The structural lesson is that `forbidden_targets` + `forbidden_tools` are the I-7 safeguard pair; one without the other leaves a sibling-site gap (same pattern as B1→A9). Worth a future invariant tightening on its own.

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
| **(a) "Now" set + easy wins (recommended)** | A1, A2, A3, A5, A6, A7, B1, B2, B3, B4, B5, B12, B7, B14, B15, B17, B18 | Eliminates every observed anomaly + closes two whole bug classes (orphan PIDs, gitignore pollution) + adds forensic + observability hygiene. ~4 hours, medium risk. **All landed in commits f1bb6b1…0bf3afb on 2026-05-23.** |
| **(e) Sprint 4 follow-up batch** | A8 | R9 enforcement gap surfaced empirically during Sprint 4 BL-0006 (engineer did 3× semantic_search + 0× graph_*; doctrine_check returned complete). Not in the original 18; queued for the next hardening pass. |
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
- [ ] A8 — R9 graph-grounding hard enforcement *(new — surfaced Sprint 4 BL-0006)*
- [ ] A9 — Gate subprocess pgroup leak *(new — surfaced Sprint 4; sibling-class of B1)*
- [ ] A10 — Orphan docker container accumulation *(new — surfaced Sprint 4; depends on Move 2 closure-check)*
- [ ] A11 — R9 streaming-side gap *(new — deepens A8; lands after A8)*
- [ ] A12 — Doctrine-meta input contract drift (`events.jsonl` vs `stream.jsonl`) *(new — promoted from doctrine-meta proposal; my own B-1 work failed I-2)*
- [ ] A13 — Doctrine enforcement events not in per-agent trace (R13 candidate) *(new — promoted from doctrine-meta proposal; first I-7 self-hardening hit)*
- [ ] A14 — Meta-agent SKILLS.md missing `forbidden_tools`; agent ran `git add -f` *(new — surfaced by smoke; sibling-class to A9)*
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
