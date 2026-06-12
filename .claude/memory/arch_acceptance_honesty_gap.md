---
name: arch_acceptance_honesty_gap
description: "2026-06-12 — acceptance honesty gap: a FAILED acceptance journey (review-submit 401) was buried under '8/8 merged, regression green' with 0 findings. Mitigation (PARTIAL) on branch acceptance-anomaly-surfacing: _acceptance_flow now ALWAYS emits acceptance.anomaly + acceptance_clean flag."
metadata: 
  node_type: memory
  type: project
  originSessionId: e384aae0-0eb8-447a-acf0-cda9cbb661c2
---

**The finding (operator-flagged 2026-06-11/12).** The ecommerce **Product Ratings &
Reviews** sprint (`run-20260611T132014Z-03e27a`) reported **8/8 merged_full, regression
GREEN, closure 0** — yet the acceptance agent's **journey 03 (UI review-submit)
actually FAILED with a `401`** ("Could not save your review"). The clean top-line hid a
real failure.

**Why it was buried (3 structural reasons):**
1. **Per-BL gates run only each BL's OWN mock tests** (C# xUnit+Moq mock the repos +
   auth) → an auth/DI/JWT bug is INVISIBLE per-BL; it only 500s/401s at live boot. (This
   is the recurring C# mock-only-tests gap — realistic cross-cutting defects surface at
   acceptance, not per-BL. See [[feedback_no_scope_overclaim]].)
2. **Acceptance is ADVISORY and runs AFTER `sprint_complete`** → it cannot un-merge the
   already-merged BLs; a failed journey doesn't reverse "8/8".
3. **The failed journey produced 0 findings** and `acceptance.done` never surfaced
   journey pass/fail counts → the failure existed only as `journey 03: failed` inside
   report.json, not as a finding or a non-clean verdict.

**The delivered feature itself:** read/display UI is REAL + correct (detail summary
avg+distribution+list; per-product card rating badges; reusable star component). The
ONE real defect = the **UI review-submit 401** (likely the frontend `reviewService` not
attaching the JWT, or the review endpoint requiring auth the UI omits). Reviews can be
READ everywhere but not WRITTEN through the browser. 15 acceptance UI screenshots at
`webapp/backend/traces_archive/run-20260611T132014Z-03e27a/acceptance/screenshots/`.

**Mitigation — PARTIAL (branch `acceptance-anomaly-surfacing` @ ae48124, off a4f6606):**
`_acceptance_flow` now ALWAYS surfaces an anomalous acceptance EXPLICITLY:
- `_summarize_acceptance_journeys(report)` → journey summary + per-journey anomalies
  (failed/unshippable); also raises anomalies for a MISSING report, UNPARSEABLE report,
  and a non-OK validator (= "could not verify → anomalous, not clean").
- emits a dedicated loud **`acceptance.anomaly`** event; `acceptance.done` now carries
  **`acceptance_clean=false` + `anomaly_count` + `anomalies` + `journeys`**.
- VERIFIED: the helper flags this run's journey 03 as `journey_failed`; compiles. Commit
  `ae48124` (I-5 honest aggregation).

**REMAINING (next session):** (1) acceptance SKILLS mandate — agent records each failed
journey as an explicit `findings` entry (so it hits the ledger, not just journey status);
(2) an acceptance-flow test; (3) merge to development + restart harness; (4) fix the
review-submit 401 product bug. See `CONTINUATION_PROMPT.md` §REMAINING.

Related: [[arch_stage3_cross_target]] (same session), [[feedback_honest_verification]],
[[feedback_no_scope_overclaim]]. The Architect's Stage-3 acceptance-regression
adjudication (`PROPOSAL_CREW_JUDGMENT_ABL0002.md` §D) is the longer-term close.
