# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-06-03.

---PROMPT START---

You are picking up the agentic-skills project. **You are the architect.**
Read `CLAUDE.md` first — especially the **"Operating principle: quality
over speed"** section (Rules 1–6, the **95% verified/tested certainty
floor**, Rule 3 on **narrative momentum**). The main project is the crew
itself; brownfield targets and their `_brownfield/` derivatives are never
committed to this repo — we only commit/push/maintain agentic-skills.

## ⭐ THIS SESSION'S GOAL (operator-stated, top priority)

**Run a NEW brownfield sprint end-to-end via the web app UI, observe and
react to any findings the acceptance pass exposes, and review / approve
immediate engineering fixes — exercising the new ABL-0021 "Dispatch fix"
flow live.**

This is a **live, operator-driven session.** Your job as architect is to
support the operator through it: get the environment green, launch the
sprint from the UI, watch the stream, and then drive the
findings-review-and-fix loop. Concretely, the loop we are validating:

```
launch sprint (web UI) → BLs run (engineer/QA/scorer, auto-merge)
   → acceptance pass exposes cross-BL findings
   → operator reviews findings in the FindingsTriagePanel
   → Confirm the real ones (verdict)
   → click "🛠 Dispatch fix" → a follow-up engineer fixes it on-demand
   → observe the fix clear the regression gate + auto-merge
```

The "Dispatch fix" facility (ABL-0021) was just built and is the headline
thing to exercise. It needs **no flag** — it's an explicit operator action
on a confirmed product_bug.

### Run from the right branch

**Check out `followup-dispatch-ui`** to run the webapp — it carries
everything this loop needs: the ABL-0015 dispatch engine, the §I.3 triage
panel + verdict/findings endpoints, AND the ABL-0021 `POST
/dispatch-followup` endpoint + the "Dispatch fix" button. (It was branched
off `cumulative_learning`, so it also has ABL-0016 lessons + ABL-0020
registry.)

```bash
cd /Users/eugenegoldberg/dev/ai-projects/agentic-skills
git checkout followup-dispatch-ui && git status -s   # clean, synced
```

### Pre-flight (do the FULL checklist — don't skip)

Run `PREFLIGHT.md` (PF-1..10) before launching: Milvus stack (3 containers
healthy + 19530 reachable), Ollama `bge-m3` + a real embedding probe,
indexer end-to-end against the target, `claude` binary version, target tree
on the right branch/head, leftover worktrees reaped, Docker.raw room,
`254/254` backend tests. Lessons from prior sessions (don'ts §below) bite
hardest when pre-flight is skipped.

### How to launch + what to watch

- Start the webapp per `webapp/PROJECT_STATE.md` §13 ("How to run from a
  fresh clone" — backend uvicorn + `vite`/built frontend). Use **Ctrl+C
  (SIGTERM)** to stop uvicorn, never `kill -9` (the SIGTERM handler reaps
  Docker stacks; A48).
- Submit a brief via the UI (`POST /run-brief` under the hood). Watch the
  SSE stream: per-BL `engineer/qa/scorer`, `regression_gate`,
  `merge_to_target`, then `sprint_complete`, then the **acceptance** phase
  (`acceptance.start` … `acceptance.ledger.appended` with
  `findings_persisted`, `acceptance.done`).
- When acceptance persists findings, the acceptance tile surfaces them and
  the **FindingsTriagePanel** opens in the detail rail.

### The findings-review + fix loop (ABL-0021 — the thing to exercise)

In the FindingsTriagePanel (`webapp/frontend/src/AppV2.jsx`):
1. Each finding shows classification + evidence + a `fix:<state>` badge.
2. **Confirm** a real `product_bug` (verdict). Refute/Defer the others.
3. A **"🛠 Dispatch fix"** button appears on confirmed product_bugs →
   click it → `POST /dispatch-followup` spawns a follow-up engineer,
   streams `acceptance.followup.*` + engineer sub-events live, and shows the
   terminal outcome (✅ merged + sha / ⚠ awaiting review / ❌ error).
4. The fix clears the **same** regression-gate + auto-merge bar as any BL
   (it reuses the ABL-0015 engine). Verify the merge; the finding's
   `dispatch_state` becomes `merged`.

**React to what you see, honestly** (Rule 1/3/6): if the acceptance agent
misclassifies, or a dispatched fix fails the gate, that's signal — capture
it, don't paper over it. A real product_bug example already lives in the
financial-management ledger (Journey 03: `PUT /billing/invoices/{id}`
bypasses the BL-0005 transition state machine) if you want a known case.

## State at hand-off

- **Branch:** `followup-dispatch-ui` (tip `3db7705`), synced with origin.
- **ABL-0021 on-demand "Dispatch fix" — COMPLETE** (this session): backend
  `8bfbec7`, frontend `3db7705`. The only remaining verification is exactly
  this session's live click-through. See `ABL-0021_ONDEMAND_DISPATCH_UI.md`
  + `arch-ondemand-dispatch-ui` memory.
- **Test posture:** 254/254 backend (scoped `cd webapp/backend && pytest
  tests/` — bare pytest recurses into gitignored target repos and errors on
  sqlmodel; not a failure). `vite build` clean.
- Built on: ABL-0015 auto-dispatch engine (flag-OFF), §I.3 findings ledger +
  triage panel, ABL-0016 lessons (flag-OFF), ABL-0020 doctrine-spec registry.

### Optional flags for this session (not required for the Dispatch-fix loop)
- `run_acceptance_followup=true` → ABL-0015 would ALSO auto-dispatch inline
  during the sprint on *pre-confirmed* findings (a fresh sprint's findings
  are pending, so this mostly matters on a re-run). The on-demand button is
  the simpler path and needs no flag.
- `inject_lessons=true` → surfaces prior confirmed lessons to the roles
  (ABL-0016). Independent of the dispatch loop.

## Deferred architect-doable work (AFTER the live session)

1. **ABL-0017 Stage 2 efficacy** (unblocked by ABL-0020) — outcome-label
   deriver → rule-efficacy index (join `doctrine_manifest` × `bl_outcomes`)
   → `retire` proposal kind in doctrine-meta → calibration. Plan:
   `CUMULATIVE_LEARNING_IMPLEMENTATION_PLAN.md` §4.
2. **Branch consolidation** — `architect-prereqs` (ABL-0015), then
   `cumulative_learning` (ABL-0016/0020), then `followup-dispatch-ui`
   (ABL-0021) stack on each other. Consider the merge/PR strategy back to a
   trunk once the live session validates the flow.
3. Two flag-flip calibration smokes still open (ABL-0016 lessons, ABL-0015
   Batch E auto-dispatch).

## Other open ledger items
A39 (gate parser baseline-vs-regressed), A45 (B5 idle-timeout), A47
(ScheduleWakeup/Glob bypass), A48 (closeable), doctrine-meta R-CHAR
characterization-ownership proposal.

## Mandatory reading order
1. `CLAUDE.md` — architect role + Operating principle
2. This file's ⭐ GOAL section
3. `ABL-0021_ONDEMAND_DISPATCH_UI.md` + `webapp/PROJECT_STATE.md` (run + the
   findings/dispatch endpoints) + `PREFLIGHT.md`
4. `THESIS.md`, `ARCHITECTURE_INVARIANTS.md` (if going deeper than the live run)

## Don'ts (carried lessons)
1. Don't commit brownfield targets / `_brownfield/` derivatives — only
   agentic-skills.
2. Don't run `docker … prune -af` without naming what to keep (wiped Milvus
   + a ledger once).
3. Don't skip the full pre-flight after a "clean" cleanup.
4. Don't lose narrative-momentum awareness — read post_tail + gate fields
   carefully every time, even when the pattern looks like prior runs.
5. Don't force-kill uvicorn mid-sprint — Ctrl+C (SIGTERM) reaps Docker
   stacks; worktrees only reap from `finally`.

---PROMPT END---
