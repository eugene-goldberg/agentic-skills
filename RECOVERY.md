# Operator Recovery Playbook

Mid-sprint failures the orchestrator can't self-heal end up in one of a few
states. This document maps each state to the fastest path back to forward
motion. Built from the Sprint 2 + Sprint 3 incident ledger
(`DESIGN_SHORTCOMINGS.md`).

> The bar: never hand-edit agent artifacts. Always re-invoke the framework with
> the right knob.

---

## Quick decision tree

```
Sprint aborted mid-flight?
├── Process crashed entirely (uvicorn died, watcher killed, OS panic)
│       → Resume via "Crash-restart" below
│
├── Specific BL has engineer+qa merged but NO scorer
│       → Backfill via "Score-only" below
│
├── Specific BL has only engineer (no qa, no scorer)
│       → Resume from that BL via "start-from-BL" below
│
├── Non-FF merge collision (operator commit raced agent worktree)
│       → A1 should auto-rebase. If `merge_rebase_failed` event fired,
│         do "Conflict resolution" below.
│
└── Milvus / claude-context crashed
        → A3 should auto-restart. If the auto-restart hit its cooldown,
          do "Manual Milvus restart" below.
```

---

## Crash-restart (resume an interrupted /run-brief)

**Symptom:** uvicorn or the driver script died mid-sprint. Agent branch
shows some BLs landed; the rest never ran. `webapp/backend/.orchestrator-state/`
has a JSON file for this run.

**Procedure:**

```bash
# 1. Confirm the orphaned state exists
ls webapp/backend/.orchestrator-state/run-*.json

# 2. Re-POST the SAME brief with skip_po=true
curl -X POST http://127.0.0.1:8000/api/projects/<repo>/run-brief \
  -H 'Content-Type: application/json' \
  -d '{
    "brief": "...same brief text...",
    "project_name": "<same>",
    "skip_po": true
  }'
```

The router (A7) detects the orphan, reuses the prior `run_id`, and proceeds.
The orchestrator's R11 no_op short-circuit + B12 partial_resume reconstruct
per-BL state from git history.

**To discard instead of resuming:**

```bash
rm webapp/backend/.orchestrator-state/<run_id>.json
# Then POST normally (skip_po=false will re-run PO from scratch).
```

---

## Score-only backfill (single BL, scorer missing)

**Symptom:** Engineer + QA both merged for `BL-XXXX`, but no scorer row
exists in the scorecard. Caused by the orchestrator aborting between QA and
scorer (Sprint 3 BL-0002 case).

**Procedure:**

```bash
curl -X POST http://127.0.0.1:8000/api/projects/<repo>/score-bl \
  -H 'Content-Type: application/json' \
  -d '{"bl_id":"BL-XXXX"}'
```

The `/score-bl` endpoint reads engineer+QA commits from `agent_branch` and
runs the scorer agent against the existing artifacts. It does NOT re-run
engineer or QA.

---

## Start-from-BL (resume from a specific BL onward)

**Symptom:** Mid-sprint abort left BLs 1..N merged, BL N+1 partial (engineer
ran but QA didn't), and BLs N+2..end never started. You want to redo BL N+1
from QA and then continue.

**Procedure:**

```bash
curl -X POST http://127.0.0.1:8000/api/projects/<repo>/run-brief \
  -H 'Content-Type: application/json' \
  -d '{
    "brief": "...same brief...",
    "project_name": "<same>",
    "skip_po": true,
    "start_bl": "BL-XXXX"
  }'
```

The orchestrator iterates BLs in dep-order. BLs before `start_bl` emit
`bl.skipped` events. Starting at `start_bl`, the normal R11 no_op short-circuit
applies (so already-merged BLs skip quickly).

> Limitation: `start_bl` is a string match, not a dep-graph slice. If
> `BL-XXXX` depends on something that's NOT yet merged, you'll get an
> `engineer_unmerged` outcome. Run with `skip_po=true` only after confirming
> the prerequisites are on `agent_branch`.

---

## Conflict resolution (A1 rebase failed)

**Symptom:** SSE log shows `merge_rebase_failed` event after a non-FF.
Worktree was left clean by `git rebase --abort`. Agent branch hasn't moved.

**Procedure:**

```bash
cd <target-repo>
git checkout agentic-skills-work-vN   # the agent_branch
git rebase <target-ref>               # resolve conflicts by hand
# After conflicts resolved + tests green:
# Re-POST /run-brief with skip_po=true to let the orchestrator finish.
```

The orchestrator will treat the now-merged BL as `no_op` via R11 and move on.

---

## Manual Milvus restart (A3 cooldown active)

**Symptom:** Preflight returns `retrieval unavailable; auto-restart attempt:
cooldown active`. Means A3 tried and failed within the last 60 seconds.

**Procedure:**

```bash
docker logs milvus-standalone --tail 100   # investigate
docker restart milvus-standalone
sleep 10
# Then re-POST /run-brief. Preflight will see the port open and skip restart.
```

If `docker restart` fails repeatedly, the container is likely
configuration-broken — outside scope for the orchestrator to recover. Fix
the container config, then resume via crash-restart above.

---

## What NOT to do

- **Don't** hand-edit `.agile-v/qa/<bl>.md` or `_brownfield/<BL>/` files.
  The orchestrator owns those; you'll break partial_resume's git-log
  cross-check (B12).
- **Don't** delete trace dirs from `webapp/backend/traces/<repo>/` while a
  run is active. They become evidence for scorers.
- **Don't** force-push the agent_branch. The doctrine validator + scorer
  rely on linear, append-only history.
- **Don't** restart uvicorn while an orchestrator run is active unless you
  also intend to discard the run. A7's disk state lets you resume — but
  the in-flight subprocess will be orphaned (mitigated by B1 pgroup-kill
  on SIGTERM if you kill cleanly).

---

*Authored 2026-05-23. Lives next to `IMPLEMENTATION_PLAN.md` /
`IMPLEMENTATION_TRACKER.md` / `DESIGN_SHORTCOMINGS.md`.*
