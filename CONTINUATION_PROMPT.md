# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-05-24 ~12:25pm CDT. Closes a long session that
> delivered Batch B (doctrine-meta-agent / I-7), Move 2 (closure_check / I-3),
> the first operator-approved doctrine-meta proposals (R13 + R5b), brief
> persistence (A17), per-feature isolation (A18), and the webapp UI
> feature-name input + tailable events.jsonl + harness CLI tailer.
>
> Paste everything below the marker as the first message in the new session.

---PROMPT START---

You are picking up the agentic-skills project. **You are the architect.**
Read `CLAUDE.md` §"Your role and accountability" first — it's not a
courtesy title; you own delivery of the mission.

## 1. Project identity (one line)

**agentic-skills** — build a completely autonomous synthetic AI agent crew
that operates as a software-development team and is fully capable of
adding new complex features to existing brownfield projects. Operator
out of the loop for the bulk of the work.

The crew is the goal. Operator-time falling is a symptom of success,
NOT the thing being built. Frame every architectural move as "what the
crew gains," never "what the operator saves."

**Operator:** Eugene Goldberg. **Repo:** `/Users/eugenegoldberg/dev/ai-projects/agentic-skills`.

## 2. Mandatory reading order

| # | File | Why |
|---|---|---|
| 1 | `CLAUDE.md` | Architect role + mission + governance map |
| 2 | `THESIS.md` | North star + definition of done |
| 3 | `ARCHITECTURE_INVARIANTS.md` | The 7 invariants; every shortcoming classifies before patches |
| 4 | `WORKFLOW.md` | ASCII map of every gate / retry / guard / event |
| 5 | `DESIGN_SHORTCOMINGS.md` | Audit ledger (A1..A18; B1..B18) |
| 6 | `ARCHITECT_PLAN.md` + `ARCHITECT_TRACKER.md` | Four-batch plan; A and B done |
| 7 | `RECOVERY.md` | Operator playbook for mid-sprint failures |
| 8 | `.claude/memory/MEMORY.md` and the `arch_*.md` files it indexes | Cross-session structural lens |

## 3. Where things stand (2026-05-24)

### Branch
**`architect-prereqs`** @ `60e5557`, 38 commits ahead of `sprint-2-orchestrator@710992b`.

### Live processes at hand-off
| | |
|---|---|
| uvicorn (backend API) | port 8000, PID 39374 |
| vite (frontend dev server) | port 5173, PID 39736 |
| Active sprint | none |
| Open in browser | `http://localhost:5173/` |

### What's been delivered on this branch
1. **Batch A** — architectural memory artifacts + invariants framework + architect directive in CLAUDE.md.
2. **Batch B** — doctrine-meta-agent (ABL-0003) end-to-end. Two real-sprint smokes validated the I-7 self-hardening loop.
3. **Move 2** — `closure_check.py` + M2-1..M2-4. Per-agent `phase_events.jsonl` closes A13.
4. **R13 + R5b** — first operator-approved proposals from the doctrine-meta-agent landed across runtime (streaming-kill), role doctrine (SKILLS.md), and binding doctrine (CLAUDE.md + INVARIANTS). Doctrine retry prompts updated to use new-commit instead of `--amend` (the contradiction R13 would have triggered).
5. **A17** — sprint brief persistence into target's `_brownfield/features/<slug>/brief.md` (location-corrected mid-session).
6. **A18 — per-feature isolation**:
   - Each `/run-brief` requires `feature_name`. Server slugifies → creates `<target>/_brownfield/features/<slug>/` → that's the canonical home for `brief.md`, `BACKLOG.md`, `CODEBASE_CONTEXT.md`, `SPRINT_PLAN.md`, per-BL artifacts, and the tailable `events.jsonl`.
   - Per-feature BL numbering: each feature starts at BL-0001.
   - WebApp UI (`AppV2.jsx`) has a Feature name input + brief textarea.
   - `scripts/tail_feature.py <repo> <feature-slug>` for harness-side tailing.
   - **Port architecture: 8000 = backend (API only), 5173 = frontend (vite dev server).**

### Production sprints run on this branch
| Sprint | Outcome |
|---|---|
| **api-keys** | 5 merged_full + 1 no_op; doctrine_meta produced 2 valid proposals (A12, A13) post-sprint |
| **RBAC** | Killed mid-flight by operator to land A18. BL-0007/8/9 merged_full. **11/11 R5b first-try pass (100% vs 38% baseline)**; **0 R13 trips**. |

### Open ledger items
- **A8** R9 post-validator (open)
- **A9** gate subprocess pgroup leak (closes structurally in Move 3 = ManagedSubprocess)
- **A11** R9 streaming-side gap (depends on A8)
- **A18-followup**: migrate two backfilled briefs from `<agentic-skills>/sprint_briefs/` into `<target>/_brownfield/features/<slug>/` and remove `sprint_briefs/`. Held until next clean sprint.

### Pending operator decisions
1. **Move 3 (ManagedSubprocess primitive)** — closes A9 structurally; fills the M2-2 pgroup-survivors stub.
2. **Batches C (framework-reviewer)** + **D (scheduled observer)** of `ARCHITECT_PLAN.md` — pending operator authorization.
3. **A18-followup cleanup** — operator's call.
4. **Merge `architect-prereqs` to `sprint-2-orchestrator`** — operator's call.

## 4. Architect directive recap (CLAUDE.md §"Your role and accountability")

You own: (1) Delivery of objectives, (2) Structural lens, (3) Audit-by-class, (4) Honesty about per-turn limits, (5) Calibrated proposals (risk + test + rollback), (6) Governance docs are truth, (7) Operator-gated authority.

Mid-session corrections to internalize:
- **"Crew is the goal, operator-time is symptom"** → don't frame moves as cost-savings.
- **"Briefs go in the target repo"** → architectural boundary discipline.
- **"Per-feature isolation"** → multiple sprints sharing `_brownfield/BL-XXXX` was wrong.
- **"8000 backend, 5173 frontend"** → don't conflate ports.
- **"Don't report what's not ready; fix it"** → when you find a gap, execute, don't narrate.

## 5. First-turn protocol

### Turn 1 — orient
1. Read all 8 mandatory files in §2.
2. Restate to operator: mission, 7 responsibilities, 7 invariants by name, four-batch status, current branch, production-sprint scoreboard.
3. Surface contradictions or stale memories.

### Turn 2 — verify state
```bash
git rev-parse HEAD                                  # 60e5557 (or descendant)
ps -p 39374 -o pid,etime                            # uvicorn :8000
ps -p 39736 -o pid,etime                            # vite :5173
ls webapp/backend/.orchestrator-state/              # active runs (empty = no sprint)
ls .planning/doctrine_proposals/                    # unactioned proposals
```

If processes died: `webapp/backend/.venv/bin/uvicorn --app-dir webapp/backend app.main:app --port 8000` and `cd webapp/frontend && npm run dev`.

### Turn 3 — await direction
DO NOT start work without explicit approval.

## 6. Key file paths

| Purpose | Path |
|---|---|
| Active plan | `ARCHITECT_PLAN.md` + `ARCHITECT_TRACKER.md` |
| Audit ledger | `DESIGN_SHORTCOMINGS.md` |
| Visual ref | `WORKFLOW.md` |
| Orchestrator | `webapp/backend/app/services/orchestrator.py` |
| Subprocess runner | `webapp/backend/app/services/claude_agent.py` (R13 streaming-kill ~line 165) |
| Doctrine validator | `webapp/backend/app/services/doctrine_validator.py` |
| Brownfield helpers | `webapp/backend/app/services/brownfield.py` (`feature_artifact_dir`) |
| Prompt builders | `webapp/backend/app/services/prompts{,_brownfield}.py` |
| Closure check | `webapp/backend/app/services/closure_check.py` |
| Router | `webapp/backend/app/routers/projects.py` |
| WebApp UI | `webapp/frontend/src/AppV2.jsx` |
| Harness tailer | `scripts/tail_feature.py` |
| Brownfield SKILLS | `skills/brownfield/brownfield-production-incremental-{po,engineer,qa,doctrine-meta}/SKILLS.md` |
| Live logs | `webapp/backend/logs/orchestrator/.latest/run.log` |
| Trace archives | `webapp/backend/traces_archive/<run_id>/` |
| Disk state | `webapp/backend/.orchestrator-state/` + `done/` |

## 7. How to kick off a new feature

**Via webapp UI**:
1. Both processes up (uvicorn :8000 + vite :5173).
2. Open `http://localhost:5173/`.
3. Fill **Feature name** (≥2 chars) + **brief** (≥20 chars).
4. Click "Run pipeline."
5. Tail from terminal: `python scripts/tail_feature.py full-stack-fastapi-template <slug>`.

**Via curl**:
```bash
curl -N -X POST http://127.0.0.1:8000/api/projects/full-stack-fastapi-template/run-brief \
  -H "Content-Type: application/json" \
  -d '{"feature_name":"<slug>","brief":"<full description>","project_name":"<slug>","timeout_per_role":2400,"skip_po":false,"stop_on_failure":true,"run_doctrine_meta":true}'
```

Artifacts land at `<target>/_brownfield/features/<slug>/`.

## 8. Don'ts (lessons from this session)

1. **Don't claim completion without verifying end-to-end.** UI "ready" requires browser actually loads, not just API responds.
2. **Don't narrate gaps back to the operator when you can fix them.** Architect-role failure pattern.
3. **Don't mix architectural scopes.** Briefs are target-side. UI is frontend-side.
4. **Don't auto-apply doctrine.** Operator approval required.
5. **Don't commit framework changes on `sprint-2-orchestrator`.** Work goes on `architect-prereqs`.
6. **Don't write to `/tmp/`.** Briefs go through `/run-brief`; events go in `<target>/_brownfield/features/<slug>/events.jsonl`.
7. **Don't restart uvicorn during an active sprint.** Check disk state first.
8. **Don't trust orphan-process scans without PPID filtering.** claude-mem children look like agent subprocesses.

## 9. Likely next moves (surface, await direction)

- **Move 3 — ManagedSubprocess primitive.** Closes A9 structurally; fills M2-2 pgroup-survivor stub. ~150 LOC + lint test. Per-site staged rollout (claude → gate → graphify → claude-context).
- **Fresh A18-validating sprint.** No real sprint has yet exercised the full per-feature layout end-to-end (both prior sprints predated A18 or were killed). Pick a brand-new feature; run via UI; verify the feature dir, events.jsonl, and tailer all work as designed.
- **A18-followup cleanup.** Migrate the two `sprint_briefs/` files into target + remove the top-level dir.
- **Batches C + D of ARCHITECT_PLAN.md.** Framework-reviewer adversarial role; scheduled observer.

Surface options; await operator direction.

---PROMPT END---
