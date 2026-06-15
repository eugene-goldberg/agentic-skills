---
name: arch_order_fulfillment_wave_proof
description: Order-fulfillment feature delivered + 100% live-accepted; wave program P1-P3 live-proven; acceptance reround worktree-collision bug fixed
metadata: 
  node_type: memory
  type: project
  originSessionId: 187bf7cc-22b5-4ced-9c4e-2a50c2bc4bf5
---

2026-06-14, run-20260614T143621Z-0b7c91 (fullstack-ecommerce-app, `wave_execution=True`):
first end-to-end live-proof of the parallel-wave program AND a clean major-feature delivery.

**Delivered + 100% live-accepted:** Order Fulfillment Lifecycle (state machine
Pending→Processing→Completed/Canceled + RBAC admin-advance + owner-cancel-while-Pending +
customer status-tracker UI + admin console UI). 5 BLs all merged_full; integration @ `f7f2283`
(31 commits over baseline 3028cce). Final acceptance (reacc2): **integrity_ok=true,
acceptance_clean=true, 11/11 journeys (3 UI + 8 API), 0 unverified, 0 anomalies.**

**Wave program P1+P2+P3 LIVE-PROVEN `[x]`:** PO emitted a real R21 DAG (5 BLs, 4 topological
waves W0=[1] W1=[2,3] W2=[4] W3=[5]); PO gate accepted it; `orchestrator.wave.start/done`
fired per wave; `reindex_after_wave.{0,1,2,3}` fired at each barrier with **0 per-BL reindex**
(reindex cadence 2/BL → 1/wave). Still concurrency=1 (serial within a wave). See
[[arch_inventory_run_and_wave_proposal]] and PROPOSAL_PARALLEL_WAVE_EXECUTION.md.

**Live-acceptance loop worked `[x]`:** acceptance booted the real app (5096+5173), drove
Playwright, found **2 real UI product_bugs** the mock per-BL gates passed (blank customer page =
@auth-kit requiring hoisted react-router@7 not 6.x; admin Login-shown-to-admin = AdminRoutes
gating on localStorage[userData] never written), root-caused with falsification, auto-dispatched
fixes (independent of the followup flag), both merged + confirmed.

**HARNESS BUG found + FIXED — acceptance reround worktree collision (`c8ccc76`):** the original
run ESCALATED (integrity_ok=false) NOT from a capability wall but because the live-acceptance
convergence loop's round-2 re-verify died at `git worktree add -b agent/accept-<run_id>` — round
1 already created that branch. Root cause: the loop round-tagged only the TraceWriter task_id;
`_acceptance_flow` built the worktree branch from raw `run_id` (constant across rounds). Fix:
`_accept_worktree_task_id(run_id, round)` (round 1 = historical `accept-<run_id>`; rounds ≥2 =
`-r<round>`) + thread `accept_round` through `_acceptance_flow`. Tests: 3 naming unit + 1
**real-git integration test** (reproduces the collision + proves the fix). Mechanism live-proven
`[x]`; end-to-end reround `[~]` pending a natural reround. 537 remote tests green.

**A55-class finding (lint false-red):** integrity_ok=false initially blocked ONLY by AC-BL-0004-4
/ AC-BL-0005-5 requiring whole-frontend `npm run lint` clean, which failed on 14 PRE-EXISTING
baseline lint errors in cart/product/auth code the feature never touched — a diff-blind
whole-codebase check manufacturing a false-red (same class as A55). Operator directed hand-fixing
the 14 (vs the diff-scope crew fix I recommended); fixed (lint+build clean, target commit
cf20499) → reacc2 integrity_ok=true. The structural lesson (diff-scope acceptance lint / don't let
PO write whole-codebase-clean criteria on brownfield) remains an open crew-improvement. Process
note: `/run-acceptance` is single-shot (no reround); re-runs need a FRESH run_id (same run_id
collides on the leaked `agent/accept-*` branch). 8 leaked accept branches + a 26h-old vite proc =
hygiene debt.

**Wave concurrency>1 (Strategy A) — BUILT + LIVE-PROVEN `[x]` 2026-06-15** on branch
`wave-concurrency` @ `3e7efd5` (NOT yet merged to dev/main). Primitives: `_merge_streams` (async
fan-in), `merge_branch_into_target` (real 3-way barrier merge, git_worktree.py:264),
`_run_wave_concurrent` (orchestration), `_one_bl_concurrent` + the `_concurrent_wave_mode` dispatch
in run_brief (orchestrator.py, _run_wave_concurrent CALLED at :4461). Flag `wave_concurrency:int=1`
(>1 opt-in; serial path byte-identical, 557 tests). LIVE PROOF run-20260615T010822Z-36f623
(fullstack-ecommerce-app, wave_concurrency=2, 2 independent diag endpoints → 1 wave
[BL-0001,BL-0002]): both engineers spawned the SAME second (013146Z trace dirs), overlapping
engineer.start before either done, 2 claude agents ran concurrently, both emitted `work_ready`
(defer-merge); barrier assembled both ok:true in BL-id order (BL-0001 noop, BL-0002 real 3-way
merge), 0 conflicts; both merged_full; DiagPing+DiagTime controllers+tests delivered to integration
@ 07ab2cd (sprint_complete was pending the barrier reindex at report time — terminal formality,
run_acceptance=False). **OPEN NUANCE to investigate:** BL-0001 assembled as `noop` (already in
integration) + its commits sit directly on integration while BL-0002 came via a merge commit —
suggests BL-0001 may not have FULLY deferred its trunk merge (likely the engineer non_ff rebase
path or QA merge_target lineage landing it early). Harmless here (both delivered, no conflict) but
could matter under a real file conflict — needs a follow-up + a deliberately-conflicting-pair live
test before merging concurrency>1 to dev/main. See [[feedback_remote_first_dev]].


**UPDATE 2026-06-15 — concurrency>1 follow-ups CLOSED + MERGED to dev/main `4265640`.**
The BL-0001 noop nuance was root-caused: the scorer in `_one_bl_concurrent` was invoked WITHOUT
`merge_target_override`, so `_qa_or_scorer_flow` defaulted its merge target to the trunk and the
scorecard FF-merge landed BL work on the trunk mid-wave. Fix `6c5f45e` (pass
`merge_target_override=work_branch` to the scorer, symmetric with QA; AST guard); BL-0001 now
assembles `kind:merged` via the barrier, not noop. Conflicting-pair LIVE-PROVEN
(run-20260615T024030Z-bcef22 + clean re-proof …033033Z-1dc152): two same-wave BLs both create
`ConflictProbe.cs` -> BL-0002 real git add/add `kind:conflict` -> `bl.escalated(role=assembly)`
no-abort, trunk=alpha only (deterministic), BL-0002 work preserved on its branch, sprint_complete
(not aborted). That run exposed + FIXED an I-5 bug (`bl_outcomes` mislabeled the conflicted BL
`merged_full`) via extracted+unit-tested `_reconcile_unassembled_outcome` ->
`escalated_assembly_conflict` (1c7c02f). Scale LIVE-PROVEN (run-…041351Z-fc2e21): 5 disjoint BLs,
`wave_concurrency=3`, wave0 3-wide + wave1 2-wide multi-wave, 5/5 merged_full, 0 escalations,
52GB free / load ~6 of 12 cores (no resource blowup). Merged FF wave-concurrency->development->
main @ `4265640`; docs updated (projects.py stale comment, CLAUDE.md R21 row). OPEN (non-blocking):
assembly-conflict auto-repair-loop scope decision (surface+escalate is the correct floor;
Concurrency_Assessment_01.md raises it); reindex latency (full op=index per barrier); one stale
vite proc + leaked accept-…05b6e9 worktree to reap. See [[feedback_remote_first_dev]].
