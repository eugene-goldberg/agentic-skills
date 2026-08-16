---
name: arch-autonomy-hardening
description: 2026-08-15 audit found mission-blockers C1–C5/M1–M4 (A49–A57); AUTONOMY_HARDENING_PLAN Batches 0–7 ALL shipped on branch autonomy-hardening (291/291); live smokes blocked on env restore
metadata:
  type: project
---

The 2026-08-15 code audit identified what blocks THESIS.md's "walk away"
goal: C1 sprint-dies-with-SSE (A34), C2 no judgment layer + dep DAG
didn't gate (A49), C3 post-merge quality has no teeth/no revert (A50),
C4 lying signals (A39/A44/A45), C5 economics, M1 amnesia, M2–M4 hygiene
(A51–A53). Small defects A54–A57.

**Shipped on `autonomy-hardening`** (off architect-prereqs @ 8745331),
suite 266/266: Batch 1 run_registry (detached runs, resumable
`/api/runs/{id}/events`, explicit abort); Batch 2 gate `build_fail` +
`gate_failure_class` + regressed⇒non-empty, api_error infra-retry
(`_stream_role_attempt` wraps all 8 role spawns), idle-clock suspension
while tool in flight; Batch 3 dep-gating (`deferred_dep`,
`complete_with_deferrals`) + triage agent v1 + **R16** (flag
`run_triage=False`); Batch 4 `merged_score_failed` outcome +
`revert_bl_span` + `POST /revert-bl {confirm:true}`.

**Why:** every prior sprint abort in the ledger terminated in the
abort-or-blind-continue code path; these batches convert failure into
routed decisions. Operator decisions D1–D6 recorded in the plan header.

Batches 5–7 shipped 2026-08-16: Batch 5 A29 PRE-cache + cost
aggregation + max_sprint_usd (`f5ab92c`); Batch 6 LESSONS.jsonl sprint
memory + prompt injection (`9e33cfc`); Batch 7 A51 checkout preflight +
verified PO commit, A53 indexer health + Milvus restart, A52 agent env
allowlist + HARNESS.md §11 trust model (`855f62b`).

**How to apply:** the plan is fully executed (see
AUTONOMY_HARDENING_TRACKER.md sign-offs); only 5-1 (target-side
playwright workers) + live smokes + calibration sprints remain, all
blocked on the environment restore (targets/Milvus/Ollama gone from
/Users/egoldberg). New flags stay OFF until calibration. The A45 test is
timing-sensitive (~2.1s fake-CLI spawn latency on this Mac): widen
margins, never weaken assertions.
