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
- Both `development` and `main` currently at **`b7ab0b9`** (2026-06-08; in sync).
  Mid-session `development` may be N commits ahead of `main`.
- Since `78559c3`: Exp 1b (crew PASSED no-telegraph discovery, 6/6); A56 warm-up
  (live); the **self-resolution arc A57–A61** (crew now resolves merge failures +
  acceptance findings autonomously) — see [[arch_self_resolution_arc]]; and the
  first REAL third-party brownfield (`beaverhabits`, [[arch_target_beaverhabits]])
  delivering "Rest Days" end-to-end (99 green). Frontier now = the CUMULATIVE
  property ([[arch_cumulative_learning]]). DOCTRINE:
  [[feedback_improve_crew_not_accommodate]] (improve crew generally; don't
  accommodate one target; don't abdicate; 95%=rigor-before-act).
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
- **Exp-2 substrate now ESTABLISHED** (`beaverhabits` wired + gate-green); the
  remaining step is to brief + launch a feature on it (candidate: streak
  freeze/backfill). Other open: gate differential-detection-on-quiet-output
  hardening (checkpoint green-by-exit-code on `-q` targets); A56 sub-items
  (eager retrieval / A51 containment verify).
- Running services: harness orchestrator uvicorn on :8000 (new code); target
  pm-app backend :8002 + frontend :3002 (Kanban board live).

Related: [[feedback-no-abort-persistence]], [[feedback-simple-gating-model]],
[[arch-harness-hardening]], [[arch-acceptance-v02]], [[arch-target-pm-app]],
[[arch-ondemand-dispatch-ui]].
