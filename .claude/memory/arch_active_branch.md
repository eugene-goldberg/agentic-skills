---
name: arch-active-branch
description: cumulative_learning (2026-06-03 handoff). ABL-0016 lessons-as-context batches A–C shipped flag-OFF; built on architect-prereqs' ABL-0015 auto-dispatch (A–D, flag-OFF). Two operator-gated calibration smokes open; next architect work is ABL-0017 Stage 2.
metadata:
  type: project
---

## State at 2026-06-03

- **Current branch:** `cumulative_learning` synced with origin — see [[arch-cumulative-learning]]
- **ABL-0016 commits (Stage 1, lessons-as-context):**
  - `512a1c5` C — record_injection provenance (Stage-2 hook)
  - `294f725` B — inject_lessons flag + wire into 4 brownfield prompts
  - `eb20d6f` A — lessons.py reader + renderer
  - `29b9503` whole-feature program plan; `e600044` ABL-0016 plan; `f259439` roadmap
- **`architect-prereqs` (separate branch):** ABL-0015 auto-dispatch A–D
  flag-OFF (`b45919d`/`df0e4ff`/`29f5ac6`/`912f21e`/`d7b1088`) — see
  [[arch-auto-dispatch]]. Built on §I.3 close + A48 fixes.

## Test posture: 233/233 backend pass (scoped `cd webapp/backend && pytest tests/`)

## Two open operator-gated calibration smokes (architect cannot run)

1. ABL-0016 lessons: sprint with `inject_lessons=true` on a target with
   prior confirmed findings → block renders + provenance written.
2. ABL-0015 Batch E: verdict Journey 03 confirmed → sprint with
   `run_acceptance_followup=true` → one clean dispatch.

## Next architect-doable: ABL-0017 Stage 2 (closed-loop doctrine efficacy)
Start with its Batch-0 verification gate (outcome-persistence + active-rule
seams) per CUMULATIVE_LEARNING_IMPLEMENTATION_PLAN.md §4.

## Active target: full-stack-fastapi-template

Branch `financial-management` carries the 12-BL Billing & Financial Management delivery. Acceptance archive at `webapp/backend/traces_archive/run-20260602T143035Z-c5868e/acceptance/`. Ledger at `_brownfield/features/financial-management/acceptance/findings_log.jsonl` with 1 confirmed-pending finding (Journey 03 product_bug, the cross-BL state-machine bypass) — the dispatch test case for ABL-0015 Batch E once verdicted, and a source of prior lessons for ABL-0016 calibration.
