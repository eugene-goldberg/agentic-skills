---
name: arch-ondemand-dispatch-ui
description: ABL-0021 operator-facing on-demand "Dispatch fix" — POST /dispatch-followup + FindingsTriagePanel button. Closes the seam between the §I.3 triage UI and the ABL-0015 dispatch engine. Complete on branch followup-dispatch-ui; only live operator click-through remains.
metadata:
  type: project
---

ABL-0021 adds the operator-control surface ABL-0015's dispatch engine was
missing. Before it, auto-dispatch only fired **inline during a sprint** on
**pre-confirmed** findings — so a freshly-landed sprint's findings (pending)
never dispatched, and there was no way to trigger a fix short of running
another sprint. ABL-0021 lets the operator, after a sprint lands, review
exposed findings → confirm → trigger the fix on-demand. Plan:
`ABL-0021_ONDEMAND_DISPATCH_UI.md`.

## What shipped (branch `followup-dispatch-ui`)

- **A backend (`8bfbec7`):** refactored the per-finding dispatch body out of
  `_dispatch_followup_engineers` into shared `_dispatch_one_followup(...)`
  (inline loop + on-demand endpoint both call it — inline behavior
  unchanged, existing tests green). `select_followup_finding(repo_dir,
  feature_slug, finding_id) -> (finding, ledger, reason)` eligibility
  resolver (reason ∈ {None, unknown, not_product_bug, not_confirmed,
  already_dispatched}; R15 here). Endpoint `POST
  /api/projects/{repo}/dispatch-followup {feature_slug, finding_id,
  timeout_seconds}` — pre-validates (404/409) then SSE-streams
  `acceptance.followup.*` + engineer sub-events; mints
  `manual-dispatch-<ts>-<rand>` run_id; retrieval builder via existing
  `_retrieval_kwargs`. +6 endpoint tests, 254/254.
- **B frontend (`3db7705`):** `frontend/src/AppV2.jsx` FindingsTriagePanel —
  `fix: <dispatch_state>` badge per finding; a "🛠 Dispatch fix" button on
  confirmed product_bugs with no dispatch_state → POST /dispatch-followup
  via `streamPost`, live phase line, terminal outcome inline (merged+sha /
  awaiting review / error), refetch. `vite build` clean.

## Design / safety

Selector+invoker, reused unchanged — the follow-up engineer clears the same
doctrine + regression-gate + auto-merge bar as any BL. Operator-gated by
construction: needs an explicit confirmed verdict AND a button press;
confirmed-product_bug-only; R15 dispatch-at-most-once. No new R-rule;
the engineer reaps its own worktree in `_engineer_flow`'s finally (on-demand
dispatch is not sprint-bound, so closure_check doesn't run after — the
finally teardown is the guarantee, same as every engineer worktree).

Builds on [[arch-auto-dispatch]] (ABL-0015 engine) + the §I.3 triage panel
(see [[arch-acceptance-agent]]).

## Open

Live operator click-through is the only remaining verification (no frontend
test infra by design; the backend endpoint is unit-tested). This is the
facility the operator will exercise next session: run a sprint via the web
UI → observe findings → review/approve → Dispatch fix.
