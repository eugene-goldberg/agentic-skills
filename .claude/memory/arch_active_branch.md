---
name: arch-active-branch
description: "Branch model (2026-06-07): work on `development`, fast-forward into `main` when verified; these are the ONLY live branches. `followup-dispatch-ui` was merged into main and DELETED (local+remote). Tip @ 78559c3. This session shipped scorer scorecard persistence, the Janitor/Ops role (R16), the item #1 gate fix (pytest parse anchor + run_gate exit-code fallback), and ran the Kanban stress experiment (crew PASSED, all 4 failure predictions falsified)."
metadata:
  node_type: memory
  type: project
  originSessionId: 326d1623-34a0-4f02-8c13-b7359c64685d
---

## Branch model (2026-06-07 — BINDING going forward)
- **`development`** = working tip; **`main`** = stable. New work lands on
  `development`, then `main` is fast-forwarded once verified. These two are the
  ONLY live branches; all others (`webapp`, `skills_with_graphs`,
  `brownfield-production`, `sprint-2-orchestrator`, `architect-prereqs`,
  `cumulative_learning`) are historical/archival.
- **`followup-dispatch-ui` is GONE** — merged into `main`, deleted local+remote
  on 2026-06-07. Do not reference it as active.
- Both `development` and `main` currently at **`78559c3`** (in sync, pushed).
  Mid-session `development` may be N commits ahead of `main`.
- Brownfield targets have their OWN repos (the current target
  `project-management-app` has NO remote — feature work stays local on its
  `integration` branch; never committed into agentic-skills).

## What shipped this session (all on main @ 78559c3)
1. **Scorer scorecard persistence** (`15872ad`) — scorer was gated out of the
   merge block (`role=="qa"`); added a gate-free ff-merge for the read-only
   scorer so `.agile-v/scorecards/<bl>.md` lands. Validated live (scorer
   merged=true 6/6).
2. **Janitor / Ops-Steward role wired with full §6 authority** (`15872ad`, R16)
   — `_janitor_flow` runs in the REAL repo checkout to repair non-code failures
   (merge error / infra_fail / QA-merge-failed); structural anomalies → I-7
   doctrine-meta; advisory contract (never aborts the run); R13 streaming-kill
   is the hard backstop. SKILLS renamed `…-ops` → `…-janitor`. Deferred:
   auto-rerun-after-repair (per-BL body must become retryable first).
3. **Item #1 gate fix** (`dfc00df`) — `PYTEST_RESULT_RE` accepts a dir prefix
   (`backend/tests/…`) + `run_gate` exit-code fallback on unparseable output.
   Proven live: the acceptance regression_checkpoint now returns `green` (was
   `inconclusive`) on the pm-app target.
4. **Kanban stress experiment** (`a8e6ed6`/`78559c3`, `EXPERIMENT_kanban_stress.md`)
   — see [[arch-target-pm-app]]. Crew PASSED: 6/6 merged, migration landmine
   handled (`_migrate_task_rank` ALTER+backfill), optimistic-rollback Playwright
   journey written, acceptance ✅ ACCEPT. Caveat: brief telegraphed the §5
   landmine; checkpoint went green-by-exit-code not by-diff; still the toy
   substrate.

## NEXT (open threads)
- Next probes: (a) §5-withheld discovery variant; (b) Experiment 2 = real
  third-party brownfield repo; (c) gate differential-detection-on-quiet-output
  hardening (checkpoint is green-by-exit-code on `-q` targets).
- Running services: harness orchestrator uvicorn on :8000 (new code); target
  pm-app backend :8002 + frontend :3002 (Kanban board live).

Related: [[feedback-no-abort-persistence]], [[feedback-simple-gating-model]],
[[arch-harness-hardening]], [[arch-acceptance-v02]], [[arch-target-pm-app]],
[[arch-ondemand-dispatch-ui]].
