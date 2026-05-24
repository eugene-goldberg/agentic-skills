---
name: arch-active-branch
description: Active work location as of 2026-05-23 — branch architect-prereqs implementing the four prerequisites for full architect-mode operation
metadata:
  type: project
---

Active work branch: **`architect-prereqs`** (off `sprint-2-orchestrator` at `710992b`). Created 2026-05-23 after operator authorized all four prerequisites named in the architect-mode discussion.

**Why:** Sprint-2 hardening (the 18-item pass) landed on `sprint-2-orchestrator`. Sprint 4 ran on it and validated most fixes but surfaced A8 (R9 enforcement gap) and A9-candidate (gate subprocess pgroup leak). The pattern of "patch one site, sibling sites still leak" forced the architect-level pass on a fresh branch.

**How to apply:**

- **Plan:** [`ARCHITECT_PLAN.md`](../../ARCHITECT_PLAN.md) — 4 batches A-D, 13 sub-items total, atomic per item.
- **Tracker:** [`ARCHITECT_TRACKER.md`](../../ARCHITECT_TRACKER.md) — live checklist.
- **Foundation:** [`ARCHITECTURE_INVARIANTS.md`](../../ARCHITECTURE_INVARIANTS.md) — the structural lens that drove the four prerequisites.

**Status at memory write time (2026-05-23 ~7:00pm CDT):**

| Batch | Items | Status |
|---|---|---|
| A — Architectural memory artifacts | A-1, A-2, A-3 | **done** (commits `658dcb1`, `a50026a`, `a2fa12a`, tracker `2185cef`) |
| B — Doctrine-meta-agent (ABL-0003) | B-1 through B-5 | pending; awaiting operator "go Batch B" |
| C — Framework-reviewer adversarial role | C-1 through C-4 | pending |
| D — Scheduled observer | D-1 through D-3 | pending |

**Branch state:** 7 commits ahead of `sprint-2-orchestrator`. Sprint 4 still running on `sprint-2-orchestrator` (launcher PID 14719 alive); uvicorn unaffected by the working-tree branch switch.

**Next session protocol:** read `CLAUDE.md` first, then `ARCHITECTURE_INVARIANTS.md`, then `ARCHITECT_PLAN.md` + tracker. Confirm Sprint 4 status. Await operator authorization before starting Batch B.

Source: `ARCHITECT_PLAN.md`, `ARCHITECT_TRACKER.md`, commit log on branch `architect-prereqs`.
