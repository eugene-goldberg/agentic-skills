---
name: arch_inventory_run_and_wave_proposal
description: Inventory & stock-enforcement sprint — 2nd clean live-acceptance delivery + the crew correctly solved an un-telegraphed concurrency invariant. Plus the parallel-wave-execution proposal.
metadata: 
  node_type: memory
  type: project
  originSessionId: 154fb558-ad8d-47e9-b9fa-cbac688b2031
---

**Inventory & stock enforcement — `run-20260614T025948Z-0c2a26`, 2026-06-14.** Second
clean end-to-end live-acceptance delivery (after ecommerce-reviews) — proves the
live-acceptance loop generalizes beyond one feature. A genuinely HARD, sensitive-core-path
feature (touched the order-placement path the reviews brief had said "don't touch"),
delivered **unattended, zero escalations/coverage-gaps/janitor across ~4.5h.**

The feature: wire stock enforcement into order placement. The grounding hook — `Product`
already exposed `Quantity` + `IsInStock()`/`UpdateStock(int)` but they were UNWIRED dead
code (the cross-target "computation exists at one layer, consumers use the legacy path"
lesson, live). PO decomposed into 4 BLs (BL-0002 = the hard atomic-decrement). All
`merged_full`; regression checkpoint green; `acceptance.loop.accepted` round 1
(integrity_ok=true, unverified_criteria=[]); evidence persisted in-target on `integration`
`3028cce` (report.json + 11 Playwright screenshots — out-of-stock badge + disabled
add-to-cart visually confirmed).

**Experiment scorecard P1–P5 all PASS (verified, not self-reported):** P1 reinvention
avoided (used existing primitives + new method); P2 multi-line atomicity (`TransactionScope`);
**P3 oversell race — the un-telegraphed probe — PASS**: the crew DISCOVERED the
concurrency requirement and shipped the textbook-correct atomic compare-and-swap
`TryDecrementStockAsync`: `ExecuteUpdateAsync(... WHERE Quantity >= quantity)`, rowsAffected>0
→ else ResourceConflictException + rollback — NOT a check-then-act TOCTOU race; P4
server-side enforcement (not UI-only); P5 regression green. Tests covered B.3–B.6 + edges
(cumulative same-product lines, race-despite-in-memory-stock). Senior-engineer-level work.

**Cost observation (motivates the wave proposal):** the run was SERIAL and
reindex-dominated — 8 full bge-m3 reindexes (2/BL), ~4.5h wall-clock. See [[arch_double_reindex]]
rationale in orchestrator.py (reindex_after_engineer feeds QA, reindex_after_qa feeds
scorer+next-BL).

**`PROPOSAL_PARALLEL_WAVE_EXECUTION.md` (committed `e5def05`, UNAPPROVED).** Architect
response to the operator's parallel-execution target sketch. Grounded in human practice
(trunk-based CI beats merge-at-end; contract-first interfaces; stacked-PRs = DAG;
conflict-disjoint decomposition). Proposes **DAG-scheduled waves** (parallel within a wave,
sequenced across), **contract-first PO interface definition** as a first-class new
responsibility (new **R21**: every BL declares deps + interface contracts; enforced at
`validate_po`), **merge-PER-WAVE not merge-at-end** (the end-merge is the human
anti-pattern), conflict-resolver agent at the wave barrier, accept-on-scratch-assembled
branch. KEEP: Janitor/no-abort, regression checkpoint, live-acceptance loop,
persist-in-target, closure, doctrine-meta. Flag `wave_execution` default OFF = today's
sequential loop (the degenerate 1-BL-per-wave case). 7-phase build plan; phase 1 (PO DAG +
contracts) delivers value before any parallelism. Inventory would be ~3 waves (~4 reindexes
not 8, 3 BLs concurrent) ≈ 2× wall-clock cut, no correctness loss.

**Phase 1 SHIPPED + LIVE 2026-06-14 (`efa9da9`).** Operator approved the proposal, "start
with phase 1." R21 implemented (validation-only, NO execution change — sequential loop
unchanged): PO declares per-BL `**Dependencies:**` (BL-id DAG) + `**Exposes:**`/`**Consumes:**`
contracts; `validate_po` enforces via `backlog.dependency_report` (missing-field/dangling-ref/
self-loop/cycle — zero false-positive risk) + `contract_report` (consumed iface must be
exposed by a declared dep; fires only when **Consumes:** present); `build_deps_contracts_fix_prompt`
in the existing PO doctrine-retry loop. `topological_waves` (Kahn) added now as the Phase-2
scheduler primitive. R21 in doctrine_spec + CLAUDE.md table (parity green) + PO SKILL. 13 new
tests; full suite **526 passed, 1 skipped**. Deployed to remote + harness restarted (pid
2052628) so R21 is live. NOT yet exercised by a live PO run — next sprint's PO will be the
first to produce the DAG/contracts. Phase 2 (wave scheduler) is the next step when approved.

**Phase 2 SHIPPED 2026-06-14.** The wave SCHEDULER (operator "proceed with phase 2").
`orchestrator._dep_waves(items)` groups BLs by the R21 DAG into topological waves
(reuses `backlog.topological_waves`, degrades to one wave on cycle); `run_brief` gains a
`wave_execution` flag (DEFAULT OFF = today's flat `_dep_order`) + `RunBriefRequest.wave_execution`;
the per-BL loop emits `orchestrator.wave.start`/`wave.done` boundary events as the flattened
order crosses DAG layers, and `backlog_parsed` carries the `waves` shape. **concurrency=1
within a wave — the proposal's "degenerate case": byte-identical per-BL semantics, the
delicate per-BL body TOUCHED ZERO; OFF = exactly today.** 6 new tests (test_wave_scheduler.py),
full suite **532 passed, 1 skipped**. This is pure scaffolding (no runtime win yet) — the
schedule the operator sees at the PO gate is now the one that runs. **NEXT (Phase 3):
reindex-AT-the-wave-barrier (1/wave not 2/BL) = the measurable wall-clock win; then raise
concurrency>1 for true intra-wave parallelism (the async event-stream merge — the genuinely
risky part, its own phase + live proof). Phase 4: conflict-resolver agent at the barrier +
accept-on-scratch-assembled-branch.** Flags `wave_execution` (Phase 2) stays OFF until
live-proven by a real sprint.

**Phase 3 SHIPPED 2026-06-14 (`22bb1d0`, remote-first).** Reindex AT the wave barrier
(1/wave) instead of 2/BL — the measurable wall-clock win, same `wave_execution` flag. The 3
per-BL reindexes (reindex_after_engineer ×2 incl. A59 path, reindex_after_qa) are guarded by
`if not wave_execution`; in wave mode ONE `reindex_after_wave.<n>` fires at each barrier
(between waves so the dependent next wave grounds on the completed wave's merges; + a final
one for acceptance/pattern-profile). Correctness = R21 invariant (same-wave BLs independent →
ground on the previous barrier's index). Inventory (4 BLs, 2 waves): 8 reindexes → 2 (~2×
cut). OFF path unchanged; remote full suite 533 passed. **Reindex-at-barrier behavior `[~]`
pending a live wave_execution=True sprint** (the natural next milestone: live-prove Phases
1–3 together on a real brief). Remaining proposal phases: concurrency>1 true intra-wave
parallelism (the async event-stream merge — riskiest, own phase) + Phase 4 conflict-resolver
+ accept-on-scratch-branch. First substantial REMOTE-FIRST code work (edited+tested+committed
+pushed all on 180; Mac pulled) — also surfaced+fixed the [[arch_findings_ledger_race]].

dev≡main≡origin≡remote(180) @ `22bb1d0`. Relates to [[arch_live_acceptance_loop]]
(CONVERGED), [[arch_zero_escape_chain]], [[feedback_baseline_auth_inscope]],
[[arch_doctrine_contract]] (I-2).
