---
name: arch_complex_feature_a65_a66
description: "2026-06-09 — first complex 5-BL feature (periodic-habit-goals) ran clean; surfaced+fixed A65 (pattern-profile dirties tree) + A66 (followup path lacked janitor-remerge, live-proof PENDING)"
metadata: 
  node_type: memory
  type: project
  originSessionId: a8424a63-c4d2-4362-94ee-c97df1d36eb3
---

**First deliberately HARD brownfield feature shipped: "Periodic Habit Goals"**
(`run-20260609T133620Z-fb16cc`, beaverhabits). A genuine 5-BL **dependency DAG**
(model → API/progress → streak/UI), two subtle-correctness BLs (Mon–Sun/calendar
period-window math; goal-streak across periods), plus a UI BL → **Playwright**
acceptance. RESULT: **5/5 BLs merged, all gates green, regression checkpoint green
(267 passed, 0 regressions), 0 per-BL escalations.** The crew handled it cleanly.
The layered model worked exactly as designed: green unit tests + a Playwright
acceptance that caught a real UI integration bug (goal badge clipped inside a
truncating `overflow:hidden` box) the units structurally couldn't see, and the
A60 auto-followup engineer FIXED it (gate green). Ran ~8.9h — almost ALL
host-saturation overhead (load avg 13; Docker VM + Microsoft Defender + Spotlight
starving Ollama → intermittent ~13-min retrieval stalls). NOT a crew-speed
problem; the harness rode it out by not idle-killing in-flight tools (vindicated).

**Two general gaps surfaced + fixed (commit `35fc42b`, UNPUSHED):**
- **A65 (FIXED):** the ABL-0019 pattern-profile refresh wrote a TRACKED file
  `_brownfield/_pattern_profile/PATTERN_PROFILE.md` into the target at
  sprint_complete → dirty tree → blocked the followup merge ("main checkout has
  modified tracked files"). `pattern_profile.consolidate` now drops a `.gitignore`
  (`*`) so the artifact is never tracked on a FRESH target (generalizes A58).
  Does NOT retro-untrack already-tracked targets (beaverhabits) → A66 / one-time
  `git rm --cached` covers those.
- **A66 (IMPLEMENTED, UNIT-TESTED, `[~]` LIVE-PROOF PENDING):** the A58/A59
  Janitor+remerge lived ONLY in `run_brief`'s per-BL loop; the acceptance-followup
  runs `_engineer_flow` via `_dispatch_one_followup` OUTSIDE that loop, so it
  bypassed the Janitor and abandoned a correct green-tested fix as `not_merged`.
  Now wired in (same `_engineer_janitor_trigger → _run_janitor →
  _should_remerge_after_janitor → fast_forward_target` chain).
  `tests/test_followup_merge_resolution.py` (+5). Both the architect AND the
  doctrine-meta agent independently filed this gap.

**A64 was LIVE-PROVEN this session too** (2nd sealed sprint `run-…-346c4d`:
`doctrine_efficacy.json` by_rule now carries `regression_checkpoint {clean:1}`).

**LIVE-PROOF for A66 (next session):** restart harness on `35fc42b` (PID 14484 is
stale — A64-era), re-dispatch the pending `periodic-habit-goals` badge finding
(`dispatch_state=not_merged`), confirm `merge_retry_post_janitor(ok=true)` +
`janitor.resolved` → promote A66 to `[x]`. See [[feedback_no_scope_overclaim]],
[[feedback_no_abort_persistence]], [[arch_self_resolution_arc]],
[[arch_stage2_closed_a64]]. dev=main=`35fc42b` (UNPUSHED; origin at `ab04f62`).
