# Continuation prompt — paste into the next Claude session

> This is the handoff document for picking up the agentic-skills project at the point where Sprint 3 (Notifications & Activity System) was aborted mid-flight on 2026-05-23 and a comprehensive 8-batch hardening plan was written but not yet executed.
>
> Paste everything below the `---PROMPT START---` line as your first message in the new session.

---PROMPT START---

You are picking up a long-running project mid-stream. Read this entire document carefully before doing anything else.

## 1. Project identity (read first)

**agentic-skills** — research/engineering project to build a completely AI-based multi-agent software development team that can autonomously add significant complex features to existing brownfield codebases.

- **Repo:** `/Users/eugenegoldberg/dev/ai-projects/agentic-skills`
- **Active branch (this branch is where harness work lands):** `sprint-2-orchestrator`
- **Brownfield target:** `/Users/eugenegoldberg/dev/ai-projects/brownfield-targets/full-stack-fastapi-template` (symlinked at `webapp/backend/repos/full-stack-fastapi-template`)
- **Current target branch (where agents commit):** `agentic-skills-work-v3` (off pristine `master`)
- **Operator:** Eugene Goldberg (single human operator)

This is NOT an A/B model comparison harness anymore (that was earlier framing). It is NOT a doctrine R&D playground. The goal is the **autonomous team itself**.

## 2. Mandatory reading (in this order)

Read these in full before any action. They are the project's governance docs and they encode hard-won context:

| Order | File | What it is |
|---|---|---|
| 1 | `CLAUDE.md` | Repo orientation — what lives where, two-subproject structure, retrieval stack, brownfield boundary, embedding stack (Ollama bge-m3 + local Milvus) |
| 2 | `THESIS.md` | Vision document — autonomous-team north star, current ~40% slice honest assessment, definition-of-done (7 criteria), sprint themes, success metric (≤1h operator-time-per-feature) |
| 3 | `BACKLOG.md` | 13-ABL roadmap (ABL-0001 Orchestrator was just completed; ABL-0002…ABL-0013 ahead) |
| 4 | `PIPELINE.md` | 8-step pipeline mapped to code paths + gap analysis — authoritative reference for what the orchestrator was supposed to do |
| 5 | **`DESIGN_SHORTCOMINGS.md`** | Audit ledger of 25 anomalies + design weaknesses observed during Sprints 1, 2, 3. Tier A (7 known anomalies with clear fixes) + Tier B (18 deeper design shortcomings). Each entry: evidence, root cause, proposed fix, effort estimate, risk. Decision matrix at the bottom. **Read every entry.** |
| 6 | **`IMPLEMENTATION_PLAN.md`** | The spec for the work you are about to execute. 12 sections, 8 sequenced batches. Per-item: goal, files touched, exact change, risk, mitigation, test, rollback. **This is the contract.** |
| 7 | **`IMPLEMENTATION_TRACKER.md`** | The live checklist. **Only this file changes as you work.** Update it as each item lands. |

## 3. Current state (what's true RIGHT NOW)

### Git state
- `sprint-2-orchestrator` branch carries the orchestrator implementation + the new governance docs. HEAD: `44b872e` (sprint-2 ABL-0001 commit).
- Target repo's `agentic-skills-work-v3` is at `b46b4d6` — contains BL-0001 through BL-0005 of the Notifications sprint. BL-0004 QA doctrine_ok=false (no tests landed). BL-0002 has no scorer (Milvus crashed mid-flight).
- Sprint 1 archive: `agentic-skills-work` branch (target repo). Sprint 2 archive: `agentic-skills-work-v2`. Both preserved untouched.

### Running processes
- **Uvicorn backend:** alive at PID 34768 on port 8000 (orchestrator endpoint registered)
- **Orchestrator script:** NOT running (aborted)
- **Milvus container:** `milvus-standalone` healthy (restarted manually after one crash)
- **Ollama:** serving bge-m3:latest on :11434
- **Watcher script:** PID 56161 was running; may or may not still be (re-check)
- **Live agent claude subprocesses:** 0 (killed during the abort)
- **Leftover worktrees:** none (cleaned)
- **Leftover `agent/*` branches in target:** none (cleaned)

### What's open
- 8-batch implementation plan **written but not executed**. The next session needs to run the pre-flight gate and start Batch 1.
- Decision matrix outcome: **(a) — "Now" set + easy wins** — 18 items: A1, A2, A3, A4, A5, A6, A7, B1, B2, B3, B4, B5, B7, B9, B12, B14, B15, B17, B18.
- Deferred: B6, B8 (cache reuse beyond path move), B10, B11, B13.
- Research probes COMPLETED — findings already informed PLAN. Don't redo them. See `DESIGN_SHORTCOMINGS.md` §"Research findings".

### Anomalies observed across Sprints 2 + 3 (you must understand these — they're the WHY of the plan)
- Orphan claude subprocesses after SSE disconnect (B1)
- No concurrency lock on `/run-brief` (B2)
- QA `git add -A` swept up 178 graphify cache files → ff-merge collisions (B3)
- Operator commit racing agent worktree → non-FF abort (A1)
- QA-doctrine-failed silently marked BL "merged" (A2 + A5)
- Milvus crashed mid-sprint → unrecoverable abort (A3)
- BL-0002 scorer aborted, no score recorded (A4)
- Reader formatter dropped event fields → silent merge failures (A6)
- Playwright flaky tests cause false regressions (M1 — already fixed via gate `CI=1` flag)
- partial_resume proxy fragile (B12)
- AppV2 ignores new event fields (B4)

## 4. Style conventions established (carry forward)

The prior session was held to a strict bar. Maintain it:

1. **No manual artifact fixes.** When an agent fails, harden the framework (new rule, validator, patch). Never hand-edit agent output.
2. **No overclaiming.** If something is half-built or untested, say so explicitly. Honest verification > polish.
3. **Tight prose.** Status snapshots get tables, not paragraphs. End-of-turn summaries ≤ 2 sentences.
4. **Every change clears a bar:** explicit risk, named regression hazard, named test that proves benefit, named rollback. The user explicitly demanded this.
5. **Research before invasive changes.** The prior session ran 5 probes before writing the plan; you should run more if a fix's risk isn't 100% clear.
6. **No `nohup bash -c '...'` chain launchers.** The orchestrator's `/run-brief` endpoint replaces all of these.
7. **TaskCreate/TaskUpdate sparingly.** Tasks live in `IMPLEMENTATION_TRACKER.md`, not in the harness's task tool, except for transient in-session work.
8. **Memory.** Read `MEMORY.md` files for context; the auto-memory system tracks user preferences and feedback.

## 5. Decisions already made (do not re-litigate)

- **Architecture:** Hybrid — Claude CLI subprocess for per-agent execution + LangGraph-style state machine for orchestration. NOT literal LangGraph. (See `PIPELINE.md`.)
- **Sprint 3 target branch:** off pristine `master` (operator chose this knowing Notifications would reference Workspace/Task/Comment that don't exist on v3; PO handled it via generic `entity_type/entity_id` + event-emitter façade with feature flag).
- **Decision (a)** of the fix matrix: "Now" set + easy wins (18 items).
- **Batch 8 (B3 graphify cache refactor)** lands on a **separate quarantine branch** `sprint-2-orchestrator-b3-graphify-cache`, smoke-tested, then merged back.

## 6. Suggested first three turns

### Turn 1 (immediately on start)

Read all 7 documents listed in §2. Don't skim. After reading, restate the plan back to the user in your own words to confirm understanding — specifically:
- The 8 batches and what each does
- Why Batch 8 is quarantined
- The probe findings that revised B1 implementation (process-group kill, not just `proc.terminate()`)
- The probe finding that A1 must rebase **inside the worktree** (`cd wt.path && git rebase`), not in main checkout
- The single-worker uvicorn assumption that B2 depends on

### Turn 2

Run the pre-flight gate from `IMPLEMENTATION_PLAN.md` §0. Report results in a table. Do not skip any check. If any fails, stop and surface to the user before proceeding.

### Turn 3

If pre-flight green, ask the user to confirm "go Batch 1" before any code change. Then execute Batch 1 (A6 + B14 + B15 + B18 — pure observability, zero behavior change), verify per the §2 gate of the plan, commit with the exact message specified, update `IMPLEMENTATION_TRACKER.md`, and report.

## 7. Key file paths cheat sheet

| Purpose | Path |
|---|---|
| Project orientation | `CLAUDE.md` |
| Vision | `THESIS.md` |
| Roadmap | `BACKLOG.md` |
| Pipeline spec | `PIPELINE.md` |
| **Audit ledger** | `DESIGN_SHORTCOMINGS.md` |
| **Implementation spec** | `IMPLEMENTATION_PLAN.md` |
| **Live tracker** | `IMPLEMENTATION_TRACKER.md` |
| Orchestrator service | `webapp/backend/app/services/orchestrator.py` |
| Subprocess runner | `webapp/backend/app/services/claude_agent.py` |
| Doctrine validator | `webapp/backend/app/services/doctrine_validator.py` |
| Indexing service | `webapp/backend/app/services/indexing.py` |
| Retrieval MCP server | `webapp/backend/mcp_servers/retrieval_server.py` |
| Graphify integration | `langgraph_engine/retrieval/graph.py` |
| Web app router | `webapp/backend/app/routers/projects.py` |
| V2 UI | `webapp/frontend/src/AppV2.jsx` (V1 preserved at `AppV1.jsx`) |
| Routing entry | `webapp/frontend/src/main.jsx` |
| Brownfield SKILLS (PO/Eng/QA doctrines) | `skills/brownfield/brownfield-production-incremental-{po,engineer,qa}/SKILLS.md` |
| Scoring rubric | `rubrics/production_grade_scorecard_brownfield.md` |
| Reference repo (retrieval) | `reference-repos/fastapi-good-patterns/` |
| Current brownfield target | `/Users/eugenegoldberg/dev/ai-projects/brownfield-targets/full-stack-fastapi-template` |
| Target's regression gate (PATCHED with `CI=1`) | `<target>/scripts/regression_gate.sh` |
| Target's gate config | `<target>/.agentic-skills.json` (currently → `agentic-skills-work-v3`) |
| Active sprint brief | `/tmp/sprint_brief.md` (Notifications & Activity System, 116 lines) |
| Sprint 2 archive branch | `agentic-skills-work-v2` (in target repo) |
| Sprint 1 archive branch | `agentic-skills-work` (in target repo) |

## 8. Common commands

**Verify backend health:**
```bash
.venv/bin/python -c "import urllib.request, json; d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/openapi.json')); print('OK' if '/api/projects/{repo}/run-brief' in d['paths'] else 'MISSING')"
```
(Run from `webapp/backend/`.)

**Restart uvicorn (clears any stuck generator state):**
```bash
cd webapp/backend && kill $(lsof -ti :8000) 2>/dev/null
sleep 2
nohup .venv/bin/uvicorn app.main:app --port 8000 > /tmp/webapp_backend.log 2>&1 & disown
sleep 4
```

**Cleanup leftover worktrees (target repo):**
```bash
cd /Users/eugenegoldberg/dev/ai-projects/brownfield-targets/full-stack-fastapi-template
git worktree list | tail -n +2 | awk '{print $1}' | while read d; do
  [ -d "$d" ] && git worktree remove --force "$d"
done
git worktree prune
git branch | grep "agent/" | xargs -I {} git branch -D {} 2>/dev/null
```

**Check no live claude agent subprocesses (excluding claude-mem daemon):**
```bash
ps -ef | grep -E "claude.*stream-json" | grep -v grep | grep -v claude-mem | wc -l
```

**Get current v3 HEAD:**
```bash
cd /Users/eugenegoldberg/dev/ai-projects/brownfield-targets/full-stack-fastapi-template && git log --oneline -1 agentic-skills-work-v3
```

## 9. Critical context you MUST internalize before any code change

### The bar
The user explicitly required: **"Before implementing every change, you must do a lot of thinking and research if necessary to develop near 100% confidence in that your change will be beneficial and will not introduce any degradation."** Adopt this as your operating bar for every fix.

### The race condition that aborted Sprint 3
The prior session committed `090d177` (M1 Playwright fix) to v3 while BL-0005's agent worktree was already forked from the older `a08b92d`. The agent branch became a sibling, not a descendant. `git merge --ff-only` correctly refused. The prior session recovered by manually rebasing the agent branch inside the worktree (NOT in main checkout) and ff-merging. **A1 in the plan formalizes this recovery; the probe confirmed the worktree-rebase approach.**

### The graphify-out disaster
QA agents ran `git add -A` and swept 178 AST cache files into the QA commit. Caused ff-merge collisions in Sprint 2 BL-0002 and BL-0004. Mitigated by adding `graphify-out/` to v3's `.gitignore`. Permanent fix is **B3 in Batch 8** — graphify writes to `~/.cache/agentic-skills/graphify/...` instead of the target repo. **High-risk refactor; quarantine branch + smoke test mandatory.**

### The orphan PID problem
When the reader script crashed on a `merged_sha=None` formatter error, FastAPI cancelled the SSE generator BUT the spawned claude subprocess kept running, burning API tokens. **B1 fixes this with `os.setsid` + `os.killpg`** — research-probe confirmed `proc.terminate()` alone leaks child MCP processes.

### What "skip_po=True" means in the orchestrator
Resume mode that reuses an existing BACKLOG.md instead of re-running PO. The orchestrator iterates BLs from start; R11 no-op detection skips ones whose engineer work is already merged; `partial_resume` (newly-added safeguard) runs QA on BLs where engineer is no-op but QA artifacts are missing.

### Doctrine rules currently active
- R5/R5b: ≥3 grounded retrieval calls + citations in QA artifacts
- R7: rubric self-consistency (any brownfield dim ≤ 2 → Fail verdict)
- R8: retrieval budget ceiling (30 calls default)
- R9: graph-grounding floor (≥1 graph_* tool call)
- R10/R10.1: gate-failure auto-recovery (2 retries with focused fix prompt)
- R11: no-op short-circuit when work already shipped
- R12: scorer grounding floor
- Tier 1.5: pre-modification kill (cannot Write/Edit before 3 grounded retrievals)

## 10. Don'ts (from prior-session lessons)

- **DO NOT** commit to the target's `agent_branch` while an agent worktree is active forked off it. (Caused the Sprint 3 abort.)
- **DO NOT** restart uvicorn while an orchestrator run is active. (Loses in-memory state. Once A7 lands, this becomes recoverable.)
- **DO NOT** hand-edit `.agile-v/qa/*.md` or `_brownfield/<BL>/*` files. These belong to the agents.
- **DO NOT** add `partial_resume` heuristics that rely on a single file check — always cross-reference git log (B12 codifies this).
- **DO NOT** use `proc.terminate()` alone on the claude subprocess. Use the pgroup-kill pattern.
- **DO NOT** ask the user yes/no questions about plan items that are already in `IMPLEMENTATION_PLAN.md`. The spec is settled. If a real surprise comes up, document it in `IMPLEMENTATION_TRACKER.md`'s issues log and surface it.
- **DO NOT** skip the pre-flight gate at the start of each batch. It's the cheapest insurance against batch-N regressions.

## 11. Done criteria for the whole engagement

You are done when:

- All 18 in-scope items in `IMPLEMENTATION_TRACKER.md` show `done` with commit refs
- Batch 8 quarantine branch is merged back to `sprint-2-orchestrator`
- A full Sprint 4 run on a fresh feature completes WITHOUT any previously-observed anomaly firing as a bug:
  - 0 orphan claude PIDs after stop
  - 0 gitignore-pollution merge collisions
  - 0 silent QA-doctrine give-ups marked "merged"
  - 0 non-FF aborts from operator commits
  - 0 Milvus-crash mid-sprint aborts
  - 0 `aborted` events with empty reason
  - Logs in `webapp/backend/logs/`, not `/tmp/`

At that point, sprint 4's first commit is the next handoff point.

## 12. Operator's authority

The user (Eugene) has approved:
- Decision (a) of the fix matrix
- The 8-batch sequencing
- Probe-revised implementations (process-group kill, worktree rebase, single-worker lock with documented assumption)
- The two new governance docs (`IMPLEMENTATION_PLAN.md`, `IMPLEMENTATION_TRACKER.md`)

The user **has not** approved:
- Starting Batch 1 — wait for explicit "go Batch 1"
- Any change not in the plan
- Anything in the deferred list (B6, B8 cache reuse, B10, B11, B13)

## 13. First message you should send back

After reading every document in §2, respond with:
1. A 5-bullet recap of what you understand to be the current state
2. The pre-flight gate results in a table (run the checks first)
3. A confirmation that you understand the 8 batches and what each contains
4. A request for the user's explicit "go Batch 1" to start

Do NOT write any code, commit anything, or restart any service in your first response. Read, understand, verify state, confirm.

---PROMPT END---

*Use this prompt as the first message in the new Claude session. The new Claude will know exactly what to do.*
