---
name: arch-horizon-run
description: "2026-06-05 — first full autonomous attempt at a fresh NEW feature (Team Calendar 'Horizon') on full-stack-fastapi-template. Surfaced + fixed A52 (false no_op after pre-grounding kill). Re-run aborted CLEANLY at BL-0001 (its CalendarEvent foundation broke login → cascaded auth specs; engineer couldn't self-repair in the gate-retry budget). The canonical 'harness now fails honestly; crew hits a real capability wall' evidence."
metadata:
  node_type: memory
  type: project
  originSessionId: 326d1623-34a0-4f02-8c13-b7359c64685d
---

First time the crew was pointed at a **brand-new feature** (not search/billing
analogs). Brief: Team Calendar & Scheduling ("Horizon"). The architect **adapted
it to the target domain first** — `full-stack-fastapi-template` has only
User/Item/SavedSearch (no Workspace/Project/Task), so the brief was re-grounded
on CalendarEvent + `Item.due_date` + EventAttendee/CalendarShare/UserAvailability
(`/tmp/bl6rerun/horizon_brief.md`). PO decomposed into **8 well-structured,
correctly-grounded BLs** (`_brownfield/features/team-calendar-horizon/BACKLOG.md`).

## A52 — false no_op after a pre-grounding kill (FOUND + FIXED this session)
First run: BL-0001's engineer was **Tier-1.5 (pre_grounding) killed** (tried to
Write before ≥3 grounded retrieval calls), committed nothing, then was falsely
marked **`no_op`** ("work already satisfied upstream, eng_patterns.md present at
HEAD"). Verified: **no CalendarEvent on the branch** — the foundation was
silently skipped, and all 7 dependent BLs would build on sand. Stopped via
End-Sprint (clean: 2 worktrees + 1 gate stack + 5 images reaped, nothing merged).

**Root cause:** `doctrine_validator.validate_engineer`'s R11 no-op check was
`(zero committed diff) AND artifact_path.exists()` — `.exists()` reads the
**working tree**. A killed engineer writes eng_patterns.md before code, so the
artifact is on disk while zero code is committed → misread as the legitimate
"inherited from an earlier BL" no-op. The no-op short-circuit returns *before*
the doctrine-retry loop, so retry was skipped too.

**Fix (`ebcf4eb`, UNPUSHED at handoff):** require the artifact to be
**committed at HEAD** (`_is_committed_at_head` → `git cat-file -e HEAD:<rel>`),
not merely present in the worktree. A killed-before-implementing engineer now
fails validation → R10.1 doctrine retry → on exhaustion `engineer_unmerged`,
never a false `no_op`. Legit inherited-no-op preserved; net-new foundation BLs
inherently never no_op-eligible. Test `test_engineer_noop_pregrounding_kill.py`
(3 cases). Ledger A52 (HIGH).

## Re-run — clean abort at BL-0001 (the capability wall)
With A52 live, BL-0001 built cleanly (85 grounding calls, no pre_grounding kill —
it was a one-off). But its CalendarEvent foundation **broke login**:
`auth.setup.ts` `page.waitForURL` 90s timeout after Log In → cascaded ALL
auth-gated specs (admin/user-settings/search) + a backend
`sqlalchemy.orm.exc.ObjectDeletedError(CalendarEvent)`. Gate `regressed` 3×
(A39 named the tests each time: admin/search/user-settings → narrowed to
`auth.setup.ts:6:1`). The engineer **chased the symptom specs without
root-causing the auth break**, R10.2 exhausted → `awaiting_review` →
`engineer_unmerged` → **clean `aborted`** ("engineer did not merge BL-0001").
Nothing broken merged; broken work quarantined on `agent/fd5263480b39` (RED).

## The lesson (two halves)
- **Harness: validated.** A39 named failures ✓, A52 no false-no_op ✓,
  wedge-proof + stop_on_failure → clean terminal ✓ — vs the 8h silent wedge this
  same session *started* with. The control plane now fails honestly and visibly.
- **Crew: real capability wall.** It couldn't root-cause/repair its own auth
  regression within the gate-retry budget — the SAME shallow-vs-deep diagnosis
  gap the v0.2 acceptance investigator ([[arch-acceptance-v02]]) addresses, here
  in the *engineer's* `build_gate_fix_prompt` loop. Open idea: give the engineer
  a "root-cause before you patch" directive so it stops chasing symptom specs.

## Next-session decision (operator deferred)
Diagnose why BL-0001 broke login (read `agent/fd5263480b39` diff — regenerated
`client/*` / model relationship / migration / router registration?) → small fix
vs hard integration → hand-fix + `skip_po=True start_bl=BL-0002` to resume, OR
re-run, OR accept as the capability finding. See `CONTINUATION_PROMPT.md`.
