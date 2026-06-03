---
name: arch-active-branch
description: architect-prereqs (2026-06-02 evening handoff). ABL-0015 auto-dispatch code batches A–D shipped flag-OFF on top of the 12-BL Financial_Management delivery. Only operator-gated Batch E live smoke remains.
metadata:
  type: project
---

## State at 2026-06-02 evening

- **Branch:** `architect-prereqs` synced with origin
- **Latest work:** ABL-0015 auto-dispatch (§I.4) — see [[arch-auto-dispatch]]
- **ABL-0015 commits:**
  - `b45919d` D — closure_check follow-up worktree coverage
  - `df0e4ff` C — dispatch block (selector + section_override + R15)
  - `29f5ac6` B — flag + retrieval_kwargs_builder plumbing
  - `912f21e` A — dispatch_* ledger fields + set_dispatch_state
  - `d7b1088` design doc (operator-approved)
  - (+ governance-docs update commit)
- **Prior session (still relevant):** `8c9afd9` §I.3 close, `02ebd7b`
  A48 four-fix leak prevention, `e9e7847…dab73cb` §I.3 Batches A–E.

## Test posture: 208/208 backend pass (scoped `cd webapp/backend && pytest tests/`)

## Active target: full-stack-fastapi-template

Branch `financial-management` carries the 12-BL Billing & Financial Management delivery. Acceptance archive at `webapp/backend/traces_archive/run-20260602T143035Z-c5868e/acceptance/`. Ledger at `_brownfield/features/financial-management/acceptance/findings_log.jsonl` with 1 pending finding (Journey 03 product_bug, the cross-BL state-machine bypass) — this is the **Batch E** dispatch test case once the operator verdicts it `confirmed`.

## Next priorities (per CONTINUATION_PROMPT.md)

1. **§I.4 Batch E** — operator-gated live calibration smoke (verdict Journey 03 → run sprint with `run_acceptance_followup=true` → observe one clean dispatch). The only open ABL-0015 step.
2. §I.2 acceptance trace observability (retrieval.jsonl, phase_events.jsonl, tool_use)
3. §I.5 Django multi-target smoke
