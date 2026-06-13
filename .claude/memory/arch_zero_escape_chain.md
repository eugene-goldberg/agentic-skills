---
name: arch_zero_escape_chain
description: "The zero-defect-escape chain (R18→R19→R20+R17) — PO criteria→engineer coverage→acceptance live-verify→always-dispatch; built 2026-06-12, live-proving on ecommerce reviews"
metadata: 
  node_type: memory
  type: project
  originSessionId: 36f446e4-bf0d-4484-aecb-c91ae129c9d8
---

**Operator directive 2026-06-12 (BINDING):** PO always writes comprehensive acceptance
criteria per BL; engineer always covers every criterion with tests; acceptance always
live-verifies every criterion in production; every detected failure always dispatches a
followup engineer; 0% detected-defect escape.

Built as a 4-gate chain on the **acceptance criterion** (`AC-<BL>-<n>`) as unit of truth.
On `development`≡`main`≡`origin` @ `6e2c096` (FF'd 2026-06-12). 478 backend tests pass.

- **R18** (`validate_po` + `backlog.thin_criteria_report`): a BL with <2 substantive
  criteria fails the PO gate → existing doctrine retry re-prompts (criteria fix prompt
  allowed to edit BACKLOG). PO SKILLS mandate.
- **R19** (`regression_gate.run_bl_tests(bl_id,feature_slug)`): per-BL gate scans the BL's
  changed tests for every `AC-<BL>-<n>`; unreferenced → `coverage_gap` (blocking) →
  no-abort fix loop. Language-agnostic substring scan. Engineer SKILLS mandate.
- **R20** (`_acceptance_flow._unverified_criteria` + `ac_coverage` cross-check): acceptance
  emits per-criterion `ac_coverage`; any criterion not `verified` → `criterion_unverified`
  anomaly → non-clean. Acceptance SKILLS mandate.
- **R17 + always-dispatch:** observed-real-journey-failure product_bug findings auto-dispatch
  INDEPENDENT of the calibration-gated `run_acceptance_followup`; `FOLLOWUP_COST_CAP` 1→25
  (no silent drop); zero-false-merge preserved (product_bug + conf≥0.90 + cost_cap + R15 +
  fix clears full doctrine+gate+merge bar).
- **Terminal integrity gate:** `integrity_ok` = clean AND no un-dispatched failure AND no
  unverified criterion; surfaced on `acceptance.anomaly`/`acceptance.done` with
  `unverified_criteria` + `open_failures`. Conservative/no-overclaim.

All registered in `doctrine_spec.py` (I-2) + CLAUDE.md R-rule table (consistency test green).
Tests: `test_acceptance_criteria_chain.py`, `test_simple_gating.py` (coverage_gap),
`test_acceptance_flow.py` (R17). Doc: `PROPOSAL_ACCEPTANCE_REAL_TEST_MANDATE.md`.

**Honesty boundary (stated to operator):** guarantees zero *detected* escape — every
criterion tested+live-verified, every detected failure dispatched, run can't read clean
while anything open. Residual = a behavior no criterion describes (PO-completeness limit),
driven down by R18 but not literally zero. `[~]` unit-proven; live-proof in flight.

**Live-prove (in flight 2026-06-12):** sprint `run-20260612T125029Z-99666a` re-running the
ecommerce reviews feature from baseline `9e98e86` on harness PID 43637. The review-submit
**401** is the canonical defect the chain must catch+auto-fix (R20). Origin of the gap:
[[arch_acceptance_honesty_gap]]. Substrate: [[arch_target_ecommerce]] (C#/.NET, app_boot
backend-only — acceptance improvises frontend boot for the UI write path).
