---
name: arch-auto-dispatch
description: ABL-0015 auto-dispatch (§I.4) — code batches A–D shipped flag-OFF on architect-prereqs; selector+invoker over unchanged _engineer_flow; only operator-gated Batch E live smoke remains.
metadata:
  type: project
---

ABL-0015 closes the self-correction loop: when acceptance finds a
cross-BL `product_bug` and the operator confirms it, the orchestrator
auto-spawns a follow-up engineer to fix it through the same gated
pipeline every BL clears. Design + grounding: `ABL-0015_AUTO_DISPATCH_DESIGN.md`.

## Core design — selector + invoker, NOT a new executor

The dispatcher filters the [[arch-acceptance-agent]] §I.3 findings ledger
and calls the **unchanged** `_engineer_flow`. Only two things differ from
a normal BL run: the task text (`section_override`) and the worktree name
(`task_id`). All dangerous parts — subprocess, regression gate,
auto-merge, A48 teardown — are the same machinery. This is the central
safety property.

Key code (orchestrator.py): `_select_followup_candidates` (pure selector),
`_build_followup_section` + `_followup_hypothesis` (task text in place of
a BACKLOG entry), `_resolve_engineer_section` (the `section_override`
branch), `_dispatch_followup_engineers` (the hook). Ledger lifecycle in
`findings_ledger.py`: 5 `dispatch_*` fields + `set_dispatch_state`.
Closure net: `closure_check.scan_stale_followup_worktrees`.

## DEVIATION worth remembering

Design said `prompt_override`; shipped as `section_override`. Reading
`build_engineer_prompt_brownfield` (prompts_brownfield.py:273) showed all
doctrine scaffolding (eng_patterns.md path, grounding, R5b citations) is
keyed on bl_id INSIDE that builder — a raw prompt override would drop it
and fail `validate_engineer`. Overriding only `bl_section` keeps every
scaffold, so the synthetic BL passes doctrine on the same terms as any BL.

## Operator-approved v1 policy (§9) + R15

Conservative gate (`verdict == "confirmed"` only), cost cap 1
(`FOLLOWUP_COST_CAP`), no auto re-run, gate-fail → manual review, flag OFF
by default (`run_acceptance_followup`). **R15** (dispatch-at-most-once) is
enforced by the selector's `dispatch_state is None` filter — added to the
CLAUDE.md R-rules table per I-2. Crosses two invariant boundaries:
acceptance becomes a writer; engineer gets non-PO work.

## Hook placement (I-3 safe by construction)

Runs inside `_acceptance_flow` AFTER the finally block (acceptance
worktree + volumes already reaped) and BEFORE `acceptance.done`. The
follow-up worktree is reaped by `_engineer_flow`'s own finally before
`run_brief`'s `closure_check.scan_all` fires. Advisory: a dispatch
exception becomes `acceptance.followup.error`, never aborts the sprint.

## The ONLY open step — Batch E (operator-gated)

Live calibration smoke: operator verdicts the real Journey 03 finding
(`sha256:6e533e84…`, the `PUT /billing/invoices/{id}` state-machine
bypass) `confirmed`, runs one sprint with `run_acceptance_followup=true`
on full-stack-fastapi-template, observes one clean dispatch + 0
`followup_worktree` closure violations. Clean smoke → architect proposes
flipping the flag default. The architect cannot run this alone.

## Test posture

208/208 backend pass. Run scoped: `cd webapp/backend && pytest tests/`.
Bare pytest recurses into gitignored target repos under `repos/` and
errors on `sqlmodel` — invocation artifact, not a real failure.
