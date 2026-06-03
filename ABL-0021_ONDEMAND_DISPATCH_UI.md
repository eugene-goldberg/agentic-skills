# ABL-0021 — Operator-facing on-demand follow-up dispatch ("Dispatch fix")

> **Status: COMPLETE — Batch A (backend) + Batch B (frontend) shipped.**
> Author: architect. Date: 2026-06-03. Branch: `followup-dispatch-ui`.
> The operator-control surface ABL-0015's dispatch engine was missing.

---

## 1. The gap

§I.3 shipped the **triage panel** (confirm/refute/defer) and ABL-0015
shipped the **dispatch engine** — but they're disconnected for the
operator. ABL-0015 auto-dispatch only fires **inline during a sprint**, and
only on findings **already confirmed before that sprint**. So a freshly-
landed sprint surfaces findings as `pending` → nothing dispatches → the
operator can confirm them but has **no facility to then trigger the fix**
short of running another whole sprint.

This ABL adds the missing step: **sprint lands → operator reviews exposed
findings → approves (confirm) → triggers the fix on-demand.**

## 2. Operator-approved UX (two-step, per-finding)

In the triage panel, per finding: **Confirm** (verdict, as today) → a
**"Dispatch fix"** button appears on confirmed `product_bug` findings →
clicking it dispatches *that* finding on-demand and streams progress.
Verdict (ledger-accuracy) and dispatch (spend compute on a fix) stay
distinct, deliberate acts; the operator can confirm-but-not-fix.

## 3. Design — reuse, don't rebuild

The follow-up engineer clears the **same** doctrine + regression-gate +
auto-merge bar as any BL (ABL-0015's selector+invoker property). On-demand
dispatch reuses that machinery unchanged; it only adds a per-finding entry
point and an HTTP/SSE surface.

### Batch A — backend (SHIPPED)

- **Refactor:** extracted `_dispatch_one_followup(repo_dir, repo_name,
  run_id, feature_slug, finding, idx, retrieval_kwargs_builder, ledger, *,
  timeout)` — the shared per-finding body now used by BOTH the inline
  sprint loop (`_dispatch_followup_engineers`) and the on-demand endpoint.
  R15-stamps `dispatched` before spawn, runs `_engineer_flow`
  (section_override), captures terminal events, stamps `merged`/
  `not_merged`. The inline loop is unchanged in behavior (existing tests
  green).
- **Eligibility resolver:** `select_followup_finding(repo_dir, feature_slug,
  finding_id) -> (finding, ledger, reason)` where reason ∈ {None, unknown,
  not_product_bug, not_confirmed, already_dispatched}. R15 lives here
  (`dispatch_state is None`).
- **Endpoint:** `POST /api/projects/{repo}/dispatch-followup`
  `{feature_slug, finding_id, timeout_seconds}`. Pre-validates eligibility
  (→ 404 unknown / 409 not-eligible / 409 already-dispatched) then SSE-
  streams `acceptance.followup.{start,done}` + engineer sub-events. Mints a
  `manual-dispatch-<ts>-<rand>` run_id; builds the retrieval builder via the
  existing `_retrieval_kwargs`.
- **Tests:** +6 endpoint tests (404/409 paths + eligible-streams with a
  faked engine + bad-slug). Existing inline dispatch tests still green
  (refactor preserved behavior). 254/254 backend pass.

### Batch B — frontend (SHIPPED)

`webapp/frontend/src/AppV2.jsx` FindingsTriagePanel — implemented: each
finding now shows a `fix: <dispatch_state>` badge; confirmed product_bugs
with no dispatch_state show a **"🛠 Dispatch fix"** button that POSTs to
`/dispatch-followup` and streams progress via `streamPost`, then refetches;
terminal outcome (merged + sha / awaiting-review / error) rendered inline.
`vite build` clean (33 modules). PROJECT_STATE.md updated. No frontend test
infra (per CLAUDE.md) — manual smoke is the verification path.

Original spec:
`webapp/frontend/src/AppV2.jsx` FindingsTriagePanel:
- Surface each finding's `dispatch_state` (the ledger already carries
  `dispatch_state`/`dispatch_bl_id`/`dispatch_merged_sha` from ABL-0015
  Batch A): `pending → confirmed → dispatched → merged/not_merged`.
- Add a **"Dispatch fix"** action on confirmed `product_bug` findings with
  `dispatch_state == null`; POST to `/dispatch-followup`, stream progress
  (reuse the existing SSE helper), reflect the terminal outcome + refresh.
- Disable/relabel once dispatched; show the outcome (merged sha / awaiting
  review) inline.
- Update `webapp/PROJECT_STATE.md`.

## 4. Invariant posture / safety

- No new R-rule. R15 (dispatch-at-most-once) is enforced by the eligibility
  resolver + the ledger `dispatch_state`.
- I-1/I-3: the follow-up engineer reaps its own worktree in `_engineer_flow`'s
  `finally` (the primary teardown) — same as inline. On-demand dispatch is
  not sprint-bound, so closure_check doesn't run after it; the `finally`
  teardown is the guarantee (unchanged from how every engineer worktree is
  reaped).
- Operator-gated by construction: dispatch requires an explicit confirmed
  verdict AND an explicit button press.

## 5. Calibrated proposal

**Risk:** Low. Backend reuses the gated ABL-0015 machinery; the endpoint
only dispatches operator-confirmed product_bugs, one at a time, R15-guarded.
Worst case = a confirmed-but-actually-wrong finding spawns an engineer whose
change still must clear the regression gate + auto-merge bar.
**Test:** the +6 endpoint tests; the inline-dispatch tests prove the refactor
is behavior-preserving. **Rollback:** revert; the inline auto-dispatch path
and the triage panel are unaffected.
