---
name: arch-active-branch
description: cumulative_learning (2026-06-03 handoff). ABL-0016 lessons-as-context (A–C, flag-OFF) + ABL-0020 doctrine-spec registry (COMPLETE, fulfills I-2). ABL-0017 Stage-2 efficacy unblocked & Batch-0 done. Built on architect-prereqs' ABL-0015 (flag-OFF). Two operator smokes open.
metadata:
  type: project
---

## State at 2026-06-03

- **Current branch:** `cumulative_learning` synced with origin, tip `db7d8d7`
- **ABL-0020 doctrine-spec registry — COMPLETE** (keystone, fulfills I-2):
  `624886f` A (registry+meta-test), `016ef5c` B (per-run manifest),
  `db7d8d7` C (consistency guard + I-2 marked fulfilled). See
  [[arch-doctrine-spec-registry]].
- **ABL-0016 lessons-as-context (Stage 1, flag-OFF):** `512a1c5` C,
  `294f725` B, `eb20d6f` A (+ plan/roadmap commits). See
  [[arch-cumulative-learning]].
- **ABL-0017 Stage 2:** Batch 0 done (`fab3a0e`), unblocked by ABL-0020.
- **`architect-prereqs` (separate branch):** ABL-0015 auto-dispatch A–D
  flag-OFF — see [[arch-auto-dispatch]].

## Test posture: 248/248 backend pass (scoped `cd webapp/backend && pytest tests/`)

## Two open operator-gated calibration smokes (architect cannot run)

1. ABL-0016 lessons: sprint with `inject_lessons=true` on a target with
   prior confirmed findings → block renders + provenance written.
2. ABL-0015 Batch E: verdict Journey 03 confirmed → sprint with
   `run_acceptance_followup=true` → one clean dispatch.

## Next architect-doable: ABL-0017 Stage 2 efficacy (now unblocked)
Both input halves persist per run (`bl_outcomes` + `doctrine_manifest`).
Proceed to design/batches per CUMULATIVE_LEARNING_IMPLEMENTATION_PLAN.md §4:
outcome-label deriver → rule-efficacy index → `retire` proposal kind →
calibration. Medium-fidelity (A13 per-rule triggers deferred).

## Active target: full-stack-fastapi-template

Branch `financial-management` carries the 12-BL Billing & Financial Management delivery. Acceptance archive at `webapp/backend/traces_archive/run-20260602T143035Z-c5868e/acceptance/`. Ledger at `_brownfield/features/financial-management/acceptance/findings_log.jsonl` with 1 confirmed-pending finding (Journey 03 product_bug, the cross-BL state-machine bypass) — the dispatch test case for ABL-0015 Batch E once verdicted, and a source of prior lessons for ABL-0016 calibration.
