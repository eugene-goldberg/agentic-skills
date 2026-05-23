# Agentic Skills — End-to-End Workflow Diagram

> Comprehensive ASCII diagram of every gate, guard, retry, and event from the
> moment a project brief enters the system until the last BL is scored or the
> sprint aborts. Cross-references every R-rule, Tier-1.5 check, A/B item from
> `DESIGN_SHORTCOMINGS.md`, and the disk-persisted state machine.
>
> **Use this as the single visual reference when reasoning about orchestration.**
> Code paths are `module:function` so you can grep directly.
>
> *Authored 2026-05-23 after Sprint 4 dry-run on Notifications backlog. Reflects
> the 18 hardening fixes (A1-A7 + B1-B18 in-scope set).*

---

## Legend

```
═══   strong/persistent control flow
───   normal sub-step
- - - optional / conditional branch
═►    emit SSE event
▶▶    spawn subprocess
↺     retry loop
⊗     hard fail / abort
✓     pass gate
⚑     R-rule / doctrine check
☐     disk artifact
◍     in-memory state
[Bn]  shortcomings ledger ID (see DESIGN_SHORTCOMINGS.md)
```

---

## 1. Top-level pipeline (operator → merged feature)

```
┌────────────────────────────────────────────────────────────────────────────┐
│  OPERATOR                                                                  │
│  ─ writes brief.md  ◍                                                      │
│  ─ POST /api/projects/<repo>/run-brief  (or webapp UI / launcher script)   │
└─────────────────────────┬──────────────────────────────────────────────────┘
                          │  brief, project_name, skip_po?, stop_on_failure?,
                          │  stop_on_qa_doctrine_failure?, start_bl?, max_bls?
                          ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  FASTAPI ROUTER  (webapp/backend/app/routers/projects.py:run_brief)        │
│                                                                            │
│  ┌──── PRE-STREAM GUARDS (must all pass before SSE begins) ────────────┐   │
│  │  [G1] _repo_dir() — symlink resolution, path-escape guard           │   │
│  │  [G2] _brief_hash = sha256(brief + project_name + repo)             │   │
│  │  [G3] lock = _get_run_lock(repo)              [B2]                  │   │
│  │       if lock.locked() AND hash matches → 409 duplicate-brief [B9]  │   │
│  │       if lock.locked() AND hash differs → 409 run-in-progress       │   │
│  │  [G4] orphan = run_state_svc.find_active(repo, brief_hash)   [A7]   │   │
│  │       if orphan AND skip_po=False → 409 orphaned-run-detected       │   │
│  │       if orphan AND skip_po=True  → reuse orphan["run_id"]          │   │
│  │       else                        → run_id = "run-<ts>-<uuid6>"     │   │
│  │  [G5] _RUN_META[repo] = {run_id, started_at, brief_hash,            │   │
│  │                          current_bl, resumed_from_orphan}           │   │
│  │  [G6] await lock.acquire()                                          │   │
│  │  [G7] WEB_CONCURRENCY warning (module-load) if > 1                  │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                                            │
│  StreamingResponse(gen(), media_type="text/event-stream")                  │
│      gen() try / except RetrievalUnavailable / except Exception            │
│           finally: _RUN_META.pop(repo); lock.release()                     │
└─────────────────────────┬──────────────────────────────────────────────────┘
                          ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  ORCHESTRATOR  (app/services/orchestrator.py:run_brief)                    │
│  ◍ summary {po, bls[]}                                                     │
│  ◍ bl_outcomes_compact []           ←─── A7 disk-state shadow              │
│  ◍ terminal_status = "aborted" (default; flipped at sprint_complete)       │
│                                                                            │
│  try:                                                                      │
│   ═► orchestrator.start  {run_id, brief_chars, project_name}               │
│                                                                            │
│   ┌─── STEP 1-3: PREFLIGHT + INITIAL INDEXING ────────────────────────┐    │
│   │  [P1] _preflight_retrieval():                                     │    │
│   │       check RETRIEVAL_REFERENCE_REPO exists                       │    │
│   │       check Milvus port 19530 reachable                           │    │
│   │       ☒ if down: _try_milvus_restart()           [A3]             │    │
│   │           ─ 60s cooldown gate (no restart-loop)                   │    │
│   │           ─ docker start <container> (env override)               │    │
│   │           ─ poll port 1s ×30 for health                           │    │
│   │       if still down → RetrievalUnavailable ⊗                      │    │
│   │  [P2] _run_indexers(repo_dir, "index_initial"):                   │    │
│   │       run_claude_context_index() ┐                                │    │
│   │       run_graphify_update()      ┤── concurrent asyncio.gather    │    │
│   │       ═► orchestrator.index_initial.{start,done}                  │    │
│   │       graphify writes via symlink to ~/.cache/.../graphify/...    │    │
│   │       worktree contains ONLY the symlink (not 178 AST files) [B3] │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                            │
│   ┌─── STEP 4: PO (skipped if skip_po=True) ──────────────────────────┐    │
│   │  ═► orchestrator.po.start                                         │    │
│   │  _po_flow() ─► see [§3 PO flow]                                   │    │
│   │  ═► orchestrator.po.done {ok}                                     │    │
│   │  ⊗ if !ok AND stop_on_failure → aborted "PO doctrine failed"      │    │
│   │                                                                   │    │
│   │  backlog_svc.find_backlog(repo_dir)                               │    │
│   │  ⊗ if not found → aborted "no BACKLOG.md found after PO phase"    │    │
│   │  items = backlog_svc.parse_file(bf)                               │    │
│   │  ordered = _dep_order(items)        ← topological sort of deps    │    │
│   │  if max_bls: ordered = ordered[:max_bls]                          │    │
│   │  ═► orchestrator.backlog_parsed {count, bls[]}                    │    │
│   │  [A7] _checkpoint(current_bl=None) ───☐                           │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                            │
│   ┌─── STEP 5: PER-BL LOOP (for it in ordered) ───────────────────────┐    │
│   │                                                                   │    │
│   │  [A4] if start_bl set AND not reached:                            │    │
│   │       ═► orchestrator.bl.skipped {reason="before start_bl=..."}   │    │
│   │       continue                                                    │    │
│   │                                                                   │    │
│   │  ═► orchestrator.bl.start {bl_id, title}                          │    │
│   │  [A7] _checkpoint(current_bl=bl_id) ───☐                          │    │
│   │                                                                   │    │
│   │       ┌─── ENGINEER ───┐                                          │    │
│   │       │  see [§4]      │ ─► merged | no_op | engineer_unmerged    │    │
│   │       └────────────────┘                                          │    │
│   │                                                                   │    │
│   │  [R11]   if engineer.no_op:                                       │    │
│   │  [B12]      qa_committed = _qa_commit_landed(repo_dir, bl_id,     │    │
│   │                                              agent_branch)        │    │
│   │             if qa_report.exists AND qa_committed:                 │    │
│   │                 ═► bl.done outcome="no_op"  ──→ next BL           │    │
│   │             else:                                                 │    │
│   │                 ═► orchestrator.partial_resume {reason}           │    │
│   │                 ──► fall through to QA on existing engineer work  │    │
│   │       elif !engineer.merged:                                      │    │
│   │  [A5]      ═► bl.done outcome="engineer_unmerged"                 │    │
│   │             ⊗ if stop_on_failure → aborted                        │    │
│   │             continue                                              │    │
│   │       else:                                                       │    │
│   │             ─► _run_indexers("reindex_after_engineer.<bl>")       │    │
│   │                                                                   │    │
│   │       ┌─── QA ───┐                                                │    │
│   │       │  see [§5]│ ─► doctrine_ok? + merged?                      │    │
│   │       └──────────┘                                                │    │
│   │                                                                   │    │
│   │  [A2]   if !qa.doctrine_ok AND !qa.merged:                        │    │
│   │              ═► orchestrator.qa_doctrine_failed {bl_id, summary}  │    │
│   │              if stop_on_qa_doctrine_failure:                      │    │
│   │  [A5]            ═► bl.done outcome="merged_no_qa"                │    │
│   │                    ═► aborted "QA doctrine failed for ..."  ⊗     │    │
│   │                                                                   │    │
│   │       ─► _run_indexers("reindex_after_qa.<bl>")                   │    │
│   │                                                                   │    │
│   │       ┌─── SCORER ───┐                                            │    │
│   │       │  see [§5 — same flow, role=scorer, no merge] │            │    │
│   │       └────────────────────────────────────────────┘              │    │
│   │                                                                   │    │
│   │  [A5]  outcome = compute_outcome(qa_doc_ok, qa_merged,            │    │
│   │                                  scorer_doctrine_ok):             │    │
│   │           merged_full   ← all three ✓                             │    │
│   │           merged_no_qa  ← QA failed OR didn't merge               │    │
│   │           merged_no_score ← scorer doctrine fail                  │    │
│   │  bl_outcomes_compact.append({bl_id, outcome})                     │    │
│   │  [A7] _checkpoint(current_bl=None) ───☐                           │    │
│   │  ═► orchestrator.bl.done {bl_id, outcome}                         │    │
│   │                                                                   │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                            │
│   terminal_status = "sprint_complete"                                      │
│   ═► orchestrator.sprint_complete {summary}                                │
│                                                                            │
│  finally:                                                                  │
│   [A7]  run_state_svc.mark_terminated(run_id, terminal_status)             │
│         ☐ .orchestrator-state/<run_id>.json → done/<run_id>.json           │
│   [B15] _archive_traces_since(repo_name, run_started_at, run_id)           │
│         ☐ traces/<repo>/... → traces_archive/<run_id>/...                  │
│         (only dirs with meta.finished_at present — skip mid-write)         │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Router pre-stream guard ladder (sub-diagram)

```
                       POST /run-brief
                              │
                              ▼
              ┌───────────────────────────────────┐
              │  _repo_dir(repo)                  │
              │  ✓ symlink resolves under         │
              │    webapp/backend/repos/          │
              │  ⊗ HTTP 400 path-escape           │
              └───────────────┬───────────────────┘
                              ▼
              ┌───────────────────────────────────┐
              │  brief_hash =                     │
              │    sha256(repo+name+brief)  [B9]  │
              └───────────────┬───────────────────┘
                              ▼
              ┌───────────────────────────────────┐
              │  lock = _get_run_lock(repo) [B2]  │
              │  existing = _RUN_META.get(repo)   │
              └───────────────┬───────────────────┘
                              ▼
                  ┌───────────────────────┐
                  │ existing.brief_hash   │── yes ──►  409 duplicate-brief
                  │  == brief_hash AND    │             {run_id, started_at,
                  │  lock.locked()?       │              current_bl}
                  └───────────┬───────────┘
                              │ no
                              ▼
                  ┌───────────────────────┐
                  │  lock.locked()?       │── yes ──►  409 run-in-progress
                  └───────────┬───────────┘
                              │ no
                              ▼
                  ┌───────────────────────┐         [A7]
                  │ orphan = find_active( │
                  │   repo, brief_hash)   │
                  └───────────┬───────────┘
                              ▼
              ┌───────────────────────────┐
              │ orphan AND !skip_po?      │── yes ──►  409 orphaned-run-detected
              └───────────┬───────────────┘             {orphan_run_id,
                          │ no                           orphan_current_bl,
                          ▼                              completed_bls[],
              ┌───────────────────────────┐              hint}
              │ orphan AND skip_po?       │── yes ──►  reuse orphan run_id
              └───────────┬───────────────┘             resumed_from_orphan=True
                          │ no
                          ▼
              ┌───────────────────────────┐
              │  run_id = "run-<ts>-<u6>" │
              │  await lock.acquire()     │
              │  _RUN_META[repo] = {...}  │
              └───────────┬───────────────┘
                          ▼
                  begin SSE generator
```

---

## 3. PO flow (`_po_flow`)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  _po_flow(repo_dir, repo_name, brief, project_name, timeout, rk_builder) │
│                                                                          │
│  cfg = repo_config_svc.load(repo_dir)                                    │
│  wt = await create_worktree(repo_dir, base_ref=cfg.agent_branch)         │
│  trace = TraceWriter(repo=repo_name, role="po")                          │
│       ☐ traces/<repo>/<ts>-po-<task_id>/                                 │
│       meta.json {harness_sha, started_at, ...}        [B14]              │
│  ═► worktree_ready {role: "po"}                                          │
│                                                                          │
│  prompt = build_po_prompt(brief, project_name, repo_dir)                 │
│      ├─ injects skills/{po,brownfield}/SKILLS.md                         │
│      ├─ requires final commit "po(<bl>...)" + JSON summary               │
│      └─ enforces R1-R12 in instructions                                  │
│                                                                          │
│  ▶▶ stream_agent_task(prompt, wt.path, timeout, idle_timeout=600,        │
│       allowed_tools="Bash,Read,Write,Edit",                              │
│       max_retrieval_calls=30,                                            │
│       trace=trace, **rk_builder(wt, "po", None, trace))                  │
│                                                                          │
│      └─► claude --print --output-format stream-json   [B1: start_new_session]
│            ── R5/R5b enforced via prompt + audit log                     │
│            ── R8 budget: kill if >30 mcp__retrieval__* calls             │
│            ── R9 grounding floor: ≥1 graph_* tool call                   │
│            ── Tier 1.5: pre-modification kill if <3 grounded calls       │
│            ── idle_timeout (600s default): silence kill           [B5]   │
│            ── _kill_pgroup on cancel / disconnect                  [B1]  │
│                                                                          │
│  ─► doctrine_svc.validate_po(wt.path) ⚑                                  │
│      missing_paths = []                                                  │
│      while !ok AND attempt < 2:        ─── R10 / R10.1 retry             │
│          fix_prompt = build_fix_prompt(missing_paths)                    │
│          ▶▶ stream_agent_task(fix_prompt, ...)                           │
│          validate again                                                  │
│      ═► doctrine_check {kind: complete|incomplete|give_up,               │
│                         attempts, summary}                               │
│                                                                          │
│  if validation.ok:                                                       │
│      backlog_import_committed(wt) — verifies "po: import backlog" commit │
│      merge = fast_forward_target(repo_dir, wt.branch, target_ref)        │
│      ═► merge_to_target {ok, merged_sha, kind, branch}                   │
│                                                                          │
│  ◍ yield {_orchestrator_outcome, role=po, doctrine_ok=ok}                │
│                                                                          │
│  finally:                                                                │
│      trace.close()                                                       │
│      remove_worktree(repo_dir, wt)                                       │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Engineer flow (`_engineer_flow`)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  _engineer_flow(repo_dir, repo_name, bl_id, timeout, rk_builder)             │
│                                                                              │
│  cfg = repo_config_svc.load(repo_dir)                                        │
│  wt = create_worktree(base_ref=cfg.agent_branch)                             │
│  trace = TraceWriter(repo, "engineer", bl_id)                                │
│  ═► worktree_ready {role: "engineer", bl_id, trace_dir}                      │
│                                                                              │
│  prompt = build_engineer_prompt(bl_id, repo_dir)                             │
│       ├─ skills/brownfield/.../SKILLS.md                                     │
│       ├─ codebase_context.md per-BL                                          │
│       └─ R1-R12 + Tier 1.5 in injected doctrine                              │
│                                                                              │
│  ┌──────────── DOCTRINE+GATE LOOP (gate_attempt < 3) ──────────────────┐     │
│  │                                                                    │     │
│  │  ▶▶ stream_agent_task(prompt, wt.path, idle_timeout=600,           │     │
│  │     allowed_tools="Bash,Read,Write,Edit", max_retrieval_calls=30)  │     │
│  │     ─ same R5/R5b/R8/R9/Tier1.5 enforcement as PO                  │     │
│  │     ─ event stream tagged orchestrator_step=engineer + bl_id       │     │
│  │     ─ pgroup-isolated subprocess  [B1]                             │     │
│  │     ─ silence kill at idle_timeout [B5]                            │     │
│  │                                                                    │     │
│  │  ⚑ doctrine_svc.validate_engineer(wt.path, bl_id, ...)             │     │
│  │     ↺ retry up to 2× with focused fix_prompt   [R10/R10.1]         │     │
│  │  ═► doctrine_check {kind, attempts, summary}                       │     │
│  │                                                                    │     │
│  │  if !validation.ok: break (→ awaiting_review)                      │     │
│  │                                                                    │     │
│  │  ─ has_new_commits(wt.branch, base_ref)?                           │     │
│  │  ─ no_op case: engineer reports R11 "already shipped upstream"     │     │
│  │     ═► return _orchestrator_outcome {merged=False, no_op=True}     │     │
│  │                                                                    │     │
│  │  ─ regression_gate_svc.run_gate(repo_dir, wt.branch, target_ref)   │     │
│  │     ┌─ create .gate-worktrees/pre-<rand>/ at target_ref            │     │
│  │     ├─ create .gate-worktrees/post-<rand>/ at agent_branch         │     │
│  │     ├─ run test_cmd (auto-detected or .agentic-skills.json) BOTH  │     │
│  │     │   — backend pytest inside docker-compose container          │     │
│  │     │   — Playwright E2E with CI=1 (flaky-retry, M1 fix)          │     │
│  │     ├─ compute regressed-test set                                  │     │
│  │     └─ kind ∈ {green, regressed, inconclusive, skipped, error}    │     │
│  │  ═► regression_gate {gate_attempt, ok, kind, regressions,          │     │
│  │                      reason, post_tail}                            │     │
│  │                                                                    │     │
│  │  if !gate.ok AND validation.ok:                                    │     │
│  │     ↺ R10.2 — re-spawn with focused gate-failure fix prompt        │     │
│  │                                                                    │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
│  if validation.ok AND gate.ok:                                               │
│     merge = fast_forward_target(repo_dir, wt.branch, target_ref)             │
│     if !merge.ok AND merge.kind == "error":                                  │
│        asyncio.sleep(2); merge_retry → use if ok                             │
│     if !merge.ok AND merge.kind == "non_ff":    [A1]                         │
│        ═► merge_rebase_attempt {branch, target_ref}                          │
│        rebase = _rebase_in_worktree(wt.path, target_ref)                     │
│           ├─ git rebase target_ref (60s timeout, inside wt.path)             │
│           └─ on conflict: git rebase --abort (10s); leave for review         │
│        if rebase.ok:                                                         │
│           ═► merge_rebase_succeeded                                          │
│           ─► run_gate (post_rebase=True flag)  ─── NEW SHA must re-pass!     │
│           ═► regression_gate {post_rebase=True, ...}                         │
│           if gate2.ok:                                                       │
│              merge = fast_forward_target(...)  ←─ retry                      │
│           else:                                                              │
│              merge = {ok=False, kind="non_ff_gate_failed_post_rebase"}      │
│        else:                                                                 │
│           ═► merge_rebase_failed {error}                                     │
│     ═► merge_to_target {ok, merged_sha, kind, error, branch}                 │
│     merged = bool(merge.ok)                                                  │
│  else:                                                                       │
│     ═► awaiting_review {reason: gate.reason or "doctrine incomplete"}        │
│                                                                              │
│  ◍ yield {_orchestrator_outcome, role=engineer, bl_id,                       │
│           merged, no_op, retrieval_call_count}                               │
│                                                                              │
│  finally:                                                                    │
│     trace.close()  ─── writes finished_at, n_events, n_retrieval_calls       │
│     remove_worktree(repo_dir, wt)                                            │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. QA / Scorer flow (`_qa_or_scorer_flow`)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  _qa_or_scorer_flow(repo_dir, repo_name, bl_id, role, timeout, rk_builder)   │
│                                                                              │
│  IDENTICAL structure to engineer flow except:                                │
│   • role ∈ {"qa", "scorer"}                                                  │
│   • SCORER NEVER MERGES (no fast_forward_target call)                        │
│   • prompts: build_qa_prompt / build_scorer_prompt                           │
│   • scorer's allowed_tools is narrower (no Edit/Write — read-only review)    │
│   • R12 grounding floor applies to scorer                                    │
│                                                                              │
│  Same gate+rebase recovery (A1) applies to QA but NOT scorer.                │
│                                                                              │
│  Returns _orchestrator_outcome {                                             │
│     role, bl_id, merged, doctrine_ok,                                        │
│     doctrine_summary    ← [A2] carries validator summary to per-BL loop      │
│  }                                                                           │
└──────────────────────────────────────────────────────────────────────────────┘

           ┌────────── QA-specific "partial_resume" trigger ───────────┐
           │                                                           │
           │  Per-BL loop fires THIS flow even when engineer.no_op=True │
           │  IF .agile-v/qa/<bl>.md is missing OR no qa(<bl>...) commit│
           │  exists on agent_branch  [B12]                             │
           │                                                           │
           │  ═► orchestrator.partial_resume {reason: <which case>}    │
           │                                                           │
           │  Sprint 4 empirical proof: BL-0004 had engineer commit but │
           │  no QA commit (Sprint 3 silent give-up). Sprint 4 detected │
           │  via B12, ran QA, scorer → outcome="merged_full".          │
           └───────────────────────────────────────────────────────────┘
```

---

## 6. Subprocess lifecycle (`stream_agent_task`)

```
┌────────────────────────────────────────────────────────────────────────────┐
│  app/services/claude_agent.py:stream_agent_task                            │
│                                                                            │
│  ┌─ prompt assembly ──────────────────────────────────────────────────┐    │
│  │   build_prompt(task) with completion protocol                      │    │
│  │   _build_retrieval_mcp_config(reference_repo, target_repo,         │    │
│  │                               retrieval_log_path) → mcp.json        │    │
│  │   effective_allowed = allowed_tools + RETRIEVAL_MCP_TOOLS          │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                                                            │
│  cmd = ["claude", "--print",                                               │
│         "--dangerously-skip-permissions",                                  │
│         "--output-format", "stream-json", "--verbose",                     │
│         "--allowedTools", effective_allowed,                               │
│         "--mcp-config", mcp.json,                                          │
│         "-p", prompt]                                                      │
│                                                                            │
│  ═► _meta phase=spawn (cmd preview)                                        │
│                                                                            │
│  ▶▶ proc = create_subprocess_exec(*cmd,                                    │
│         cwd=repo_path,                                                     │
│         stdout=PIPE, stderr=PIPE, env={...},                               │
│         start_new_session=True)         ◄─── [B1] own pgroup               │
│                                                                            │
│  stderr_task = asyncio.create_task(_drain_stderr())                        │
│                                                                            │
│  effective_timeout = min(idle_timeout, timeout_seconds)   [B5]             │
│  grounded_count = 0  ;  retrieval_call_count = 0                           │
│  pregrounding_violated = False ; budget_exceeded = False                   │
│                                                                            │
│  try:                                                                      │
│    try:                                                                    │
│      while True:                                                           │
│        ┌── per-readline wait_for ────────────────────────────────────┐     │
│        │ raw = wait_for(proc.stdout.readline(),                      │     │
│        │                timeout=effective_timeout)                   │     │
│        └───────────────────────────────────────────────────────────────┘   │
│        on TimeoutError [B5]:                                               │
│           await _kill_pgroup(proc)                                         │
│           ═► _error {kind: idle_timeout, idle_seconds, error}              │
│           return                                                           │
│                                                                            │
│        evt = json.loads(line)                                              │
│        for tool_use in _tool_uses_in_event(evt):                           │
│           if tool.startswith("mcp__retrieval__"):                          │
│              retrieval_call_count++                                        │
│              if tool in GROUNDED: grounded_count++                         │
│              if retrieval_call_count > max_retrieval_calls:                │
│                 budget_exceeded = True [R8]                                │
│           elif min_pregrounding > 0 AND tool in MUTATING_TOOLS             │
│                AND grounded_count < min_pregrounding:                      │
│              pregrounding_violated = True  [Tier 1.5]                      │
│                                                                            │
│        trace.write_event(evt)                                              │
│        yield evt                                                           │
│                                                                            │
│        if budget_exceeded:                                                 │
│           _kill_pgroup(proc)                                               │
│           ═► _meta retrieval kind=budget_exceeded {reason}                 │
│           return                                                           │
│        if pregrounding_violated:                                           │
│           _kill_pgroup(proc)                                               │
│           ═► _meta pre_grounding_violation {grounded_count, required}      │
│           return                                                           │
│                                                                            │
│    finally:  ◄────────── INNER FINALLY                                     │
│       if proc.returncode is None:                                          │
│           _kill_pgroup(proc)  [B1]                                         │
│           ─ SIGTERM to pgroup; wait 10s; SIGKILL if alive                  │
│       try: wait_for(proc.wait(), 2.0)                                      │
│       stderr_task.cancel()                                                 │
│       ═► _meta phase=exit {exit_code, duration_s}                          │
│           (yield wrapped in try/except GeneratorExit per PEP 525)          │
│                                                                            │
│  except Exception as exc:                                                  │
│       _kill_pgroup(proc)                                                   │
│       ═► _error {error}                                                    │
│                                                                            │
│  finally:  ◄────────── OUTER FINALLY                                       │
│       _kill_pgroup(proc)         ◄─── idempotent guard [B1]                │
│       if !stderr_task.done(): stderr_task.cancel()                         │
│       mcp_config_path.unlink()                                             │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Doctrine validator + R-rule cheatsheet

```
                    R-RULE / TIER GATE MATRIX (active 2026-05-23)
┌──────────┬─────────────────────────────────────────────────────────────────┐
│ R1       │  Each role's required artifacts MUST exist + be ≥120 bytes      │
│ R2       │  Engineer commit subject MUST follow "BL-XXXX(...): ..." form   │
│ R3       │  No agent may write outside the worktree                        │
│ R4       │  Engineer MUST end with `git status` clean (no stray files)     │
│ R5       │  ≥3 grounded retrieval calls (semantic/graph) per role          │
│ R5b      │  All claims in QA artifacts MUST cite retrieved sources         │
│ R7       │  Rubric self-consistency: any brownfield dim ≤2 → Fail verdict  │
│ R8       │  ≤30 mcp__retrieval__* calls per role (budget ceiling)          │
│ R9       │  ≥1 graph_* tool call per role (graph-grounding floor)          │
│ R10      │  Gate-failure → up to 2 retries with focused fix prompt         │
│ R10.1    │  Doctrine-incomplete → up to 2 retries with delta prompt        │
│ R10.2    │  After R10's 2 retries, awaiting_review if still failing       │
│ R11      │  No-op short-circuit when BL work already on agent_branch       │
│ R12      │  Scorer grounding floor (separate ceiling from R5)              │
│ Tier 1.5 │  Pre-modification kill if Write/Edit before ≥3 grounded calls   │
└──────────┴─────────────────────────────────────────────────────────────────┘

         doctrine_validator.py:validate_po / validate_engineer / validate_qa
                                       │
                                       ▼
         returns {ok: bool, summary: dict, missing: list[str]}
                                       │
                                       ▼
                  build_fix_prompt(missing) — names exact missing paths
                                       │
                                       ▼
                                ↺ retry (R10.1)
```

---

## 8. Regression gate v3 (`regression_gate_svc.run_gate`)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  run_gate(repo_dir, agent_branch, target_ref)                            │
│                                                                          │
│  ┌─ create two disposable worktrees ────────────────────────────────┐    │
│  │   pre_wt  = .gate-worktrees/pre-<rand>/  ← checkout target_ref   │    │
│  │   post_wt = .gate-worktrees/post-<rand>/ ← checkout agent_branch │    │
│  │   git merge agent_branch INTO post_wt's target_ref (dry-run)     │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─ run test_cmd in BOTH ──────────────────────────────────────────┐     │
│  │   test_cmd source order:                                        │     │
│  │     1. .agentic-skills.json:test_cmd  (explicit override)       │     │
│  │     2. autodetect (scripts/regression_gate.sh)                  │     │
│  │     3. fallback: pytest -q                                      │     │
│  │                                                                 │     │
│  │   Sprint 4 target uses scripts/regression_gate.sh:              │     │
│  │     ─ docker compose up -d (db + mailcatcher + backend + front) │     │
│  │     ─ wait for healthchecks (90s ceiling)                       │     │
│  │     ─ docker exec backend pytest -q                             │     │
│  │     ─ npx playwright test (CI=1 for flaky retry, M1 fix)        │     │
│  └─────────────────────────────────────────────────────────────────┘     │
│                                                                          │
│  parse junit/text output → pre_set, post_set                             │
│  regressed = pre_passed ∩ post_failed                                    │
│                                                                          │
│  result kinds:                                                           │
│    green       — post exit=0, no regressions      ✓                      │
│    regressed   — at least one previously-passing test now fails ⊗        │
│    inconclusive— post exit≠0 but no parseable output (broken test infra) │
│    skipped     — greenfield: gate intentionally off                      │
│    error       — docker/infra failure                                    │
│                                                                          │
│  returns {ok, kind, regressions[], reason, post_tail[]}                  │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 9. A1 non-FF auto-rebase recovery

```
              merge = fast_forward_target(...)
                            │
                            ▼
                ┌──────────────────────┐
                │  merge.kind == ?     │
                └──────────┬───────────┘
        ┌──────────────────┼─────────────────────┐
        │                  │                     │
       ff/noop           error               non_ff
        │                  │                     │
        ▼                  ▼                     ▼
     ✓ merged       sleep 2s + retry      ═► merge_rebase_attempt
                          │                     │
                          ▼                     ▼
                 retry.ok? ─ yes ──► ✓    _rebase_in_worktree(wt.path, target_ref)
                          │                     │
                          no                    ├─ git rebase target_ref (60s)
                          ▼                     │  in cwd=wt.path
                  ═► awaiting_review            │
                                                ▼
                                          rebase.ok? ─── no ──► git rebase --abort
                                                │                       │
                                                yes                     ▼
                                                │             ═► merge_rebase_failed
                                                ▼                       │
                                         ═► merge_rebase_succeeded      ▼
                                                │             ═► awaiting_review
                                                ▼
                                         re-run regression_gate
                                         ═► regression_gate post_rebase=true
                                                │
                                       gate2.ok? ─ no ─► merge_to_target {
                                                │           ok=False,
                                                yes         kind=non_ff_gate_failed_post_rebase
                                                │        }
                                                ▼         ═► awaiting_review
                                         fast_forward_target(...)
                                                │
                                                ▼
                                              ✓ merged
```

---

## 10. Persistence & observability layers

```
┌──────────────────── DISK ARTIFACTS PER RUN ─────────────────────────┐
│                                                                     │
│  ☐ webapp/backend/.orchestrator-state/<run_id>.json    [A7]         │
│     {run_id, repo, brief_hash, started_at, updated_at,              │
│      current_bl, bl_outcomes[], status}                             │
│     ─ atomic write: tmp + fsync + rename                            │
│     ─ updated at every milestone (backlog_parsed, bl.start, bl.done)│
│     ─ moves to .orchestrator-state/done/<run_id>.json on terminate  │
│                                                                     │
│  ☐ webapp/backend/traces/<repo>/<ts>-<role>[-bl]-<tid>/  per-agent  │
│     meta.json {harness_sha [B14], role, bl_id, started_at,          │
│                finished_at, cmd, n_events, n_retrieval_calls,       │
│                final_result_frame, done}                            │
│     stream.jsonl   {every SSE frame from claude}                    │
│     retrieval.jsonl {per-call audit log from MCP server}            │
│     ─ on sprint_complete / aborted: moved to                        │
│       webapp/backend/traces_archive/<run_id>/...  [B15]             │
│                                                                     │
│  ☐ webapp/backend/logs/orchestrator/<YYYYMMDD-HHMMSS>/  [B18]       │
│     run.log         tee'd from launcher stdout                      │
│     milestones.log  filtered subset via milestone_watcher.sh        │
│     .latest         symlink to most recent timestamped dir          │
│                                                                     │
│  ☐ ~/.cache/agentic-skills/graphify/<sha256(repo)[:16]>/  [B3]      │
│     graph.json, GRAPH_REPORT.md, manifest.json, cache/              │
│     ─ <repo>/graphify-out is a SYMLINK to this dir                  │
│     ─ gitignore (no trailing slash) catches the symlink             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────────── SSE EVENT TAXONOMY ──────────────────────────┐
│                                                                  │
│  Top-level (phase = "orchestrator.<key>")                        │
│  ─ start {run_id}                                                │
│  ─ index_initial.{start,done}                                    │
│  ─ po.{start,done}                                               │
│  ─ backlog_parsed {count, bls[]}                                 │
│  ─ bl.{start,done} {bl_id, outcome}                              │
│  ─ bl.skipped {reason}                              [A4]         │
│  ─ engineer.{start,done}                                         │
│  ─ qa.{start,done}                                               │
│  ─ scorer.{start,done}                                           │
│  ─ reindex_after_{engineer,qa}.{start,done}                      │
│  ─ partial_resume {bl_id, reason}                   [B12]        │
│  ─ qa_doctrine_failed {bl_id, summary}              [A2]         │
│  ─ sprint_complete {summary}                                     │
│  ─ aborted {reason}                                              │
│                                                                  │
│  Per-role (phase = various; orchestrator_step + bl_id tagged)    │
│  ─ worktree_ready                                                │
│  ─ spawn {cmd preview}                                           │
│  ─ assistant/user/system/tool_use/tool_result (claude raw)       │
│  ─ doctrine_check {kind ∈ {complete,incomplete,give_up},         │
│                    attempts, summary}                            │
│  ─ regression_gate {gate_attempt, ok, kind, regressions,         │
│                     reason, post_tail, post_rebase}              │
│  ─ merge_to_target {ok, merged_sha, kind, error, branch}         │
│  ─ merge_rebase_{attempt,succeeded,failed} {branch, error} [A1]  │
│  ─ awaiting_review {reason}                                      │
│  ─ rate_limit_event                                              │
│  ─ result   (claude final summary)                               │
│  ─ exit {exit_code, duration_s}                                  │
│  ─ _meta retrieval {kind ∈ {budget_exceeded, ...}}               │
│  ─ _meta pre_grounding_violation                                 │
│  ─ _error {error, kind ∈ {idle_timeout, ...}}       [B5]         │
│  ─ FULL_EVENT (reader-side full JSON dump on failure) [A6]       │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 11. UI rendering (`AppV2.jsx:ingest`)

```
                        SSE event arrives
                              │
                              ▼
                     ┌──────────────────┐
                     │  events.push(e)  │ (bounded ring buffer 2000)
                     └────────┬─────────┘
                              ▼
                  phase.startsWith("orchestrator.")?
                              │
            ┌──────yes────────┘
            ▼
   key = phase.slice("orchestrator.".length)
   switch(key):
     start            → setStage("preflight", done, {run_id})
     index_initial.*  → setStage("index_initial", running|done)
     po.*             → setStage("po", running|done|failed)
     backlog_parsed   → setStage("backlog_parsed", done); setBls(...)
     bl.start         → upsertBl(blId, status="running", title)
     bl.done          → outcome→status mapping (A5 colors):
                          merged_full   → done   (green bold)
                          merged_no_qa  → warned (amber border)
                          merged_no_score → warned (amber border)
                          engineer_unmerged → failed (red border)
                          no_op         → done (gray italic)
                          merged        → done (legacy)
     bl.skipped       → upsertBl(skipped, skip_reason)
     partial_resume   → upsertBl(partial_resume=true, reason)
     qa_doctrine_failed → setBlStep(bl, "qa", doctrine_failed=true,
                                              doctrine_summary)
     engineer.* / qa.* / scorer.*
                      → setBlStep(bl, role, status, merged, no_op,
                                  doctrine_ok)
     reindex_after_*  → setBlStep(bl, "reindex_e|q", running|done)
     sprint_complete  → setStage("sprint_complete", done, summary)
     aborted          → setStage("sprint_complete", failed, reason)

                  per-role (step + bl_id tagged):
     regression_gate  → setBlStep(stepKey, gate_kind, gate_ok,
                                  gate_post_rebase?)
     merge_to_target  → on !ok: setBlStep(merge_failed, merge_kind,
                                          merge_error)
     merge_rebase_attempt    → setBlStep(rebase_attempt=true)
     merge_rebase_succeeded  → setBlStep(rebase_succeeded=true)
     merge_rebase_failed     → setBlStep(rebase_failed, rebase_error)
     awaiting_review         → setBlStep(awaiting=true, reason)

                  run() error path:
     409 detail surfaced via {phase:"orchestrator.aborted",
                              reason: detail.error, detail}
```

---

## 12. End-to-end happy path (Sprint 4 BL-0006 example)

```
operator                  router                orchestrator              agent
   │                        │                       │                       │
   │ POST /run-brief        │                       │                       │
   │ {skip_po=true, ...}    │                       │                       │
   ├───────────────────────►│                       │                       │
   │                        │ G1-G7 guards          │                       │
   │                        │ acquire lock          │                       │
   │                        │ run_id minted         │                       │
   │                        ├──────────────────────►│                       │
   │                        │                       │ ═► start {run_id}     │
   │                        │                       │ preflight ✓           │
   │                        │                       │ index_initial         │
   │                        │                       │ ═► backlog_parsed     │
   │                        │                       │ _checkpoint(None)     │
   │                        │                       │                       │
   │                        │                       │ for BL in ordered:    │
   │                        │                       │ ═► bl.start BL-0006   │
   │                        │                       │ _checkpoint(BL-0006)  │
   │                        │                       │ ═► engineer.start     │
   │                        │                       ├──────────────────────►│
   │                        │                       │                       │ ▶▶ claude
   │                        │                       │                       │ R5/R8/R9
   │                        │                       │                       │ Tier 1.5
   │                        │                       │                       │ git commit
   │                        │                       │◄──────────────────────┤
   │                        │                       │ doctrine_check ✓      │
   │                        │                       │ regression_gate green │
   │                        │                       │ fast_forward_target   │
   │                        │                       │ ═► merge_to_target ✓  │
   │                        │                       │ ═► engineer.done      │
   │                        │                       │ reindex_after_eng     │
   │                        │                       │                       │
   │                        │                       │ ═► qa.start           │
   │                        │                       ├──────────────────────►│
   │                        │                       │                       │ ▶▶ claude
   │                        │                       │◄──────────────────────┤
   │                        │                       │ doctrine + gate ✓     │
   │                        │                       │ ═► merge_to_target ✓  │
   │                        │                       │ ═► qa.done            │
   │                        │                       │ reindex_after_qa      │
   │                        │                       │                       │
   │                        │                       │ ═► scorer.start       │
   │                        │                       ├──────────────────────►│
   │                        │                       │                       │ ▶▶ claude
   │                        │                       │◄──────────────────────┤
   │                        │                       │ doctrine_ok=true      │
   │                        │                       │ ═► scorer.done        │
   │                        │                       │                       │
   │                        │                       │ outcome=merged_full   │
   │                        │                       │ _checkpoint(None)     │
   │                        │                       │ ═► bl.done {full}     │
   │                        │                       │                       │
   │                        │                       │ ... more BLs ...      │
   │                        │                       │                       │
   │                        │                       │ ═► sprint_complete    │
   │                        │                       │ terminal_status=done  │
   │                        │                       │ mark_terminated()     │
   │                        │                       │ _archive_traces       │
   │                        │ release lock          │                       │
   │◄───────────────────────┤◄──────────────────────┤                       │
   │ SSE stream closed      │                       │                       │
```

---

## 13. Failure-mode cross-reference

| Anomaly observed in Sprint 2/3 | Mitigation lands in | Code path |
|---|---|---|
| Orphan claude subprocesses on SSE disconnect | B1 | `claude_agent._kill_pgroup` + `start_new_session=True` |
| Hung claude burns 40-min wall budget | B5 | `claude_agent.stream_agent_task: effective_timeout` |
| Two parallel `/run-brief` POSTs stomp each other | B2 | `projects._get_run_lock` + 409 response |
| Same brief retried by operator → duplicate run | B9 | `projects._brief_hash` → 409 duplicate-brief |
| Crash mid-sprint → lost queue position | A7 | `run_state.write_checkpoint` + `find_active` + orphan 409 |
| Operator commit races agent worktree (non-FF) | A1 | `orchestrator._rebase_in_worktree` + gate re-run |
| Milvus crash mid-sprint | A3 | `projects._try_milvus_restart` + 60s cooldown |
| QA-doctrine give-up silently labeled "merged" | A2 + A5 | `orchestrator: qa_doctrine_failed` + truthful outcome |
| Half-written QA file fools partial_resume | B12 | `orchestrator._qa_commit_landed` git-log cross-check |
| 178 graphify AST files swept into QA commit | B3 | `_ensure_graphify_symlink` → `~/.cache/.../graphify/` |
| `aborted` event missing reason | A6 | reader script `FULL_EVENT` JSON dump on failure phases |
| No forensic link between trace and harness version | B14 | `traces._HARNESS_SHA` in `meta.json` |
| Live traces dir accumulates forever | B15 | `_archive_traces_since` on terminate (complete or abort) |
| UI silently drops new event types / outcome labels | B4 | `AppV2.ingest` handlers for 8 new event types |
| Operational logs in `/tmp/` (ephemeral) | B18 | `webapp/backend/scripts/run_orchestrator.py` writes to `webapp/backend/logs/orchestrator/<ts>/` |
| Single-BL scorer abort had no resume path | A4 | `RunBriefRequest.start_bl` + RECOVERY.md playbook |
| Flaky Playwright on M1 causing false regressions | M1 mitigation | `target/.../regression_gate.sh: CI=1` |

---

## 14. Operator authority boundaries

```
┌────────────────────────────────┬────────────────────────────────────┐
│  AGENT-OWNED (do not hand-edit)│  OPERATOR-OWNED                    │
├────────────────────────────────┼────────────────────────────────────┤
│  .agile-v/qa/<bl>.md           │  PROJECT_BRIEF / brief.md          │
│  _brownfield/<BL>/*.md         │  .agentic-skills.json (per-target) │
│  agent_branch git history      │  rubrics/*.md                      │
│  worktree contents             │  skills/*/SKILLS.md (doctrine)     │
│  graphify cache                │  doctrine_validator.py changes     │
│  trace dirs (post-write)       │  ROADMAP / ABL-prioritization      │
└────────────────────────────────┴────────────────────────────────────┘
```

---

## 15. Sprint 4 empirical validation snapshot

As of `tail -f webapp/backend/logs/orchestrator/.latest/run.log`:

```
✓ B18 logs in webapp/backend/logs/orchestrator/        (was /tmp/)
✓ A7  state at webapp/backend/.orchestrator-state/     (bl_outcomes[] live)
✓ B14 harness_sha in trace meta.json                    (every trace)
✓ B3  target's graphify-out is a symlink                (1 entry, not 178)
✓ B12 partial_resume fired correctly on BL-0004         (was silent-failure in Sprint 3)
✓ A2/A5 BL-0004 traced engineer→QA→scorer→merged_full   (was "merged" w/no QA in Sprint 3)
✓ R10.1 doctrine retry: incomplete → complete           (BL-0004, BL-0005 QA)
✓ B1  zero orphan claude subprocesses                   (during entire run)
... (more BLs ahead — diagram updated when sprint completes)
```

---

*This file is a living diagram. When new R-rules, A/B items, or event types
ship, update the relevant section + the cross-reference table in §13.
For the audit ledger see `DESIGN_SHORTCOMINGS.md`; for the contract see
`IMPLEMENTATION_PLAN.md`; for live progress see `IMPLEMENTATION_TRACKER.md`.*
