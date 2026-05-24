---
name: arch-mission-framing
description: Operator correction 2026-05-23 — the mission is the autonomous synthetic crew itself, not operator-time metrics. Metrics are symptoms.
metadata:
  type: feedback
---

The mission of agentic-skills is to build a **completely autonomous
synthetic AI agent crew** that operates as a software development team and
is fully capable of adding new complex features to existing brownfield
projects.

**Why:** Operator corrected me on 2026-05-23 after I framed strategic
moves around "operator-time-per-feature < 1 hour." That framing inverts
cause and effect. Operator time collapses *because* the crew is capable
and autonomous; it is not the thing being built. Treating the metric as
the mission produces process-tuning around the operator instead of
capability-building inside the crew.

**How to apply:**
- The crew is synthetic end-to-end. PO, Engineer, QA, scorer, and every
  future role (doctrine-meta, framework-reviewer, observer) are AI
  agents. The operator is the customer of the crew, not a member.
- "Autonomous" means: kickoff → final report with no human in the loop
  for the bulk of the work. Not "human approves each step faster."
- "Capable" means: significant complex features on real brownfield repos
  with their own history, tests, conventions. Not toy CRUD.
- Architectural moves are crew capabilities, not operator-cost
  reductions. The doctrine-meta-agent ([[arch-self-hardening]]),
  closure-check ([[arch-closure-postconditions]]), and ManagedSubprocess
  ([[arch-subprocess-lifecycle]]) are missing capabilities of the crew,
  not productivity tools for the operator.
- When proposing strategy, frame every move as "what the crew gains" not
  "what the operator saves." If the crew gains nothing, the move is
  wrong regardless of operator-time impact.

Related: [[arch-claude-role]] (architect accountability for delivery of
this mission), [[arch-invariants]] (the seven rules whose satisfaction
constitutes a working crew).
