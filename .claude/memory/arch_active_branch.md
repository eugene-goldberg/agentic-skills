---
name: arch-active-branch
description: "followup-dispatch-ui (2026-06-03 handoff). ABL-0021 on-demand \"Dispatch fix\" UI COMPLETE, built atop cumulative_learning (ABL-0016/0020) + architect-prereqs (ABL-0015). NEXT SESSION GOAL = operator runs a live sprint via the web UI, observes/reacts to findings, reviews/approves immediate fixes."
metadata: 
  node_type: memory
  type: project
  originSessionId: 7979a248-b0b3-495b-9685-dc8fd4f1d643
---

## State at 2026-06-03

- **Current branch:** `followup-dispatch-ui` synced with origin, tip `3db7705`.
  Branched off `cumulative_learning`, so it carries ABL-0016 + ABL-0020 too.
- **ABL-0021 on-demand Dispatch-fix UI — COMPLETE:** `8bfbec7` A (backend
  `POST /dispatch-followup` + `_dispatch_one_followup` refactor), `3db7705`
  B (FindingsTriagePanel button + dispatch_state badge). See
  [[arch-ondemand-dispatch-ui]].
- **ABL-0020 doctrine-spec registry — COMPLETE** (fulfills I-2): see
  [[arch-doctrine-spec-registry]].
- **ABL-0016 lessons-as-context (Stage 1, flag-OFF):** see
  [[arch-cumulative-learning]].
- **ABL-0017 Stage 2 efficacy:** Batch 0 done, unblocked by ABL-0020.
- **ABL-0015 auto-dispatch (architect-prereqs, flag-OFF):** see
  [[arch-auto-dispatch]].

## Test posture: 254/254 backend pass (scoped `cd webapp/backend && pytest tests/`); `vite build` clean

## ⭐ LIVE-RUN GOAL — DONE 2026-06-04
The ABL-0021 Dispatch-fix flow was exercised end-to-end in a real sprint
(invoice soft-delete on full-stack-fastapi-template; see
[[arch-live-run-invoice-soft-delete]]). 6/6 BLs merged, acceptance found a real
cross-BL product_bug, confirm → Dispatch fix → gate → not_merged (correct
conservative behavior on a flaky non-green gate). Fix verified green standalone
and merged via skip_gate. **New top follow-up: A49 gate non-determinism** —
flaky false-red blocked a correct fix; fix playwright-retry honoring + transient
network classification so the gate verdict is a pure function of the diff.

## Deferred architect-doable (after the live session)
ABL-0017 Stage 2 efficacy (unblocked): outcome-label deriver → rule-efficacy
index → `retire` proposal kind → calibration. Plus the two flag-flip
calibration smokes (ABL-0016 lessons, ABL-0015 Batch E).

## Active target: full-stack-fastapi-template

Branch `financial-management` carries the 12-BL Billing & Financial Management delivery. Acceptance archive at `webapp/backend/traces_archive/run-20260602T143035Z-c5868e/acceptance/`. Ledger at `_brownfield/features/financial-management/acceptance/findings_log.jsonl` with 1 confirmed-pending finding (Journey 03 product_bug, the cross-BL state-machine bypass) — the dispatch test case for ABL-0015 Batch E once verdicted, and a source of prior lessons for ABL-0016 calibration.
