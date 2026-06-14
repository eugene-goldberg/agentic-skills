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

dev≡main≡origin≡remote(180) @ `e5def05`. Relates to [[arch_live_acceptance_loop]]
(CONVERGED), [[arch_zero_escape_chain]], [[feedback_baseline_auth_inscope]].
