# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-06-05 (evening). Supersedes the morning hand-off.

---PROMPT START---

You are the architect of the agentic-skills project. Read `CLAUDE.md` first —
especially "Operating principle: quality over speed" (the **95% verified/tested
floor**, falsify-before-affirm, narrative-momentum). Only agentic-skills is
committed/pushed; brownfield targets and their `_brownfield/` are never
committed here.

## ⭐ FIRST ACTIONS (do these before anything else)
1. **`git push`** — `ebcf4eb` (the A52 fix) is committed on `followup-dispatch-ui`
   but **NOT pushed**. Everything else is pushed.
2. **Restart uvicorn** only if you intend to run anything — the live process
   (PID ~97469) is already on `ebcf4eb`, so a restart is NOT needed unless you
   change backend code.
3. Skim this whole prompt + `DESIGN_SHORTCOMINGS.md` A52/A39/A45/A49.

## What this session accomplished (all pushed except ebcf4eb)
This session took the harness from "wedges on the first hard thing" to "fails
honestly and self-corrects," and proved it on two live features.

- **3 deferred harness fixes shipped + validated live** (`4773e67`, pushed):
  - **A39** — gate now expands the opaque `tests/playwright::e2e_suite` into the
    real per-test node-ids + names them in `reason` (`_extract_playwright_failures`).
  - **A49** — annotate-only: `detect_transient_markers` (socket hang up/ECONNRESET/…)
    surfaces gate non-determinism without flipping a verdict; explicit
    `--retries=2` made self-contained in both gate templates. *(Verdict-flip
    reclassification is deferred for operator sign-off.)*
  - **A45 wedge-proof** — `run_brief` outer `try` had only a `finally` (can't
    yield during aclose, PEP 525) → any unhandled raise escaped with no terminal
    event. Added (A) engineer-flow wrap → `engineer_unmerged`, (B) outer
    `except` backstop → terminal `aborted`. No more 0-procs wedge.
- **Search & Discovery feature COMPLETED** — re-ran BL-0006 → `merged_full`,
  **6/6 BLs**. Then ran the acceptance pass → it found a real cross-BL
  `product_bug` (default smart views returned nothing: empty-query → empty
  tsquery → 0 rows). Confirmed it (verified vs source), dispatched via ABL-0021
  → follow-up engineer fixed it (**browse mode**, `4ac7e27`) + characterization
  tests → green gate → merged → A50 synced the ledger. **Full
  deliver→diagnose→confirm→dispatch→fix→merge loop validated end-to-end on a
  real bug.**
- **ABL-0015 Calibration Campaign plan** drafted (`79bc978`, pushed) —
  `ABL-0015_CALIBRATION_CAMPAIGN.md`, governance map entry 24. The phased,
  evidence-gated path to flip `inject_acceptance_priors` then
  `run_acceptance_followup` ON (close the triage→dispatch loop unattended).
  Trust signal = per-classification precision prior; not started (N≈2, floor 10).
- **Acceptance SKILLS v0.2 — verified root-cause investigator** (`b0c9b19`,
  pushed): the acceptance agent must now ship a *source-grounded, falsified*
  root-cause dossier (file:line + alternatives_falsified), never a one-sentence
  hypothesis, so the harness can route the right fixer. Made **binding** by two
  companions: (1) `acceptance_validator.py` rejects a code/test/data finding
  missing its dossier → R10.1 retry; (2) `findings_ledger.Finding` gained
  `root_cause/source_refs/alternatives_falsified/fix_locus/confidence`.
  Shakedown on the completed search feature → clean (`validator_ok`, 0 findings).
- **A52 found + fixed live** (`ebcf4eb`, **UNPUSHED**) — see below.

## ⭐ WHERE WE LANDED — the Horizon run (your decision point)
The operator submitted a real brief: **Team Calendar & Scheduling ("Horizon")**.
I adapted it to the target's actual domain (User/Item/SavedSearch — there is **no
Workspace/Project/Task** in `full-stack-fastapi-template`; the adapted brief is
`/tmp/bl6rerun/horizon_brief.md`, scope grounded on CalendarEvent + Item.due_date
+ EventAttendee/CalendarShare/UserAvailability). PO decomposed it into **8
well-structured BLs** (`_brownfield/features/team-calendar-horizon/BACKLOG.md`,
preserved on disk + committed at `e74ac82`).

- **First run** hit **A52**: BL-0001's engineer was pre-grounding (Tier-1.5)
  killed, committed nothing, and was falsely marked `no_op` ("work already
  satisfied") — silently skipping the foundation. Verified absent. Stopped via
  End-Sprint.
- **A52 fix** (`ebcf4eb`): `validate_engineer`'s R11 no-op now requires the
  eng_patterns.md artifact to be **committed at HEAD** (`_is_committed_at_head`
  → `git cat-file -e HEAD:<rel>`), not merely present in the worktree. A killed
  engineer now routes to retry → `engineer_unmerged`, never a false `no_op`.
  Test `test_engineer_noop_pregrounding_kill.py` (3 cases). Suite **297 passed**.
- **Re-run** → BL-0001 built cleanly (A52 avoided), but its CalendarEvent
  foundation **broke login**: `auth.setup.ts` `page.waitForURL` 90s timeout
  after Log In → cascaded ALL auth-gated specs (admin/user-settings/search) +
  a backend `ObjectDeletedError(CalendarEvent)`. Gate `regressed` 3× (A39 named
  the tests every time), engineer chased the **symptom specs** without
  root-causing the auth break, R10.2 exhausted → `awaiting_review` →
  `engineer_unmerged` → **clean `aborted`**. Nothing broken merged; broken work
  isolated on `agent/fd5263480b39` (RED — DO NOT merge).

**The harness behaved perfectly** (A39 names ✓, A52 no false-no_op ✓, wedge-proof
clean terminal ✓ — vs the 8h wedge this session started with). **The crew hit a
real capability wall**: it couldn't root-cause/repair its own auth regression
within the gate-retry budget — the same shallow-vs-deep diagnosis gap the v0.2
acceptance investigator addresses, here in the *engineer's* gate-fix loop.

### ⭐ THE DECISION FOR NEXT SESSION (operator deferred it)
The architect's recommended next step (#1, operator hasn't chosen yet):
**diagnose WHY BL-0001 broke login** — read `agent/fd5263480b39`'s diff (likely
the regenerated `client/*`, or the new model's relationship/migration, or the
router registration). Determine if it's a small fixable engineer mistake or a
hard integration. Then: hand-fix BL-0001 + `skip_po=True start_bl=BL-0002` to
resume, OR re-run, OR accept it as the capability finding.
Bigger idea worth weighing: should the engineer's `build_gate_fix_prompt` carry
a v0.2-style "root-cause before you patch" directive so it stops chasing symptom
specs? (proposal, not built).

## State at hand-off (all clean)
- **agentic-skills:** `followup-dispatch-ui`; pushed @ `b0c9b19`; **`ebcf4eb`
  (A52) UNPUSHED** → push first.
- **Target:** `full-stack-fastapi-template` @ `agentic-skills-work-search_and_discovery`
  `e74ac82` — Search 6/6 + browse-mode fix merged; **calendar NOT merged**.
  Broken BL-0001 on `agent/fd5263480b39` (RED).
- **Horizon backlog** (8 BLs) preserved at
  `_brownfield/features/team-calendar-horizon/`.
- **Clean:** Docker = Milvus only, worktrees = 1, no active run, lock clear.
  uvicorn live on `ebcf4eb` (PID ~97469). Disk ~96 GB free.
- **Tests:** `cd webapp/backend && .venv/bin/python -m pytest tests/` → **297
  passed**, 1 deselect needed: `test_findings_ledger.py::test_concurrent_append_no_torn_lines`
  is a **pre-existing parallel-execution flake** (passes in isolation; not ours).

## Honest project read (unchanged, reinforced)
~40–45% of the thesis, the right 40%. Worker-loop ships straightforward BLs
(Search 6/6) but walls on a foundation BL that breaks a shared subsystem and
can't self-repair in budget. **The win this session is the control plane**: it
now fails *honestly and visibly* (named failures, clean halt, quarantined
branch) instead of wedging. "Submit a brief and walk away to 100%" is still NOT
real: triage→dispatch is operator-gated (auto-confirm unbuilt), and the crew's
self-repair depth is the next capability frontier.

## Other deferred (carried)
- ABL-0015 calibration Phase-0 groundwork (deferral-reason hygiene + precision
  report); flag flips need N≥10 @ ≥0.90.
- A49 verdict-flip (regressed→inconclusive on transient) — operator sign-off.
- A39 sub-mode 39a (build-failure conflation) still open under the primary A39.
- Branch consolidation (architect-prereqs→cumulative_learning→followup-dispatch-ui)
  to a trunk — still deferred.

## Reading order
1. `CLAUDE.md` (architect role + 95% floor)
2. This ⭐ section + `DESIGN_SHORTCOMINGS.md` A52 / A39 / A45 / A49 / A50 / A51
3. `ABL-0015_CALIBRATION_CAMPAIGN.md`, `DOCTRINE.md`, `CONTROL_FLOW.md`
4. Memories: `arch_active_branch`, `arch_harness_hardening`, `arch_horizon_run`,
   `arch_acceptance_v02`

## Don'ts (carried)
1. Don't commit brownfield targets / `_brownfield/`.
2. Don't `docker … prune -af` without naming what to keep (Milvus!). For
   dangling only use `docker image prune -f`; full unused images `-a` ONLY
   when no sprint is running.
3. Don't merge `agent/fd5263480b39` — its gate is RED (broken auth).
4. Ctrl+C (SIGTERM) uvicorn, not kill -9. To kill a LIVE run cleanly: drop the
   SSE consumer (TaskStop) THEN `POST /end-sprint {purge_images:true}`.
5. Don't announce a root cause without reading the actual source/branch (95%).

---PROMPT END---
