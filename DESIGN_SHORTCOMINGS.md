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

### A15 — R13: agents must not run history-rewriting git commands

**Class:** `scope-creep + silent-failure` · **Invariant:** I-1 (agents own files, never refs) + I-7 (self-hardening surface). **Surfaced by:** doctrine-meta-agent against api-keys sprint (proposal `sprint-run-20260524T014937Z-agent-initiated-rebase.md`, 4 evidence citations). **Operator-approved 2026-05-24.**

**Evidence:** Two QA agents (api-keys BL-0004 + BL-0006) ran `git rebase agentic-skills-work-v3` on their own `agent/<task_id>` branch during the doctrine-retry path. The rebase rewrote the SHAs the orchestrator was tracking; the subsequent FF-merge check failed with `HEAD is not a descendant of agentic-skills-work-v3 (agent rebased or reset history); merge would be non-ff`. The orchestrator caught the symptom via string-match in `missing`, but no R-rule prevented the cause. Identical pattern across two BLs → structural signal per I-6.

**Cause:** Doctrine omission. The role SKILLS.md (engineer/QA/PO) didn't tell agents the orchestrator owns refs. Agents reaching for `git rebase` to fix their own branch is rational from the agent's perspective; from the orchestrator's it creates the exact non-FF state A1 exists to recover.

**Fix:** Three-layer enforcement.
1. **Runtime kill** (`0e6bab6`): new `FORBIDDEN_GIT_RE` in `claude_agent.py` matched against `Bash` tool_use `command`. Streaming-kill emits `phase=forbidden_git_op kind=killed` and `_kill_pgroup`s the agent. Anchored on the 7 history-rewriting verbs: rebase, reset --hard, push --force/-f/--force-with-lease, filter-branch, commit --amend, update-ref, tag -d, branch -D. Read-only git unaffected.
2. **Role doctrine** (`68a1f11`): new `## Forbidden Tools (R13)` section added to engineer/QA/PO brownfield SKILLS.md naming the seven commands + pointing at the orchestrator's A1 auto-rebase as the correct path.
3. **Binding doctrine** (`86afca7`): new R13 row in CLAUDE.md R-rule table + new "Tightened scope (post-R13)" section in ARCHITECTURE_INVARIANTS.md I-1 making the agent–orchestrator ref boundary explicit.

**Risk:** false positives on benign uses; cross-platform regex behavior; agents may try to evade by chaining commands. **Mitigations:** anchored regex (18-case test passes); kill emits structured event so the trace explains the agent's exit; follow-up framework-reviewer (Batch C) can spot evasion patterns from `forbidden_git_op` events vs commit history.

**Test:** synthetic engineer prompted to rebase → streaming-kill fires → `phase_events.jsonl` records `phase=forbidden_git_op kind=killed`. Regex unit tests pass (9 positive, 9 negative, `0e6bab6`).

**Rollback:** revert the three commits. Pure runtime guard + doctrine text; no persistent state affected.

---

### A17 — No durable record of the sprint brief (operator intent)

**Class:** `observability-gap` · **Invariant:** I-3 (durability of artifacts intended to persist) + I-4 (single source of identity for a run). **Surfaced by:** operator question 2026-05-24 mid-RBAC-sprint — "which REQUIREMENTS.md file are you working with when implementing a new feature?"

**Evidence:** The two real-sprint briefs I authored in this session (`/tmp/api-keys-brief.md`, `/tmp/rbac-brief.md`) live only on `/tmp/`. They were POSTed verbatim into the `brief` field of `/api/projects/<repo>/run-brief` and are now embedded inside each PO trace's `stream.jsonl` and `meta.json.prompt` field — but no canonical, version-controlled record exists at the agentic-skills repo root. Consequences:
1. **No version history of what was asked for** beyond grepping trace archives.
2. **No reviewable artifact before the sprint runs.** A bad brief is invisible until the PO has interpreted it.
3. **Cross-sprint intent is invisible.** Two briefs that together imply a third gap don't surface that gap.
4. **The PO's `BACKLOG.md` and `SPRINT_PLAN_CN.md` are the *interpretation*, not the *original*.** Drift between intent and interpretation is unreviewable.

The current `briefs/` top-level dir holds **old-harness role-work-packets** (`engineering-work-packets/`, `qa-work-packets/`), not sprint briefs — overloading the name would conflate two unrelated artifacts.

**Cause:** The orchestrator accepts the brief as an inline string (`RunBriefRequest.brief: str`) and never persists it. The PO trace is the only durable record, and it's inside `webapp/backend/traces/`, not in the agentic-skills source tree where governance lives.

**Fix:** On every `/run-brief` invocation:
1. After the PO worktree is created (in `orchestrator._po_flow`), the server writes the brief verbatim to **`<worktree>/<artifact_dir>/sprint_briefs/<run_id>-<slug>.md`** — that is, into the target repo's brownfield artifact tree. The brief describes a target-repo feature; it belongs alongside `BACKLOG.md`, the per-BL `codebase_context.md` files, and the eventual feature code on the target's agent branch. **NOT** in the agentic-skills source tree, which holds only doctrine + ledger + framework code.
2. The file carries a YAML frontmatter header with `run_id`, `project_name`, `repo`, `started_at`, `brief_hash` so each brief is self-describing.
3. The orchestrator emits an `orchestrator.brief_persisted` SSE event (tagged `orchestrator_step=po`) carrying the worktree-relative path; UI + observer can surface it.
4. The PO's existing copy-back path (`shutil.copytree wt/<art> → repo_dir/<art>`) and `git add <art>` flow naturally pull the brief into the PO's import-backlog commit. The brief lands on the target's `agent_branch` (e.g. `agentic-skills-work-v3`) alongside the PO's other artifacts.
5. The server (orchestrator) does NOT touch the agentic-skills repo's index. The brief lands on the target via the existing PO commit; the target's branch lifecycle is operator-owned.

**Location correction (initial draft was wrong):** an earlier version of A17 had the server write to `<agentic-skills>/sprint_briefs/<run_id>-<slug>.md`. That conflated framework-level governance (doctrine, ledger, invariants — agentic-skills concerns) with target-level intent (feature briefs — target repo concerns). Operator-flagged 2026-05-24 mid-RBAC-sprint. Implementation now writes to the target's `_brownfield/sprint_briefs/`. Backfilled briefs in `agentic-skills/sprint_briefs/` (api-keys + RBAC) are transitional records; they will be moved into the target's `_brownfield/sprint_briefs/` after the RBAC sprint completes.

**Risk:**
1. **Brief size**: massive briefs (50+ KB) clutter the repo. Mitigation: leave it; large briefs are signal that scope is too big, not noise.
2. **Naming collisions**: `<run_id>` is unique-by-construction (timestamp + 6-char hex), so collisions impossible. Mitigation: built-in.
3. **Drift between persisted brief and PO interpretation**: by design — that's exactly the diff the operator would want to review. The persisted brief is the contract; the BACKLOG.md is the agent's reading of it.
4. **Operator forgets to commit**: same risk as today's doctrine proposals. Mitigation: framework-reviewer (Batch C, future) can flag uncommitted briefs from completed runs.

**Mitigations:** all four above are first-class addressed.

**Test:** kick off a sprint with `curl -d '{"brief": "<text>", ...}'` and verify `sprint_briefs/<run_id>-<slug>.md` exists with correct frontmatter + content. SSE includes `orchestrator.brief_persisted` event before `index_initial.start`.

**Effort:** ~30 LOC (router endpoint + slug helper) + `sprint_briefs/README.md` + `.gitignore` carve-out so accidental `*.md` rule additions don't sweep this directory.

---

### A16 — R5b first-attempt pass rate at 38%; bake citation template into SKILLS.md

**Class:** `enforcement-gap` (rule fires; prompt didn't teach the rule) · **Invariant:** I-2 (doctrine is a contract). **Surfaced by:** doctrine-meta-agent against api-keys sprint (proposal `sprint-run-20260524T014937Z-r5b-prompt-doctrine-drift.md`, 10 evidence citations). **Operator-approved 2026-05-24.**

**Evidence:** Across 17 traces in the api-keys sprint, 10 hit `doctrine_check incomplete attempt=1` on the R5b citation requirement; 100% recovered on first retry. First-attempt pass rate 6/16 ≈ 38%. Cost: 30–90s per BL + a re-invocation with full context. The rule worked; the prompt didn't teach it. Honest waste.

**Cause:** Engineer/QA/PO SKILLS.md described artifacts and rubrics but never said "every artifact must end with a `## Retrieval evidence` footer of ≥3 bullets." Agents learned R5b by failing it.

**Fix:** Embedded artifact-template `## Required Retrieval Evidence Footer (R5b)` section in engineer/QA/PO brownfield SKILLS.md (`68a1f11`). Template:

```
## Retrieval evidence
- [retrieval: <tool_name>] — <one-sentence summary>
- [retrieval: <tool_name>] — <one-sentence summary>
- [retrieval: <tool_name>] — <one-sentence summary>
```

Bullets must correspond to retrieval calls that actually appear in `retrieval.jsonl`; fabricated citations are blocker-grounds for the framework-reviewer (Batch C).

**Risk:** template gaming (bullets without backing calls); over-prescriptive artifact shape; brownfield-vs-greenfield scoping. **Mitigations:** streaming-side R5/Tier-1.5 still counts actual grounded calls (template change only addresses the citation-in-artifact half); the rest of artifact-spec is unchanged; only brownfield SKILLS.md edited. Scorer has no SKILLS.md (its prompt comes from `build_score_prompt_brownfield` + rubric); scorer-side R5b reduction handled separately if its first-attempt rate also shows the pattern.

**Test (named acceptance criterion):** next full sprint's R5b first-attempt pass rate rises from 38% to ≥80%. If it doesn't, the template wording is wrong, not the structural premise.

**Rollback:** remove the `## Required Retrieval Evidence Footer (R5b)` section from the three SKILLS.md files. R5b rule and enforcement point unchanged.

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
- [x] A10 — Orphan docker container accumulation — `ff04634` (M2-1 labeling) + `616e46f` (M2-2 scan) + `1764ab3` (M2-3 hook). Reaper endpoint deferred (operator-gated by design).
- [ ] A11 — R9 streaming-side gap *(new — deepens A8; lands after A8)*
- [ ] A12 — Doctrine-meta input contract drift (`events.jsonl` vs `stream.jsonl`) *(new — promoted from doctrine-meta proposal; my own B-1 work failed I-2)*
- [x] A13 — Doctrine enforcement events not in per-agent trace — `570b228` (M2-4 `phase_events.jsonl`). R13 doctrine codification deferred (operator's call; the mechanism is now in place).
- [ ] A14 — Meta-agent SKILLS.md missing `forbidden_tools`; agent ran `git add -f` *(new — surfaced by smoke; sibling-class to A9)*
- [x] A15 — R13: agents must not history-rewrite — `0e6bab6` (streaming kill) + `68a1f11` (SKILLS.md) + `86afca7` (CLAUDE.md + INVARIANTS)
- [x] A16 — R5b citation template baked into SKILLS.md — `68a1f11`. Acceptance criterion measurable on next sprint (first-attempt pass rate ≥80%).
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
- [x] A19 — per-feature BL numbering must reset to BL-0001 — `58d9468`
- [x] A20 — canonical `brief.md` at `_brownfield/features/<slug>/` root — `58d9468`
- [x] A21 — regression gate no longer falsely green on non-zero exit (I-5) — `9142263`. Verified live in run-20260524T180834Z-3bbf81 (gate correctly emitted `regressed` 3×).
- [x] A22 — `_compose_project_prefix` lowercased; docker-compose accepts ISO timestamps in run_id — `9142263`. Verified live (containers ran with `agentic-skills-...t180834z-...` lowercase).
- [x] A23/A24 — `events.jsonl` untracked on target's `agent_branch`; local `.git/info/exclude` entry — target commit `b2c79d4`.
- [x] A25a — `_extract_test_failures` priority-orders infra markers, gate-wrapper pseudo-tests, TS errors before pytest/Playwright — `58d9468`.
- [x] A25b — new `kind="infra_fail"` distinct from `regressed`; orchestrator retry loop already gated on `regressed` so infra failures auto-route to awaiting_review — `9142263` + `58d9468`.
- [x] A26 — pre-flight disk check (`_MIN_FREE_GB=5.0`) before gate spawn — `9142263`.
- [x] WI3A — `validate_engineer` rejects commits touching sibling `_brownfield/features/<other>/` paths; PO prompt warns of the boundary — `58d9468`.
- [ ] **A27** — Per-feature branch isolation off `main_ref` (deferred). Current model: every sprint forks from shared `agent_branch`, which accumulates prior PO commits + merged BL work. Doctrine + WI3A provide logical isolation; branch-level isolation would provide structural guarantee. ~200 LOC across `git_worktree.py`, `orchestrator.py`, `closure_check.py`, `repo_config.py`. **Defer until parallel sprints become a real workload.**
- [ ] **A28** — Playwright workers = 1 in `regression_gate.sh`. Bump to `--workers 4` for 3-4× gate speedup. ONE-LINE FIX. Verifiable: time before/after on identical sprint. Risk: low (some flake risk under contention; mitigate with `--retries 1`).
- [ ] **A29** — PRE-phase result caching keyed on `agent_branch` HEAD SHA. Current gate re-runs full PRE for every BL even when baseline hasn't moved. Cache hit → skip PRE worktree+stack+tests entirely (~50% gate time reduction per sprint after first BL). Risk: cache invalidation on `agent_branch` mutation; mitigate with SHA-based key + TTL.
- [ ] **A30** — Test Impact Analysis (TIA). Map engineer's `git diff --name-only` → affected playwright spec files. Run only those. 5-20× reduction on focused changes (e.g. editing only `app/api/routes/items.py` → run only `items.spec.ts`). Heuristic mapping (file-prefix or test-name correspondence) is the cheap start; explicit mapping table in `.agentic-skills.json` is the durable version. Risk: under-inclusion misses cross-cutting regressions; mitigate with full-suite fallback on schema/auth/UI-system-level changes.
- [ ] **A31** — Tiered gate: per-BL fast (unit + smoke ≤3min), full e2e once at sprint-completion or async post-merge. Restructures the "every BL is production-ready" contract — appropriate when the crew has matured. Out-of-band fix path: revert sprint if post-merge full e2e regresses. Risk: medium (changes the merge contract). Defer until A28 + A30 are in place and the crew has demonstrated consistent BL-quality.

---

## Gate throughput note (2026-05-24)

The brownfield target's gate runs **~79 playwright e2e tests at 1 worker, PRE+POST per BL**. Per-BL gate time = 80-160 minutes. For an 11-BL sprint this projects to 17-33 hours of gate wall-time alone before any retries. This is **the single biggest throughput lever** in the current framework. See `.claude/memory/arch_gate_throughput.md` for cross-session context and industry comparison.

---

*Authored: 2026-05-23, after Sprint 3 BL-0005 abort. Update this file as the ledger is worked through.*

*Updated 2026-05-24: A19, A20, A21, A22, A24, A25a/b, A26, WI3A landed (commits 9142263 + 58d9468). A27 (per-feature branch isolation) and A28-A31 (gate throughput) filed as open follow-ups.*

- [x] **A32** — Gate hangs on QA test design defects (`TestClient(app)` connection leak + Alembic DDL with session-scoped fixture). **Class:** I-2 + I-3. **Evidence:** sprint `run-20260524T220528Z-f56070` hung 30+ min on `tests/api/routes/test_workspaces_qa.py::test_alembic_upgrade_downgrade_upgrade_round_trip`; reproduced locally. **Root cause:** `_add_member` helper instantiated `TestClient(app)` without `with` context manager across 7 tests → leaked ASGI lifespan-bound DB connections → 8th test's `command.downgrade()` blocked on `AccessExclusiveLock` for `DROP TABLE workspace`. **Defense-in-depth fix:** (target commit `c7ea13e` on `agentic-skills-work`) `scripts/regression_gate.sh` now runs pytest with inline-installed `pytest-timeout` and `--timeout=120 --timeout-method=signal` + shell `timeout 900` backstop; (architect-prereqs commit `7ffad52`) new R14 in QA `SKILLS.md` codifies three sub-rules (R14.1 TestClient hygiene, R14.2 no Alembic DDL with shared session, R14.3 timeout opt-out discipline). Detail in `.claude/memory/arch_test_hygiene.md`.
- [ ] **A33** — `webapp/backend/logs/orchestrator/.latest` symlink not updated to current run; points at May 23 BL-0006 log. Minor observability issue. Defer.
- [ ] **A35** — Untracked `graphify-out` symlink in agent_branch worktree blocks FF-merge of agent branches that committed it. **Class:** I-1 (artifact leakage) + doctrine/reality gap. **Evidence:** sprint `run-20260525T015039Z-1e306f` aborted on BL-0005 after engineer wrote good code (170 tests green on POST gate). `merge_to_target kind=error error="The following untracked working tree files would be overwritten by merge: graphify-out"`. **Root cause:** harness `.gitignore` (commit `2a9dc81` on `agentic-skills-work`) adds only `_brownfield/features/*/events.jsonl` — no `graphify-out` entry. Per CLAUDE.md the symlink is *supposed* to be unsweepable by `git add -A` ("the worktree only ever contains a single symlink; the actual cache lives outside") but the protective ignore was never added. Agent worktree's indexer creates the symlink → `git add -A` sweeps it in → branch commits a tracked `graphify-out` → FF-merge into `agentic-skills-work` (which also has an untracked `graphify-out` from its own indexer) refuses. **Impact:** silently kills any BL whose agent_branch happened to materialize the symlink before commit. BL-0005 in this sprint passed engineer + 1 retry + green gate but lost the merge step, ending the sprint. Same failure mode possible for every future BL until ignore lands. **Required fix:** (1) append `graphify-out` to harness `.gitignore` on `agentic-skills-work` (1 line); (2) pre-merge in orchestrator's `merge_to_target` step, strip the symlink from the source branch if present (`git rm --cached graphify-out`) before attempting FF-merge — closes the door for branches that already committed it; (3) update CLAUDE.md's "Persistence layout" claim to be accurate or actually enforce it. **Priority:** high — silently aborts sprints mid-flight.
- [ ] **A37** — QA `merge_to_target` errors are downgraded to non-fatal; sprint continues with QA-test commit silently lost. **Class:** I-3 (closure asymmetry) + observability gap. **Evidence:** sprint `run-20260527T160519Z-9811fa`, BL-0002 (`merge_to_target ok:False kind:error` at 17:55:34, immediately followed by `orchestrator.qa.done` + `reindex_after_qa.start`) and BL-0007 (same pattern at 22:02:29). In both cases QA's `regression_gate` was GREEN, doctrine_check complete, but the merge step errored — and the orchestrator advanced through `qa.done` → reindex → scorer → `bl.done` → next BL anyway. Result on `agentic-skills-work-documents_2`: engineer's BL-0002 commit `9f6d821` IS on branch, but no `qa(BL-0002, ...)` commit landed (similar for BL-0007). QA's added tests (the regression-reinforcement coverage that should compound across the sprint) never reached the branch. **Asymmetry with engineer-merge-failure:** documents_1's BL-0005 (`run-20260525T015039Z-1e306f`) ABORTED the entire sprint when engineer's `merge_to_target` errored (see A35); here, QA's merge erroring is silently swallowed. Two paths, two policies, one shipping criterion (the branch). **Impact:** every BL whose QA-merge errors loses its test reinforcement; the branch ships with engineer code that no QA cycle ever re-validated against subsequent BLs. This pattern occurred 2× this sprint; will recur. **Required fix:** (1) make QA `merge_to_target` failure either retry (with R10 budget) or abort the sprint — never silently swallow, per I-3 (the orchestrator must not advance past a phase whose final write to the agent_branch failed); (2) emit a distinct `qa.merge_error` _meta event surfaced in UI/logs (not buried in the generic merge_to_target event); (3) make `bl.done` post-condition include "no `merge_to_target ok:False` events in this BL's window" so downstream phases don't run on a partially-merged BL. **Priority:** high — silently degrades QA coverage on every sprint; meta-agent does NOT surface this because it's an orchestrator merge bug, not a doctrine-rule firing pattern.
- [ ] **A38** — *withdrawn.* What looked like a frontend-specific layer-coverage gap on BL-0008 (`run-20260527T160519Z-9811fa`) is already covered by A36's required fix (#2), which lists "route layer" among the layers PO grounding must cover. Doctrine-meta-agent independently mapped the BL-0008 frontend failure to A36 in its 23:25:45 run. No new entry needed.
- [ ] **A39** — `regression_gate` parser conflates *build failure* with *all-tests-regressed*, diluting R10 retry signal. **Class:** I-2 (doctrine contract: signal quality) + parser bug. **Evidence:** sprint `run-20260527T160519Z-9811fa`, BL-0008 engineer attempt #1 (`regression_gate` at 22:15:44). `reason: 161 regression(s); post exit=1`, `regressions[]` lists 50 test names. Actual `post_tail` shows `tests/gate::build FAILED` due to a single stale `routeTree.gen.ts` — when the frontend build fails, no test runs, so the parser counts every PRE-pass-POST-not-run case as a regression. R10 retry prompt receives 161 noisy test-name items instead of "the frontend build doesn't compile, here is the TS error." Engineer still recovered on attempt #3 by reading `post_tail`, but the retry budget paid a tax on attempt #1's signal dilution. **Required fix:** in `webapp/backend/app/services/regression_gate.py`'s post-parsing — detect a build/lint sentinel failure (`tests/gate::build FAILED`, `tests/frontend::lint_typecheck_build FAILED`); when present, set `regressions: []` (empty), set `reason: "build failed; downstream tests not run"`, and ensure `post_tail` is truncated to the actual error block, not the 5 KB of container-orchestration noise that follows. Optionally add a `gate_failure_class: "build" | "lint" | "test"` field that the engineer retry prompt builder can switch on to produce role-specific fix guidance. **Second sub-mode (39b — empty extraction):** the inverse also occurs — REAL test failures, but `regressions: []` comes back empty with a non-zero count, so the engineer's retry prompt names a count but no identities. The fix must ALSO ensure the parser reliably extracts the actual `FAILED <nodeid>` lines into `regressions[]`; an empty list with a positive failure count is itself a parser bug and must never be emitted (assert `len(regressions) == count` or downgrade the kind to `inconclusive` with the raw `post_tail`). **Priority:** **HIGH** (escalated 2026-05-30 — was medium). **Now a 4-instance class** that no longer merely wastes retries but *causes sprint aborts*: documents_2 BL-0008 (`run-20260527T160519Z-9811fa`, 39a "161 regressions"), intelligent_kanban BL-0006, time-tracking BL-0012 (biome+routeTree), and **time-tracking BL-0014** (`run-20260530T133341Z-f97e8c`, 39b — gate reported "2 new failure(s)" with `regressions: []` empty; the real failures were `test_time_settings.py::test_policy_allows_compliant_entry_and_rounds` on a `Z`-suffix isoformat bug + a `test_time_entries` assertion). In BL-0014 the empty `regressions[]` left the engineer with no test names, so it **ran the full gate itself to self-diagnose** — and was then killed by the B5 idle-timeout while blocking on that gate (**A45**), discarding a verified fix and aborting the sprint. A39 is the upstream cause in that A39 → self-run-gate → A45 idle-kill → abort chain. The metric-corruption and retry-tax harms remain; the abort harm is the new reason for HIGH.
- [ ] **A40** — Engineer prompt does not direct agents to use available auto-fix tooling (`biome --apply`, `ruff --fix`, `eslint --fix`, etc.). **Class:** I-2 (doctrine contract: tooling discoverability). **Evidence:** sprint `run-20260527T160519Z-9811fa`, BL-0008 engineer attempt #2 (`regression_gate` at 22:31:55). Failure was `src/routes/_layout/documents/folder.$id.tsx:3:1 ✗ Sort the imported names` from biome — and biome's own output included `i Safe fix: Organize imports and exports (Biome)`, signaling the formatter has an auto-fix available via `biome check --apply`. Engineer manually re-wrote the import statement instead of running the auto-fixer. Lost an entire retry cycle (~10 min wall-time) on a one-character problem the formatter could fix in zero LLM tokens. **Required fix:** add a clause to `webapp/backend/app/services/prompts_brownfield.py:211 build_engineer_prompt_brownfield`: *"If a gate failure reports a biome/ruff/eslint/prettier rule with 'Safe fix' or 'auto-fix available', run the formatter's --apply / --fix flag and re-stage before editing manually. Manual edits are reserved for failures the formatter cannot auto-fix."* No SKILLS.md change needed; this is engineer-prompt scope. **Priority:** medium — cheap to ship, recurring savings (any lint-class regression).
- [ ] **A41** — Doctrine-meta-agent's per-invocation prompt contradicts its own SKILLS.md; `proposals_count: 0` event does not preserve the meta-agent's reasoning for *why* zero. **Class:** I-2 (doctrine contract: prompt ambiguity) + observability gap. **Evidence:** sprint `run-20260527T160519Z-9811fa`, `orchestrator.doctrine_meta` run at 23:25:45. Two distinct issues: **(a)** The per-invocation prompt assembled in `orchestrator.py:_doctrine_meta_flow` instructs the agent to "Follow the Required Completion Steps in your SKILLS.md" — which then tell it to `git add -A` + `git commit`. SKILLS.md's *Forbidden Tools* section explicitly forbids both. The agent resolved the contradiction by citing A14 precedent (SKILLS.md hard-limits override per-invocation imperatives) and not committing — but this required reasoning to navigate, and a less-careful future revision of either doctrine file could flip the resolution. **(b)** The agent ran 15 tool calls and produced a thoughtful final message: "Analysis complete. Findings map to existing ledger entries (A8/A11 for R9 graph-grounding silent pass; A13 for partial phase_events coverage; A36 for layer-coverage breadth). No new proposal-worthy patterns surfaced — duplicates are forbidden per SKILLS.md." This justification is in the trace's `stream.jsonl` (`result.result`) but **NOT in the `orchestrator.doctrine_meta.proposals` event** that the orchestrator emits — which carries only `{proposals_count: 0, valid_count: 0, proposals: []}`. An operator reading only the events.jsonl cannot tell whether zero proposals means "agent worked correctly and found no new patterns" or "agent crashed silently / wrote bad files / hit timeout." This is exactly the same observability-gap class as A13. **Required fix:** **(a)** Remove the imperative `git add -A` / `git commit` from the Required Completion Steps in `skills/brownfield/brownfield-production-incremental-doctrine-meta/SKILLS.md`; replace with "emit final JSON summary to stdout; the orchestrator writes proposals to disk and records the run, not the agent." Aligns the doctrine with what already works. **(b)** Extend the `orchestrator.doctrine_meta.proposals` event payload with a `justification` field populated from the agent's final `result.result` text — even ~200 chars of the agent's own reasoning makes the event interpretable standalone. Optionally also add `findings_mapped_to_ledger: ["A8", "A11", ...]` extracted from the same text via a regex on `A\d+` mentions, so the event is queryable. **Priority:** medium — meta-agent works today, but the contradiction is a latent bug and the observability gap blocks honest "is the self-hardening loop working?" diagnosis (which I myself wrongly answered "no" before reading the trace).
- [ ] **A36** — PO Codebase Intelligence Protocol satisfies R5 by retrieval *count* but not by layer *coverage* — convention queries miss the migration / test layers, producing engineer commits that mirror model conventions but violate them in adjacent files. **Class:** I-2 (doctrine contract: rule wording is incomplete) + Pattern Fidelity (brownfield rubric axis 1) + Invariant Preservation (axis 4). **Evidence:** sprint `run-20260527T160519Z-9811fa`, BL-0001 first attempt commit `653c7f3` ("Workspace + WorkspaceMember scaffolding behind FEATURE_DOCUMENTS_HUB"). Regression gate `kind=regressed`, 16 failed / 2 errored. **Root cause (verified, full confidence):** engineer added `class WorkspaceMember(SQLModel, table=True)` with no `__tablename__` override — SQLModel/SQLAlchemy default is lowercased class-name with no separator → table name `workspacemember`. Engineer's Alembic migration `a1b2c3d4e5f6_add_workspace_tables.py` calls `op.create_table('workspace_member', ...)` (snake_case with underscore). Existing target convention, established by `e2412789c190_initialize_models.py`, is `op.create_table("user", ...)` and `op.create_table("item", ...)` (single-token lowercase, zero `__tablename__` in any existing model). Mismatch → POST gate emits `INSERT INTO workspacemember ...` against a DB that only has `workspace_member` → `psycopg.errors.UndefinedTable`. **Why R5 missed it:** PO's brownfield doctrine v1.1 requires ≥3 grounded retrieval calls before Write/Edit (Tier 1.5 + post_validation), but the count rule does not require coverage **breadth**. PO satisfied R5 with three model-layer chunks from `models.py` (Item family) and produced an `eng_patterns.md` analog citing model lines only — never retrieved an `op.create_table` chunk from `alembic/versions/`, so the convention the engineer had to match was invisible. **Cascade:** session-scoped `autouse=True` `db` fixture in `conftest.py` (verified line 15) ran `delete(WorkspaceMember)` in teardown → DELETE on non-existent table → SessionTransaction enters DEACTIVE → 10 unrelated `tests/crud/test_user.py` tests then fail with `PendingRollbackError` on `session.commit()`. The 10 user-test failures are amplification, not root cause. Diagnosis tree collapses to one defect; one model/migration-name fix would have made all 16 failures vanish. **Impact:** every brownfield BL that adds a new SQLModel `table=True` class is at risk of the same defect class — model naming and migration naming are governed by two different conventions in this template, and PO's current grounding floor doesn't force the engineer to see both. **Required fix (4 parts, in order):** **(1)** this ledger entry (commit attached). **(2)** PO prompt update in `webapp/backend/app/services/prompts_brownfield.py:110 build_po_prompt_brownfield` — extend the Codebase Intelligence Protocol from "≥3 grounded retrieval calls" to "≥3 calls covering ≥3 of {model layer, migration layer, test layer, route layer, dependency layer}; cite at least one chunk per relevant layer for any BL that introduces new persistent state." Wording lands in the PO instructions; R5 count check unchanged in `doctrine_validator.py` but augmented with a `_check_layer_coverage` helper that scans `_brownfield/features/<slug>/<BL>/codebase_context.md` for citations to each layer the BL touches. **(3)** Engineer prompt addendum in `webapp/backend/app/services/prompts_brownfield.py:211 build_engineer_prompt_brownfield` — add an explicit "Persistent-state consistency rule" clause: *"If you introduce a SQLModel class with `table=True`, the Alembic migration's `op.create_table('<name>', ...)` MUST equal either `__tablename__` (if you set it) or the SQLModel default (the lowercased class name with no separator). Verify against existing `op.create_table` calls in `backend/app/alembic/versions/` before writing the migration."* **(4)** Pre-merge validator in `webapp/backend/app/services/doctrine_validator.py:189 validate_engineer` — new check `_check_sqlmodel_tablename_consistency(changed_files)`: for each newly-added/modified file under `backend/app/models.py`, parse for `class X(... table=True)` and any `__tablename__ = "y"`; for each newly-added file under `alembic/versions/`, parse for `op.create_table("<n>", ...)`; assert every new model has a matching migration table at the right name. Failure adds an entry to the role's `_finalize` accumulator with `kind="incomplete"` — triggers R10.1 doctrine retry with the mismatch named in the fix prompt. **Long-run replacement:** ABL-0003 / `ARCHITECT_PLAN.md` Batch B doctrine-meta-agent should be able to propose fixes (2) and (3) autonomously by reading regression payloads + diffs; fix (4) is the kind of static rule that should land as a generated validator. Until that exists, the four-part fix is operator-driven. **Priority:** high — silently produces engineer commits that fail gate for the same structural reason on every new-table BL; budget cost is one full retry per occurrence (PRE+POST × ~8 min).
- [ ] **A43** — Doctrine-meta-agent generated a structurally rigorous proposal whose central evidence is contradicted by its own citations; the existing `## Evidence Discipline` section does not explicitly forbid schema-uniformity assumptions across tools. **Class:** I-7 (self-hardening) + observability/quality gap. **Evidence:** sprint `run-20260528T013535Z-ed1a60`, meta-agent produced `.planning/doctrine_proposals/run-20260528T013535Z-graph-retrieval-payload-gap.md` (moved to `rejected/` in this commit) claiming `graph_neighbors`, `graph_summary`, and `graph_find_similar` log only `{ts, tool}` (no input args, no result count) and proposing a `retrieval.jsonl` schema extension. **Architect verification (this session):** spot-checked the literal cited lines in `webapp/backend/traces_archive/run-20260528T013535Z-ed1a60/*/retrieval.jsonl`. 100% of 19 graph_* entries across the sprint carry both `n` (result count) and `path|symbol` (input). Failure mode reconstructed: the meta-agent assumed `semantic_search`'s field convention (`n_hits`, `with_n_results`) generalizes to graph_* tools, counted occurrences of `with_n_results` literally, observed 0 in the graph_* slice, and reported "field missing" without ever reading individual graph_* records. The proposal's 10 citations index aggregate counts, not the per-record evidence its absence-claim requires. **Why existing Evidence Discipline did not catch it:** the section forbids hallucinated citations and demands N citations for an N-instance claim, but does not name the failure class of "true citations supporting a false generalization." The reviewer (architect) caught the error at operator-review time by re-reading the cited files — the rule worked at the review boundary but not at the authoring boundary. **Impact (I-7):** the meta-agent is the self-hardening mechanism. If proposals routinely require operator forensic verification of every absence-claim, the loop degrades into adversarial fact-checking rather than judgment on real signal, and trust in autonomous proposal generation falls. n=1 today; do not over-engineer, but do harden the prompt so the next failure is a different class. **Required fix (Layer 1 only):** extend `## Evidence Discipline` in `skills/brownfield/brownfield-production-incremental-doctrine-meta/SKILLS.md` with (a) a worked failure example citing this exact proposal + the contradicting lines + the lesson, and (b) a schema-uniformity-assumption rule: *"When asserting a field is missing from a tool's records, do not generalize one tool's schema across tools. For every named tool whose schema you claim, open ≥3 records of that tool and confirm the field set you assert IS the field set present. Cite line numbers, not aggregates. Absence-claims require per-tool, per-record citations."* **Explicitly rejected: Layer 2 (mechanical claim-checker)** — accepted-proposal citation formats are too variable for regex extraction, absence-claims are hard to verify programmatically, and the existing rule worked at review time. Revisit Layer 2 only if a second false-evidence proposal occurs. **Priority:** medium — meta-agent works today, operator caught the failure, but the prompt-side defense is cheap and prevents the same class from recurring. **Status:** Layer 1 fix shipped in this commit; proposal moved to `.planning/doctrine_proposals/rejected/`.
- [ ] **A34** — `/run-brief` orchestrator dies on SSE client disconnect. **Class:** I-1 (lifecycle) + I-3 (closure). **Evidence:** sprint `run-20260525T001852Z-95e031` submitted at 19:18 CDT via `urllib.request.urlopen(..., timeout=30)`; after the 30s read timeout the client closed the SSE stream; orchestrator emitted only `orchestrator.start` + `orchestrator.index_initial.start` and went silent. 22 min later: uvicorn (PID 98752) had zero children, graphify cache untouched since 17:42, no TCP to Milvus/Ollama, no `.orchestrator-state/<run_id>.json`, no new `logs/orchestrator/<ts>/` dir. **Root cause hypothesis:** Starlette `StreamingResponse` cancels the underlying async generator on client disconnect; in `_run_indexers` the cancellation fires after the `.start` yield but before `asyncio.create_task(...)` actually schedules the subprocess coroutines, so neither indexer subprocess ever spawns and the entire sprint is silently aborted. **Impact:** any operator who submits via a curl/script with a finite timeout, or closes their browser tab while the SSE stream is open, loses the sprint with no failure event, no state file, no log dir — only two events in `events.jsonl` and a lingering `_RUN_META` entry that may also block resubmission via B2's 409 path. **Required fix:** decouple the orchestrator run from the SSE response — kick off the run as a `asyncio.create_task` (or background task registered in `_RUN_META` with proper lifecycle), make the SSE response a *consumer* of an event broker / replay queue, so disconnect = stop streaming, not stop running. Closure invariants (I-3) must still fire on operator-issued abort, not on incidental disconnect. **Priority:** high — invalidates "submit and walk away" mission posture.
- [ ] **A44** — Agent subprocess stream reader uses asyncio's default 64 KiB line-buffer limit; a single oversized `stream-json` line kills the agent mid-read and is silently mislabeled as "agent produced no source change." **Class:** I-1 (resource/IO lifecycle: the harness cannot reliably consume the output of a process it owns) + I-3/I-5 (the failure is surfaced under a false, more-optimistic-than-reality label). **Evidence:** sprint `run-20260528T144444Z-e4ba3d` (intelligent_kanban) aborted at BL-0004 after delivering 4/7 BLs. Trace `webapp/backend/traces_archive/run-20260528T144444Z-e4ba3d/20260528T202148Z-engineer-BL-0004-78815d511303/stream.jsonl` (3 R10.1 attempts concatenated). Attempts 1 (24s) and 2 (264s) both died with `exit_code 143` + `_error: "ValueError: Separator is found, but chunk is longer than limit"` **on the Read of `boards.py`** — the last recorded event in each is the `Read boards.py` tool_use; the tool_result line never appears (readline raised before returning it). Attempt 3 (144s) died differently — `exit_code 1`, `API Error: 400 messages.1.content.18: \`thinking\` or \`redacted_thinking\` blocks ... cannot be modified` — a separate CLI-internal error (see "Secondary" below). Three failed attempts → `doctrine_check give_up` → `orchestrator.aborted reason="engineer did not merge BL-0004"`. The orchestrator behaved correctly given a non-merging engineer; the root cause is upstream in the stream reader. **Root cause (verified to ±0.4% by two independent methods):** `webapp/backend/app/services/claude_agent.py` spawned the `claude` CLI via `asyncio.create_subprocess_exec(...)` with **no `limit=`**, so the StreamReader used asyncio's `_DEFAULT_LIMIT = 2**16 = 65536` bytes. `claude --output-format stream-json` emits one newline-delimited JSON event per line; a `Read` tool_result echoes the file content TWICE (the cat -n render in `message.content[].tool_result` AND the raw file in a top-level `tool_use_result.file` field) → ~2.28× inflation, giving a **~28.8 KB crossover**: any source file above ~29 KB produces a >64 KiB line. `boards.py` grew across the sprint (8→15→20→**32 KB** after BL-0001/0002/0005/0003), so BL-0004 was the first engineer to Read the 32 KB version → a **~73 KB line** (method A empirical ratio: 73,254 B; method B git reconstruction: 72,975 B; both > 65,536). `proc.stdout.readline()` then raised — note `StreamReader.readline()` converts the underlying `asyncio.LimitOverrunError` into `ValueError(e.args[0])`, which is the exact `"ValueError: Separator is found, but chunk is longer than limit"` in the trace — and the broad `except Exception` at `claude_agent.py` killed the process group (`os.killpg(SIGTERM)` → exit 143) before any code was written. BL-0001/0002/0003/0005 succeeded because their reads stayed under 64 KiB (BL-0003's `boards.py` read was the 45.9 KB near-miss). **Secondary (independent, not harness-caused):** attempt 3's API-400 thinking-block error is the `claude` CLI mis-assembling its own request on a long (33-turn) run — confirmed NOT a harness history-replay bug (every retry is a fresh `claude -p <prompt>`; there is no `--resume`/`--continue` anywhere and `build_fix_prompt` is plain text). The harness neither causes nor *detects* it: `stream_agent_task` never inspected the terminal `result` event's `is_error`/`api_error_status`, so an API failure was indistinguishable from "agent did no work," burning the final retry and aborting under a false label. **Fix (shipped in working tree; commit pending operator approval):** **(1)** `claude_agent.py` — new module constant `STREAM_READER_LIMIT = 64 * 1024 * 1024` (64 MiB) passed as `limit=` to `create_subprocess_exec`. This is the only clean fix: on `LimitOverrunError` the buffer is NOT consumed, so catch-and-continue cannot recover — the ceiling must be raised. **(2)** defense-in-depth: a dedicated `except ValueError` around the readline (matching `"chunk is longer than limit"`, else re-raise) that kills and emits a distinct `_meta phase=stream_overrun` event so this harness IO failure can never again masquerade as "no source change." **(3)** companion (I-3/I-5 honesty): `stream_agent_task` now inspects the terminal `result` event and emits a distinct `_meta phase=api_error` event (status, subtype, num_turns, truncated detail) so the attempt-3-class API failure is visible to control flow and the operator. **(4)** regression test `webapp/backend/tests/test_a44_stream_buffer_limit.py` (5 cases): default 64 KiB limit raises on the ~73 KB BL-0004 line; raised limit reads it (and a 10 MiB line) intact; the constant exceeds the default and the BL-0004 line; and `inspect.getsource(stream_agent_task)` asserts `limit=STREAM_READER_LIMIT` is actually passed (guards against a refactor silently reintroducing A44). All 25 backend tests pass. **Follow-up (open, tracked here):** the orchestrator does not yet ACT on `phase=api_error` — it should treat an API-error attempt as a RETRIABLE infrastructure failure (retry with backoff / escalate) rather than a doctrine-incomplete attempt that burns the R10.1 budget and aborts. That control-flow change touches `orchestrator.py` retry loops and is deferred to its own scoped change. **Priority:** high — crossover at a ~29 KB source file means this bites routinely on real brownfield repos; it presents as "agent mysteriously did no work," the most misleading possible signal, and it silently caps sprint completion. **Status:** primary + defense-in-depth + companion fix and 5-test suite implemented and passing; orchestrator-side api_error handling is the open follow-up.
- [ ] **A47** — Claude CLI built-in tools (`ScheduleWakeup`, `Glob`, possibly others) bypass the `--allowedTools` allowlist that `claude_agent.stream_agent_task` configures. The harness passes `allowed_tools="Bash,Read,Write,Edit"` (+ retrieval MCP tools), but the agent has been observed invoking `ScheduleWakeup` (sleeps while waiting for long-running children) and `Glob` (file pattern search) in every acceptance run. **Class:** I-2 (doctrine contract: a documented restriction is not enforced) + harness honesty (the allowlist gives a false sense of containment). **Evidence (4 worked examples, all acceptance runs 2026-05-30 → 2026-05-31):** smoke-1 `smoke-20260530T161537Z` (2 ScheduleWakeup invocations); smoke-2 `smoke-20260531T022625Z` (status synonym calibration also observed Glob); smoke-3 `smoke-20260531T034747Z` (clean run still used built-ins); REAL `run-20260531T134012Z-dd4864` health-version acceptance (1 ScheduleWakeup + 3 Glob despite allowed_tools restriction). The CLI emits no error/warning for the bypassed calls — they just succeed. **Impact:** today, BENIGN — agents use them productively (ScheduleWakeup as a `sleep` substitute that survives idle-timeout suppression; Glob as a faster `find`). But the failure mode is real: doctrine that names which tools are allowed cannot be relied on to actually constrain the agent, which weakens every R-rule that depends on the allowlist (e.g. R5's "no Write/Edit before grounding" assumes the harness can see the Write/Edit calls — fine — but a future R-rule that bans some other tool would silently fail). **Required fix:** **(1)** investigate WHY `--allowedTools` doesn't catch these — is it that built-in CLI tools are exempt by design, or is it a Claude Code CLI version-specific behavior? Check the Claude Code docs/changelog. **(2)** if exempt-by-design, document it in `HARNESS.md` §6.1 ("R-rules — the agent contracts") so future operators don't assume `--allowedTools` is a security boundary. **(3)** if a bug, file upstream and add a Tier 1.5 streaming-side kill for the specific tools we don't want (e.g. block any `tool_use` whose name isn't in an allowlist, killing the agent on attempt). **Priority:** low (no observed harm) but **interesting** — every operator who reads CLAUDE.md's R-rules assumes `--allowedTools` is enforced. Filed 2026-05-31 after 4-instance observation across all acceptance runs.
- [x] **A46** — Per-BL QA isolation structurally prevents recovery from cross-component bugs; "regression-clean gate" ≠ "feature works as a user would experience it." **Class:** I-2 (doctrine contract: no role exists for whole-feature acceptance) + I-7 (self-hardening: no signal exists for the meta-agent to mine when integration breaks). **Evidence:** time-tracking sprint, BL-0007 REQ-0502 (`run-20260529T133015Z-04da86`). The QA agent's reinforcement test for superuser self-approval caught a real defect: `ReviewTimesheet` keeps its dialog open on error → Radix Dialog sets `aria-hidden` on sibling content → the approval queue rows vanish from the a11y tree → no follow-up test interaction can find them. QA's 3 R10 retries could not fix it because the fix is an engineer-side dialog-close-on-error change in `ReviewTimesheet`; QA tests its BL in isolation and cannot request component changes that belong to a sibling BL's engineer. Operator hand-patched: merged QA's branch, skipped the REQ-0502 test, documented engineering follow-up. Net: the framework shipped a "regression-clean" branch with a real cross-component bug, masked by a `.skip`. Same pattern projects to any feature where two BLs touch related components — per-BL isolation is exactly the property that prevents the framework from noticing. **Resolution:** ABL-0014 Acceptance Agent — runs once at `sprint_complete` against the *assembled* branch with seeded multi-user state, exercises end-to-end user journeys via playwright with full-page screenshots, classifies failures into `product_bug | test_bug | data_bug | infra_bug | uncertain`, produces a report the operator can review at sprint close. The REQ-0502-class defect would have surfaced as a `product_bug` finding with screenshot evidence instead of a silent `.skip`. Validated 2026-05-31: smoke #2 against time-tracking found 2 real `product_bug` findings (`report_export`, `timesheet_submit_ui`) that per-BL QA had missed. SKILLS.md: `skills/brownfield/brownfield-acceptance-agent/SKILLS.md`. Implementation: commits `4a5c108` (Batch A: skill + validator + skeleton), `f1bdb8b` (Batch B: spawn + R10.1 retry + archive + closure_check extension), `c504e4f` (Batch C: frontend + docs + memory), `aa0e9ef` + `eb075ad` (calibration fixes), `8499dd3` (default flipped True). Plan: `ABL-0014_ACCEPTANCE_AGENT_IMPLEMENTATION.md`. **Status:** RESOLVED — ABL-0014 Acceptance Agent operational by default as of 2026-05-31. Filed as A46 (not A45) because A45 was claimed by the idle-timeout false-positive entry above; this entry was intended for Batch C commit `c504e4f` but the working-tree edit was never `git add`-ed.
- [x] **A36b** — `_check_tablename_consistency` scope bug: full-file parse of `models.py` at HEAD vs migration-files-in-diff produces N false-positives on every incremental BL (one per pre-existing `table=True` class in models.py). **Class:** I-2 (doctrine contract: validator scope) — sub-bug of A36 fix #4. **Evidence (1 worked example):** sprint `run-20260531T211839Z-1f47e6` (resumed at BL-0004 via `start_bl=BL-0004` on `run-20260601T025903Z-0a4b25`), engineer attempt 1 (709s, exit 0, branched off `health-version`). BL-0004 added one new model (`PortalAccessGrant`) + one new migration (`op.create_table("portalaccessgrant", ...)`). Doctrine check returned `missing=5`: User, ClientUser, PortalInvitation, PortalAuditLog, Item — all pre-existing classes in `models.py` from BL-0001/BL-0003 commits already on the branch. Engineer would have been told to "add 5 create_table calls" the second attempt — either making the migration unrunnable (duplicate-table) or burning R10.1 retries trying to argue with a false-positive validator. **Root cause:** `_check_tablename_consistency` calls `_parse_models_for_tables(path.read_text())` against the whole HEAD content of every changed models file (so it sees ALL `table=True` classes), but parses migration table names only from migration files *in this diff* (so it only sees newly-created tables). Asymmetric scope → every pre-existing class trips the "missing migration" branch. **Fix shipped:** add `_added_lines(repo_root, base_ref, rel_path)` helper that returns concatenated `+` lines from `git diff --unified=0 base_ref...HEAD -- <path>`. `_check_tablename_consistency` takes a `base_ref` kwarg; when present, restricts `declared` to classes whose `class X(...table=True)` declaration line appears in the added-slice (intersection with whole-file parse to preserve `__tablename__` resolution). Caller in `validate_engineer` (line 288) threads `base_ref` through. Backward compatible: if `base_ref` is None (existing unit-test path), falls back to whole-file parse. **Tests added (`tests/test_doctrine_validator_tablename.py`):** `test_a36b_incremental_bl_does_not_flag_prior_models` reproduces the BL-0004 false-positive on a 2-table baseline + 1-new-table BL using a real git repo + agent branch; `test_a36b_incremental_bl_still_catches_real_mismatch` pins that the original A36 WorkspaceMember-snake-vs-camel detection still fires. All 16 tests in the file pass. **Priority:** high — silently aborts every incremental BL on any project with >0 prior `table=True` classes; the failure mode masquerades as engineer error which is the most misleading possible signal. **Filed 2026-05-31, fix shipped same session.**
- [ ] **A48** *(fixes #1+#2 of 4 shipped 2026-06-01; #3 + #4 still open)* — Host disk-full mid-sprint surfaces as `regression_gate kind=infra_fail` with a misleading `PendingRollbackError` headline; no pre-flight free-space check and no inter-BL docker-volume reaper exist. **Class:** I-1 (resource lifecycle: the harness creates docker volumes per BL gate but does not bound their accumulation across sprints) + I-3 (closure asymmetry: closure_check tears down per-BL stacks at sprint end, but anonymous volumes from gate-spawn'd compose stacks persist across sprints and accumulate on the host) + observability/diagnosability (the canonical SQLAlchemy `PendingRollbackError` is reported as the failure headline; the actual `(psycopg.errors.DiskFull) could not extend file "base/16384/16505": No space left on device` is buried in `post_tail` ~3 KB deep, so an operator reading only the `_meta` event sees a session-state error and misclassifies). **Evidence (1 worked example):** sprint `run-20260531T211839Z-1f47e6` (Client_Portal_Self_Service_Platform), BL-0003 QA-phase regression_gate at 2026-06-01T02:27:17Z. QA agent itself reported PASS-W/R at 02:12:30Z (+7 tests, 0 regressions in its own stack); the orchestrator's standalone regression_gate then re-ran the QA-augmented suite against a fresh POST stack and PG ran out of space mid-`INSERT INTO portalauditlog (...)` (params include `created_at: 2026-06-01T02:23:10Z`). Phase event: `regression_gate ok=false kind=infra_fail` with `reason: "infra failure: E sqlalchemy.exc.PendingRollbackError ..."`; full chain visible in `post_tail`: `Original exception was: (psycopg.errors.DiskFull) could not extend file "base/16384/16505": No space left on device. HINT: Check free disk space.` The subsequent test that surfaced the `PendingRollbackError` (`tests/crud/test_user.py:109 db.commit()` after creating a bcrypt user) is a red herring — that test was simply the next operation on a SQLAlchemy session already DEACTIVE'd by the DiskFull. Host state at abort: Mac `/System/Volumes/Data` 93% full (398/460 GiB used, 32 GiB avail); `docker system df`: 1054 images (10.11 GB, 76% reclaimable), 78 local volumes (16.88 GB, 53% reclaimable), 1951 build-cache entries (1.46 GB). Post-prune (`docker system prune -af --volumes` + `docker volume prune -af` this session): 14.47 GB recovered, disk to 91% (42 GiB avail), 1 image / 1 container / 1 volume (Milvus standalone) retained intentionally. **Mechanism:** each BL gate spawns two disposable compose stacks (PRE + POST) each with its own anonymous postgres data volume; closure_check tears down the *containers* and the *named* docker resources on terminate, but anonymous volumes from gate stacks persist across sprints (44 anonymous-hash-named volumes were observable post-abort, of which 8.24 GB worth were prune-eligible). A 10–14 BL sprint chews through 5–15 GB in fresh volumes; combined with no pre-flight check, a 93%-full host will hit DiskFull deterministically mid-sprint. **Not A39 (parser was honest — `kind=infra_fail`, not `kind=regressed`); not A45 (no silent kill); not A40 (no biome). Genuinely new infra-class.** **Required fix:** **(1) Pre-flight check** in `webapp/backend/app/routers/projects.py::run_brief` (or `orchestrator.py::_pre_flight`): before `orchestrator.start`, query `shutil.disk_usage("/")` and `docker info` (effective storage path); refuse the run with HTTP 409 + a `pre_flight: insufficient_disk` SSE event when free space < N × estimated-per-BL-volume-size (suggest N=2× margin; estimated-per-BL = 1 GB conservative). Operator gets a clear "free disk first" failure at submission time, not 3h into the sprint. **(2) Inter-BL volume reaper** in the orchestrator's BL teardown path (`webapp/backend/app/services/closure_check.py` or the per-BL cleanup hook): after `bl.done`, run `docker volume prune -f --filter "label=com.docker.compose.project=<this-bl-project>"` to drop anonymous PG-data volumes from this BL's gate stacks. The named-by-project filter avoids touching Milvus or other operator-owned volumes. **(3) Surface the real cause** in `webapp/backend/app/services/regression_gate.py`'s `_classify_gate_result`: when the `post_tail` contains `psycopg.errors.DiskFull`, `No space left on device`, `disk quota exceeded`, or `OperationalError.*disk`, set `kind=infra_fail` *with* `infra_fail_reason: "host_disk_full"` (not the `PendingRollbackError` headline), and include the *original* exception line in `reason` rather than the cascade error that pytest happened to render first. This makes the failure self-diagnosing in the events.jsonl without operator forensic work. **(4) (Optional, lower priority) Stack-data-dir tmpfs override** for gate compose stacks where the postgres data dir is mounted to a tmpfs of capped size (e.g. 512 MB), so a runaway test cannot exhaust the host — failure becomes a contained "gate stack ran out of its own quota" instead of a host-level event. Defer until A48 recurs after fixes 1–3. **Priority:** medium — single observed instance, mitigation is straightforward, but on a multi-BL sprint with the operator's current 91%-full disk this WILL recur; pre-flight check (fix #1) is ~30 lines and a fix-it-now candidate. **Filed 2026-05-31 after BL-0003 QA-gate infra_fail aborted `run-20260531T211839Z-1f47e6` at 3/10 BLs.** **Fix #1 status (2026-06-01):** shipped as `webapp/backend/app/services/disk_preflight.py` + `RunBriefRequest.{enforce_disk_preflight,min_free_disk_gb,per_bl_disk_gb}` + `orchestrator.pre_flight.disk` SSE event. Advisory by default (event always emitted; HTTP 409 only when `enforce_disk_preflight=true`). Defaults: 5 GB floor + 1 GB/BL × max_bls (or 10 BL fallback). 10 new tests pass; full backend suite 104/104. **Fix #2 status (2026-06-01):** shipped as `webapp/backend/app/services/volume_reaper.py` (`reap(project)` + `reap_many([projects])` running `docker volume prune -f --filter label=com.docker.compose.project=<project>`). Wired into `regression_gate.run_gate` finally block (both `pre_proj` and `post_proj` reaped after each gate) and `_acceptance_flow` finally block (acceptance compose project reaped; surfaces as `acceptance.volume_reaper` SSE event with `volumes_removed` + `bytes_reclaimed`). 13 new tests pass (no-op semantics, name validation, output parsing for KB/MB/GB/TB, FileNotFoundError + OSError + timeout + non-zero exit failure paths, `reap_many` sequential, falsy-entry skip). Full backend suite 117/117. **Open: fix #3 (DiskFull-aware gate classifier) + fix #4 (optional tmpfs override) remain.**
- [ ] **A45** — B5 idle-timeout kills agents that are legitimately busy but stream-silent — specifically an engineer blocking on a long synchronous child process (the regression gate it ran itself). The agent's verified fix is destroyed mid-wait, before it can commit. **Class:** I-1 (lifecycle: a liveness heuristic whose false-positive discards in-flight work) + I-2 (the idle-timeout's "silence ⇒ hung" assumption is incomplete) — and causally coupled to A39. **Evidence:** sprint `run-20260530T133341Z-f97e8c` (time-tracking), BL-0014 ("settings: rates, policies, holidays"), 3rd engineer attempt (task `7369151ef9c0`). Chain (from `/tmp/tt-bl13-sse.log` + per-agent `stream.jsonl`): engineer gate came back `regressed` on a **real** bug — `ValueError: Invalid isoformat string: '2026-04-03T09:30:00Z'` (`test_time_settings.py::test_policy_allows_compliant_entry_and_rounds`) — but the gate event carried `regressions: []` (empty; see A39), so the R10.2 fix prompt named no failing test. The engineer therefore **ran the full gate itself** to self-diagnose, and **correctly solved it**: assistant text *"No sibling parses a `Z`-suffixed datetime — the fix belongs in the test"*, made the Edit, and **verified it** (`python3 -c "…"` → `parsed: 2026-04-03 09:30:00+00:00 OK`; `ruff: All checks passed!`). It then launched the gate in the background and **waited on it with a silent loop**: `until grep -q "GATE EXIT" /tmp/gate_run2.log 2>/dev/null; do sleep 15; done`. That loop emits **zero stream output**; after 600 s the harness fired `_error: "agent silent for 600s (idle_timeout; idle=600 wall=1200)"` → `_kill_pgroup` SIGTERM → `_meta exit_code=143`. The working fix was never committed (worktree killed mid-wait, then cleaned up). The orchestrator's own follow-up gate then ran `inconclusive` ("post suite did not exit clean (exit=1, 0 passed, 1 failed)") → `awaiting_review` → `engineer_unmerged` → `orchestrator.aborted reason="engineer did not merge BL-0014"`. **Net:** the abort was a harness false-positive, NOT a capability failure — the crew had a verified fix in hand and was killed for being silent while a legitimate child process ran. **Root cause:** B5's idle-timeout (`claude_agent.py`, the `asyncio.wait_for(proc.stdout.readline(), timeout=effective_timeout)` path with `idle_timeout=600`) equates "no NEW stream token for 600 s" with "hung." An agent that has issued a Bash `tool_use` spawning a long synchronous child (gate / pytest / playwright, routinely 10–25 min here) and is blocking on it is fully alive and working, yet stream-silent — the heuristic cannot tell "hung" from "busy-waiting on a legitimate child." **Causal chain with A39:** A39 (gate hands the engineer no actionable failing-test identities) → engineer must self-run the full gate to diagnose → engineer blocks silently on that gate → A45 idle-timeout kills it → sprint aborts. A39 + A45 compound into aborts; neither alone would have. **Required fix (defense-in-depth):** **(1) Harness** — before the idle-timeout kill, check whether the agent's process group still has an active descendant doing work (a running gate/pytest/playwright/docker child), OR track "a `tool_use` was emitted with no matching `tool_result` yet" as an in-flight-tool state; while a tool is in flight, the agent is *busy*, not *idle* — suppress or extend the idle clock (e.g. fall back to the wall-timeout only). This is the structural fix. **(2) Prompt/SKILLS (R14-adjacent)** — instruct engineers to NEVER run the full regression gate themselves and to NEVER use a silent blocking `sleep`/`until` wait loop; if a wait is unavoidable, emit periodic progress (`echo`) so the stream is not silent. Extends R14.3 (timeout-opt-out discipline). **(3) Deeper** — closing A39 removes the *need* to self-run the gate, eliminating the trigger. **Priority:** high — directly aborted a sprint that the crew had effectively solved; will recur on any BL where A39 forces self-diagnosis and a real gate failure exists. The most expensive failure mode observed: a correct fix thrown away by a liveness heuristic.
