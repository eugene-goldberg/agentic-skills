# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-06-12 (EOD). Supersedes all prior hand-offs. Every fact below
> was verified against the live repo/processes at write time. **Context ran low at the
> end of this session — a few items are deliberately left as clean, well-scoped
> remaining steps (see §REMAINING).**

---PROMPT START---

You are the **architect** of the agentic-skills project. Read `CLAUDE.md` and
`THESIS.md` first. Mission: a **fully autonomous AI crew** that adds complex features
to real brownfield repos with no human in the loop — grounded, self-correcting, honest,
cumulative. **The thing being built is the crew.** Operating doctrine is unchanged
(quality-over-speed, no-abort, improve-the-crew-not-accommodate, 95%-rigor-before-act,
no-scope-overclaim `[x]` vs `[~]`). Honor the memory files.

## What happened this session (the arc)

1. **Stage 3 cross-target cumulative learning (ABL-0018) — SHIPPED then made DORMANT.**
   Built the global "community" lessons store (recurrence graduation ≥2 targets, real-
   bge-m3 floor 0.62, + curated seed) + merged `search_lessons` pull + `inject_global_lessons`
   push. Read-path push+pull was LIVE-PROVEN on ecommerce (first cross-target transfer:
   a beaverhabits lesson advised the ecommerce PO). **Then, per operator directive, made
   DORMANT by default** — a master switch `global_lessons.enabled()` (`STAGE3_CROSS_TARGET=1`,
   default unset) gates ALL three paths (push/pull/graduation). Default = fully dormant;
   the on-disk store + curated seed stay intact, just unconsumed. Docs: `ABL-0018_*`.
   Memory: [[arch_stage3_cross_target]]. (commit `caea812`, on dev/main.)

2. **The Architect agent (ABL-0002) — NEW crew role; SKILLS on dev/main, WIRING on a branch.**
   Operator direction: fill the crew's "engineering-judgment gap" (the evaluation's
   "biggest autonomy gap"; the Horizon wall) with a NEW **Architect** role — the Janitor
   STAYS in its env/merge lane. The Architect REVIEWS + DECIDES; never writes feature code
   or repairs the harness. Three modes: `plan_review` (PO breakdown), `impl_review`
   (engineer diff), `adjudicate` (rescue a stuck BL at code-gate exhaustion). SKILLS
   grounded in 3 reference repos (codenamev/ai-software-architect, SpillwaveSolutions/
   architect-agent, addyosmani/agent-skills). Confirmed delivery model **(A)**: the
   Architect returns the fix as a **directive**; the engineer applies it in one bounded
   re-run through the gate. SKILLS + role-registry on **dev/main (`a4f6606`)**; the
   **orchestrator wiring (Stage 0 + Stage 1) is on branch `architect-wiring` (`8fdbb04`),
   UNMERGED, 468 backend tests green, `run_architect` default OFF.** Stage 0 = sprint-
   summary truthfulness (escalated/deferred roll-up). Stage 1 = `adjudicate`
   (retry_reframed/defer/escalate) at the engineer escalation seam. Doc:
   `PROPOSAL_CREW_JUDGMENT_ABL0002.md` (§D wiring map, staged: 0/1 done, 2 backlog-mutation,
   3 acceptance-regression). Memory: [[arch_stage3_cross_target]] sibling — add an
   architect memory next session.

3. **Reviews feature sprint on ecommerce (C#/.NET) — delivered, 8/8, BUT a real UI bug +
   an acceptance honesty gap.** Ran ~12h on `run-20260611T132014Z-03e27a`: **8/8
   merged_full** (scored 92–95), regression_checkpoint GREEN, closure 0 violations. The
   acceptance agent **improvised a frontend boot + Playwright** and captured **15 UI
   screenshots** (`webapp/backend/traces_archive/run-20260611T132014Z-03e27a/acceptance/screenshots/`).
   - **The read/display UI is correct and real** (detail summary avg+distribution+list;
     per-product card rating badges; reusable star component readonly + interactive).
   - **REAL DEFECT — the UI review-submit fails with `401`.** Journey 03 shows "Could not
     save your review." The write form renders + star-picker works + draft fills, but the
     POST is rejected. Likely cause (unconfirmed): the frontend `reviewService` doesn't
     attach the JWT (`setupAuthHeader`), or the review endpoint requires auth the UI
     doesn't send. The displayed reviews were seeded by the acceptance agent via the API
     (with a token). This is the exact class of bug C# **mock-only** per-BL tests can't
     catch (mocks fake auth) — it only surfaces at live boot.

4. **THE ACCEPTANCE HONESTY GAP (operator-flagged) + its mitigation (PARTIAL).** The
   sprint reported "8/8 merged, regression green, clean" **while acceptance journey 03
   actually FAILED** (the 401). Why it was buried: (a) per-BL gates run only each BL's own
   MOCK tests → auth bug invisible; (b) acceptance is ADVISORY + runs AFTER
   `sprint_complete` → can't un-merge; (c) the failed journey produced **0 findings** and
   `acceptance.done` never surfaced journey pass/fail counts. **Mitigation shipped
   (PARTIAL)** on branch **`acceptance-anomaly-surfacing` (`ae48124`)**: `_acceptance_flow`
   now ALWAYS surfaces an anomalous acceptance EXPLICITLY — `_summarize_acceptance_journeys`
   extracts per-journey anomalies (+ missing/unparseable report + non-OK validator), emits
   a loud **`acceptance.anomaly`** event, and `acceptance.done` carries
   **`acceptance_clean=false` + `anomaly_count` + `anomalies` + journey summary**. VERIFIED
   the helper flags this run's journey 03; compiles. **Not yet:** the SKILLS addition +
   tests + merge (see §REMAINING).

## Branch state (verify with `git`)
- **`development` ≡ `main` @ `a4f6606`** — Stage 3 (dormant) + Architect SKILLS/registry
  (role registered but INERT — no wiring on this branch). **Push status: VERIFY** (last
  confirmed push was `caea812`; `a4f6606` may be local-only — `git push` if so).
- **`architect-wiring` @ `8fdbb04`** (off `a4f6606`) — Architect Stage 0+1 orchestrator
  wiring (`b8abe34`) + the cart-discount hard brief/launcher (`8fdbb04`). UNMERGED. 468
  tests green. `run_architect` default OFF.
- **`acceptance-anomaly-surfacing` @ `ae48124`** (off `a4f6606`) — the acceptance anomaly
  backstop (PARTIAL). UNMERGED. **← current branch.**

## Running services (re-verify: `lsof -nP -iTCP:<port>`)
- **Harness** uvicorn `127.0.0.1:8000` PID **17754** — running OLD code (pre-architect-
  wiring, pre-acceptance-fix). No live sprint. Restart only when you want new harness code
  live.
- **Milvus** :19530 (hardened `ops/milvus/`), **Ollama** bge-m3, **ecommerce-pg** :5433 — up.
- A **Vite frontend on :5173** (ecommerce integration code) may still be running. No `:5096`
  backend (acceptance's ephemeral backend was torn down).
- ecommerce target on branch `integration @ 92a3b47` (the merged reviews feature). Baseline
  to reset for a fresh sprint: `git -C <target> checkout integration && git reset --hard 9e98e86`.

## REMAINING mitigation steps (prioritized)
1. **Finish the acceptance-anomaly fix** (branch `acceptance-anomaly-surfacing`): (a) add to
   the acceptance SKILLS (`skills/brownfield/brownfield-acceptance-agent/SKILLS.md`) a
   mandate that the agent records EACH failed/unshippable journey as an explicit `findings`
   entry (classification + summary) in report.json — so it lands in the ledger, not just as
   a journey status; (b) add an acceptance-flow test asserting a report with a failed journey
   yields `acceptance.anomaly` + `acceptance_clean=false`; (c) run the backend suite; (d)
   merge to `development` + restart the harness.
2. **Fix the review-submit 401** (the real product bug). Diagnose: does the frontend
   `reviewService` attach the JWT? does the review controller require auth? It's a small
   frontend/auth fix — or dispatch a follow-up engineer on it once acceptance findings wire
   it up (which #1 enables).
3. **Architect Stage-1 live-proof** (operator DECLINED running it this session; brief +
   launcher are ready on `architect-wiring`): when wanted, merge `architect-wiring` →
   `development`, restart harness, reset ecommerce baseline, launch
   `scripts/launch_ecommerce_cart_discount.py` (`run_architect=true`). The penny-rounding
   foundation BL reliably fails the engineer's own mock test (proportional + whole-cent +
   exact-sum is solvable via largest-remainder; naive rounding fails the exact-sum) →
   Architect `retry_reframed` (the full rescue loop). Probabilistic (crew may solve it).
4. **Merge decisions:** `architect-wiring` and `acceptance-anomaly-surfacing` are both
   unmerged off `a4f6606`. Decide order; both are additive + flag-gated/observability-only.

## Where to start
1. Read `CLAUDE.md`, `THESIS.md`, then this file + memory `arch_active_branch`,
   `arch_stage3_cross_target`, the new `arch_acceptance_honesty_gap`.
2. `git branch -v`; confirm the three branches above; push `a4f6606` if origin is behind.
3. Pick a REMAINING item. #1 (finish acceptance anomaly fix) is the smallest + closes the
   operator-flagged honesty gap cleanly. #2 (the 401) is the real delivered-feature bug.

---PROMPT END---
