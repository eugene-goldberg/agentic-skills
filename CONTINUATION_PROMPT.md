# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-06-02 (evening). This session designed and
> implemented **ABL-0015 auto-dispatch** (§I.4) — code batches A–D —
> on top of the prior Financial_Management 12-BL delivery. All work is
> committed and pushed to `architect-prereqs`.
>
> **Only Batch E remains, and it is operator-gated** — a live
> calibration smoke that dispatches a real follow-up engineer on the
> confirmed Journey 03 `product_bug`. The architect cannot run it.

---PROMPT START---

You are picking up the agentic-skills project. **You are the architect.**
Read `CLAUDE.md` first — especially **"Operating principle: quality over
speed"** (Rules 1–6, the **95% verified/tested certainty floor**, and
Rule 3 on **narrative momentum**).

## ⚠️ Priority 0 — Verify branch state (30 sec)

```bash
cd /Users/eugenegoldberg/dev/ai-projects/agentic-skills
git status -s                  # MUST be clean
git log --oneline @{u}..HEAD   # MUST be empty (synced with origin)
git log --oneline -1           # expect the governance-docs commit on architect-prereqs
```

## 1. Identity

**agentic-skills** — autonomous synthetic AI crew for brownfield feature
delivery. Operator: Eugene Goldberg. Active branch: `architect-prereqs`.

## 2. State at hand-off — ABL-0015 auto-dispatch shipped (flag-OFF)

This session built the feedback-loop-closing feature: when acceptance
finds a cross-BL `product_bug` and the operator confirms it, the
orchestrator auto-spawns a follow-up engineer to fix it through the same
gated pipeline every BL clears.

**Code batches A–D — all committed on `architect-prereqs`:**

| Commit | What |
|---|---|
| `d7b1088` | design doc (`ABL-0015_AUTO_DISPATCH_DESIGN.md`, operator-approved) |
| `912f21e` | A — 5 `dispatch_*` ledger fields + `set_dispatch_state` |
| `29f5ac6` | B — `run_acceptance_followup` flag + `retrieval_kwargs_builder` thread-through |
| `df0e4ff` | C — selector + section builder + `section_override` + dispatch hook + R15 |
| `b45919d` | D — `scan_stale_followup_worktrees` closure coverage |
| (this session's last) | governance-docs update (BACKLOG, ABL-0014 §I.4, CLAUDE.md R15, this file) |

**Design principle:** selector + invoker, **not** a new executor. The
dispatcher filters the I.3 findings ledger and calls the *unchanged*
`_engineer_flow` (only `section_override` + `task_id` differ). All
dangerous parts — subprocess, regression gate, auto-merge, A48 worktree
teardown — are the same machinery that guards every BL.

**Operator-approved v1 policy** (`ABL-0015_AUTO_DISPATCH_DESIGN.md` §9):
- Conservative verdict gate: dispatch only on `verdict == "confirmed"`.
- Cost cap 1 (`FOLLOWUP_COST_CAP`).
- No auto re-run of acceptance after the fix.
- Gate-fail → `not_merged`, manual review, no extra retry.
- Flag **OFF by default** (`run_acceptance_followup=False`).

**New doctrine rule R15** (dispatch-at-most-once) — enforced by the
selector's `dispatch_state is None` filter. Added to the CLAUDE.md
R-rules table per I-2.

### Test posture

```
208/208 backend pass (was 176 at start of session, +32)
  +8   test_findings_ledger        (dispatch lifecycle)
  +5   test_followup_flag_wiring    (Batch B plumbing)
  +15  test_followup_dispatch       (selector / builders / dispatch loop)
  +4   test_closure_check_…stack    (followup_worktree scan)
```

**IMPORTANT — how to run the suite:** scope it to `tests/` from
`webapp/backend/`:
```bash
cd webapp/backend && python3 -m pytest tests/ -q -p no:cacheprovider
```
Bare `pytest` from `backend/` recurses into the gitignored brownfield
**target** repos under `repos/` and errors on their `sqlmodel` dep —
a pre-existing invocation artifact, not a real failure.

## 3. The ONLY open step — Batch E (operator-gated live calibration smoke)

This is the step the architect cannot do alone. To legitimize flipping
the flag ON (same default-flip discipline as §I.1 API-acceptance):

1. **Operator-verdict the real finding `confirmed`.** Journey 03's
   `product_bug` (`sha256:6e533e84…`) lives in
   `…/_brownfield/features/financial-management/acceptance/findings_log.jsonl`
   (on the `full-stack-fastapi-template` target). Set it via the AppV2
   triage panel or `POST /verdict`. Until then the selector finds zero
   candidates by design.
2. **Run one sprint with `run_acceptance_followup=true`** (and
   `run_acceptance=true`) on that target.
3. **Observe exactly one follow-up dispatch** fixing
   `PUT /billing/invoices/{id}` (it writes `status` directly, bypassing
   BL-0005's guarded transition state machine — see design §3a). Watch
   for `acceptance.followup.{start,done}` in the stream and
   `BL-ACCEPT-<run_id>-0` sub-events.
4. **Verify clean closure:** `closure_check` reports 0
   `followup_worktree` violations; ledger finding transitions
   `dispatch_state: confirmed-verdict → dispatched → merged`.

If the smoke is clean, the architect can propose flipping the flag
default (operator approves).

## 4. The bug the smoke will fix (Journey 03, the proof point)

`PUT /billing/invoices/{id}` (`update_invoice`) assigns
`InvoiceUpdate.status` straight onto the model, bypassing the guarded
state machine (`POST /{id}/transition`, which correctly rejects illegal
transitions with 409). The follow-up engineer should route status changes
through `app/billing/workflow.py`. This is the exact cross-BL integration
class per-BL QA structurally cannot catch — the canonical evidence that
the acceptance agent + auto-dispatch loop earns its place.

## 5. §I production-readiness roadmap status

| Item | Status |
|---|---|
| **I.1** 3 calibration smokes for API-acceptance | ✅ closed |
| **I.2** observability gaps | not started |
| **I.3** ledger + triage UI + extractor | ✅ closed |
| **I.4** ABL-0015 auto-dispatch | **code A–D shipped, flag-OFF; Batch E live smoke is the open step** |
| **I.5** Django smoke (multi-target) | not started |

After Batch E, the highest-leverage remaining moves are **I.2**
(observability) and **I.5** (Django multi-target validation).

## 6. Other open ledger items

| ID | Status |
|---|---|
| **A39** | open — regression_gate parser conflates baseline-broken with engineer-regressed |
| **A45** | open — B5 idle-timeout false-positive |
| **A47** | open — ScheduleWakeup/Glob bypass `--allowedTools` |
| **A48** | closeable pending operator review (4 fixes shipped 2026-06-02) |
| doctrine-meta proposal | open — characterization-test ownership contradiction (engineer vs QA SKILLS vs rubric); R-CHAR proposed; awaiting operator decision |

## 7. Mandatory reading order for next session

1. `CLAUDE.md` — architect role + "Operating principle"
2. `THESIS.md`, `ARCHITECTURE_INVARIANTS.md`
3. `ABL-0015_AUTO_DISPATCH_DESIGN.md` — the feature you'd be calibrating
4. `ABL-0014_ACCEPTANCE_AGENT_IMPLEMENTATION.md` §I — production roadmap
5. This file's §3 — the one open step

## 8. Don'ts (carried lessons)

1. Don't run `docker container prune -f && docker image prune -af`
   without naming what to keep — it wiped Milvus + a ledger file last time.
2. Don't auto-skip pre-flight (`PREFLIGHT.md`) after a clean cleanup.
3. Don't lose narrative-momentum awareness — read post_tail + gate fields
   carefully every time, even when the pattern looks like prior runs.
4. Don't force-kill uvicorn during live sprints — use Ctrl+C (SIGTERM)
   so the shutdown handler reaps Docker stacks (worktrees only reap from
   `finally`).

---PROMPT END---
