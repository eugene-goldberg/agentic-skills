---
name: arch-self-hardening
description: I-7 — in steady state, no new R-rule or invariant comes from a human; the framework observes its own failures, proposes hardening, opens operator-gated proposals
metadata:
  type: project
---

Every R-rule from R5 onward was added by Eugene (operator) or me (claude) manually. The framework cannot catch up to itself; each sprint exposes 1–3 new things only AFTER they fail in production. The architect-prereqs branch (Batches B + C) introduces the loop that closes this gap.

**Why:** The "we keep finding new bugs" pattern isn't a hardening failure — it's the structural cost of human-only doctrine evolution. With 18 fixes landed and Sprint 4 still finding A8 + A9 candidate, the find-rate per sprint is roughly constant. Only a meta-agent reading every sprint's traces + R-rule trigger counts + scorer findings can keep up. ABL-0003 in BACKLOG.md is the spec; Batch B of ARCHITECT_PLAN.md is the implementation.

**How to apply:**
- After every sprint_complete, the doctrine-meta agent runs against `traces_archive/<run_id>/`.
- It identifies recurring failure modes ("in N of M BLs the engineer omitted X, R-rule Y had to retry").
- Drafts a proposal under `.planning/doctrine_proposals/<sprint>-<topic>.md` with motivation, evidence count, proposed change.
- Framework-reviewer (Batch C) adversarially reviews the proposal.
- Operator approves OR rejects. NEVER auto-merged. Auto-applying doctrine changes risks runaway self-modification — the agent could loosen a rule that triggered an inconvenient retry; next sprint silently degrades.

The proposal-review-approve loop preserves operator authority forever. The doctrine-meta agent earns trust over many sprints; never gets one-click merge rights.

Companion: [[arch-doctrine-contract]] (the spec format the meta-agent's proposals must comply with).

Source: `ARCHITECTURE_INVARIANTS.md` § I-7; backlog spec at `BACKLOG.md` ABL-0003.
