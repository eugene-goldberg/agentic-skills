---
name: arch-active-branch
description: followup-dispatch-ui (2026-06-03 handoff). ABL-0021 on-demand "Dispatch fix" UI COMPLETE, built atop cumulative_learning (ABL-0016/0020) + architect-prereqs (ABL-0015). NEXT SESSION GOAL = operator runs a live sprint via the web UI, observes/reacts to findings, reviews/approves immediate fixes.
metadata:
  type: project
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

## ⭐ NEXT SESSION GOAL (operator-stated)
**Run a NEW sprint via the web app UI, observe/react to any findings, and
review/approve immediate engineering fixes (the ABL-0021 "Dispatch fix"
flow).** This is a live operator-driven session — architect supports:
pre-flight (PREFLIGHT.md), launch via the UI, watch the SSE stream, then
exercise the findings triage panel → Confirm → Dispatch fix. To enable
auto-dispatch behavior also consider flag `run_acceptance_followup` /
`inject_lessons`, but the headline is the on-demand Dispatch-fix path which
needs no flag.

## Deferred architect-doable (after the live session)
ABL-0017 Stage 2 efficacy (unblocked): outcome-label deriver → rule-efficacy
index → `retire` proposal kind → calibration. Plus the two flag-flip
calibration smokes (ABL-0016 lessons, ABL-0015 Batch E).

## Active target: full-stack-fastapi-template

Branch `financial-management` carries the 12-BL Billing & Financial Management delivery. Acceptance archive at `webapp/backend/traces_archive/run-20260602T143035Z-c5868e/acceptance/`. Ledger at `_brownfield/features/financial-management/acceptance/findings_log.jsonl` with 1 confirmed-pending finding (Journey 03 product_bug, the cross-BL state-machine bypass) — the dispatch test case for ABL-0015 Batch E once verdicted, and a source of prior lessons for ABL-0016 calibration.
