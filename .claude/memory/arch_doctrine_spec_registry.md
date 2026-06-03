---
name: arch-doctrine-spec-registry
description: ABL-0020 doctrine-spec registry (doctrine_spec.py) — fulfills the standing I-2 mandate (single in-code rule registry + meta-test + CI consistency guard) and adds the per-run doctrine_manifest. The keystone that unblocked ABL-0017 Stage-2 efficacy. Complete on cumulative_learning.
metadata:
  type: project
---

ABL-0020 discharges the long-standing **I-2 architectural mandate** — "a
single doctrine spec data structure (in code, not prose) names each rule,
its enforcement point, and a callable check" + a meta-test — which had been
unfulfilled since the invariants were written. Plan:
`ABL-0020_DOCTRINE_SPEC_REGISTRY.md`.

## How it came about

Started as [[arch-cumulative-learning]]'s **ABL-0017 Batch 0** verification.
The gate found Stage-2 efficacy couldn't attribute outcomes to rules
because there was no registry, no per-run active-rule record, and only
fragmented trigger events (A13). Operator chose **Option C** (keystone
first). The Batch-0 gate working as designed — it caught a blocker before
any efficacy code was written.

## What shipped (branch `cumulative_learning`)

- **A (`624886f`)** `app/services/doctrine_spec.py`: `DoctrineRule` +
  `DOCTRINE_SPEC` for all 13 canonical rules (R5, R5b, R7, R8, R9, R10,
  R10.1, R10.2, R11, R12, R13, R15, Tier1.5). Each: `enforcement_point`,
  `enforced`, resolvable `check_ref` ("module:symbol"), `has_test`,
  `targeted_failure_class` (the I-6 class the rule reduces — the Stage-2
  hook). `KNOWN_GAPS={R9}` (A8). `resolve_check()` imports the symbol;
  `manifest()` emits the per-run snapshot. I-2 meta-test in
  `tests/test_doctrine_spec.py`.
- **B (`016ef5c`)** per-run `doctrine_manifest` (= `manifest()` +
  `traces.harness_sha()`) written into `.orchestrator-state/<run_id>.json`
  via `run_state.write_checkpoint` (new nullable param), built once in
  `run_brief`. Survives terminate into `done/`.
- **C (`db7d8d7`)** CI consistency guard
  (`test_registry_matches_claude_prose_table`) fails if the registry and
  CLAUDE.md's R-rules table drift → registry is the source of truth. I-2
  marked **FULFILLED** in ARCHITECTURE_INVARIANTS.md. 248/248 tests.

## Why it matters

Two payoffs: (1) discharged the oldest architectural debt — doctrine is now
machine-readable and CI-enforced (add a rule to prose without registering
it w/ enforcement + check → build fails). (2) Unblocked **ABL-0017 Stage
2**: both halves of the efficacy input contract now persist per run —
`bl_outcomes` (run_state) + `doctrine_manifest`.

## Residual / follow-up

R9 is the one declared gap (A8). Full per-rule **synthetic-harness tests**
(I-2's third bullet) are follow-up; `has_test` tracks per-rule coverage.
Per-rule **trigger events** (A13 closure) deferred — Stage-2 efficacy v1 is
medium-fidelity (knows which rules were active, not every fire).
