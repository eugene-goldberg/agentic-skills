---
name: arch-live-run-invoice-soft-delete
description: First live end-to-end exercise of the ABL-0021 on-demand Dispatch-fix loop (2026-06-03/04). Full sprint + acceptance + dispatch on full-stack-fastapi-template. Surfaced A49 gate non-determinism. Loop validated.
metadata: 
  node_type: memory
  type: project
  originSessionId: 7979a248-b0b3-495b-9685-dc8fd4f1d643
---

First fully operator-driven live run exercising the ABL-0021 on-demand
"Dispatch fix" loop end-to-end. Target: `full-stack-fastapi-template`.
Feature: soft-delete / undo for billing invoices.

## Setup (the right call)

Operator chose the RUNBOOK clean fork, BUT master has **zero** billing code
(billing lives only on `financial-management`). A clean fork off master would
have stripped the very code being extended. Correct move = **hybrid**: fork the
new agent branch `agentic-skills-work-invoice_soft_delete` off
`financial-management` (inherit invoice code) + run RUNBOOK *hygiene* steps
(strip `_brownfield/`, purge graphify cache, drop the exact Milvus collection
`hybrid_code_chunks_514e5679` via the bridge `has_index` op, archive traces).
Lesson: **clean-fork-off-main-ref only applies to an *independent* feature; a
feature that extends a prior delivery forks off the feature-bearing branch.**

## The run

- `run-20260603T171421Z-30c5d9`, slug `invoice-soft-delete`, 6 BLs, all
  `merged_full`, zero operator interventions. PO decomposition was high-quality
  and grounded (pinpointed `invoices.py:246` hard-delete, "exactly 5 read
  sites", reused `record_audit`, mirrored `INVOICE_NET_TERMS_DAYS=30`).
- Acceptance exposed **1 genuine cross-BL `product_bug`** (journey_02): restore
  shipped backend-side (BL-0004/0005 PASS in api journeys) but **unreachable
  from the UI** — no trash/deleted view. Exactly the cross-BL seam per-BL gates
  can't catch (the [[arch-acceptance-agent]] value prop, live).

## The Dispatch-fix loop (validated)

verdict=confirmed (`POST /verdict`) → `POST /dispatch-followup` →
`acceptance.followup.start` → follow-up engineer in its own worktree (the
unchanged ABL-0015 engine, see [[arch-auto-dispatch]] / [[arch-ondemand-dispatch-ui]])
→ same doctrine + regression gate → **`outcome=not_merged`** (gate non-green) →
finding `dispatch_state=not_merged`, R15 spent. The refuse-to-merge was the
**correct conservative** behavior, not a bug.

## What it surfaced: A49 gate non-determinism

The dispatched fix was actually **correct**. Architect re-ran the full gate on
the same branch (`bc96a6c`) standalone → `GATE EXIT=0` (fe-lint PASS, backend
`314 passed/0 failed`, playwright `68 passed/2 flaky`). The dispatch gate's two
attempts had *disagreeing* spurious failures: a first-build frontend flake
(`tests/frontend::lint_typecheck_build`) and a transient `socket hang up` in an
**unrelated** reset-password E2E. Filed **A49** (DESIGN_SHORTCOMINGS) — gate
verdict is not a pure function of the diff; distinct from A39 (true-failure
signal quality) and A45 (silence-while-busy kill). Fix directions: honor
playwright `--retries` (flaky-final-pass = PASS), classify network transients as
retryable-infra, single rebuild-retry on first-build frontend flake.

## Resolution

Fix verified green + merged via operator override: `POST /merge-branch
{skip_gate:true}` → ff `merged_sha bc96a6c` into the agent branch; finding
`dispatch_state` set to `merged`. Soft-delete/undo feature complete end-to-end.

**Why:** proves the ABL-0021 loop works live AND that the gate's flakiness can
block correct fixes — a foundational-trust issue for both the per-BL loop and
on-demand dispatch.

**How to apply:** when an on-demand (or auto) dispatch returns `not_merged`,
don't assume the fix is wrong — re-run the full gate standalone on the
follow-up branch first; a green standalone run means A49 flakiness, and the fix
can be merged via `skip_gate`. Prioritize A49 (playwright retry honoring) to
stop false-reds blocking correct auto-merges.
