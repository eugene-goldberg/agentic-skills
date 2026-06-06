---
name: feedback-simple-gating-model
description: "Operator directive 2026-06-06 (BINDING): the gating model must be SIMPLE. Per-BL = engineer writes code per PO spec + comprehensive UNIT tests for that BL; QA runs ONLY that BL's tests. Repeat per BL. After the LAST BL, the acceptance agent writes ONE comprehensive whole-feature E2E (Playwright ONLY if the feature has UI journeys) and MUST create+execute all API-based testing regardless of UI. NO per-BL full-regression suite, NO per-BL Playwright. Replaces the diff-blind full-suite-per-BL regression gate I over-built."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 48e5d2ed-b267-495f-91d2-00b7a0b8acbb
---

## The simple gating model (operator, 2026-06-06 — BINDING)

Operator feedback verbatim intent: *"YOU have made this gating system complex
and unreliable. The logic must be simple."*

**Per-BL cycle (repeat for every BL):**
1. The **engineer** agent writes the code per the PO's spec for that BL.
2. The **engineer** agent writes **unit tests** giving comprehensive coverage of
   that BL.
3. The **QA** agent executes **only the tests associated with that BL** (the BL's
   own tests) — NOT the whole regression suite, NOT Playwright.

**End of sprint (after the LAST BL):**
4. The **acceptance** agent creates ONE **comprehensive whole-feature E2E** that
   tests the entire sprint/feature as a whole.
   - Playwright is used **only IF the feature involves UI journeys.**
   - The acceptance agent **must create and execute all API-based testing
     regardless of UI/Playwright** (API testing is mandatory and unconditional).

## Why (the complexity this removes)

The pre-2026-06-06 per-BL `regression_gate.run_gate` ran a **diff-blind full
`test_cmd`** (frontend lint + full backend pytest + full Playwright E2E) as a
pre/post differential **on every BL, for engineer AND QA**. Consequences this
caused (item-comments run `…251422`, BL-0001):
- A **backend-only, correctly-scoped** BL still triggered the full ~71-spec
  Playwright suite → load-induced flaky **false red** on a byte-identical
  frontend → the no-abort loop then **thrashed 6→157** (backend stack died under
  overload). The crew was correct; the GATE was the failure.
- Much of A39 (playwright expansion), A49 (transient markers), A28–A31
  (throughput) machinery existed only to cope with running Playwright/full-suite
  **per BL** — which this model deletes outright.

## How to apply

- **Per-BL gate = run only that BL's own tests** (unit/integration tests the
  engineer wrote for the BL). Backend-only BL → backend tests only; no E2E.
- **No per-BL Playwright, no per-BL full-regression differential.**
- **E2E lives ONLY at acceptance** (whole-feature, end of sprint), Playwright
  gated on "does this feature have UI journeys"; **API testing always**.
- This composes with [[feedback-no-abort-persistence]]: deep persistence is only
  safe on a trustworthy signal — running only the BL's own scoped tests removes
  the false-red surface that made persistence dangerous.

## OPEN fork (confirm before/while implementing)
Under this model, a BL that breaks **pre-existing / unrelated** functionality is
no longer caught per-BL (per-BL runs only the BL's own tests). Such regressions
would surface (if at all) at the acceptance phase. Operator to confirm whether
that is acceptable (simplest, intended) OR whether the acceptance pass must also
re-run the pre-existing suite as the integration safety net. Default assumption
pending confirmation: per-BL = BL tests only; acceptance = whole-feature E2E +
all-API + (re-run existing suite as the single regression checkpoint).

Related: [[feedback-no-abort-persistence]], [[arch-gate-throughput]],
`DESIGN_SHORTCOMINGS.md` A30/A31 (now superseded — per-BL E2E is removed, not
optimized).
