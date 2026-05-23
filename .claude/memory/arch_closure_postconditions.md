---
name: arch-closure-postconditions
description: I-3 — at run termination, the orchestrator verifies the world matches cleanup's intent; violations are structured events, not silent leaks
metadata:
  type: project
---

Cleanup paths today are "do the cleanup and hope." Closure-postcondition discipline says "do the cleanup AND assert the postcondition AND emit a `closure_violation` event if assertion fails."

**Why:** Sprint 4 surfaced 30-hour-old `regression_gate.sh` + multiple docker containers from prior sprints. Nothing checked. We discovered them only because I manually ran `ps -eo command | grep regression_gate`. With closure assertions, the orchestrator would have emitted a structured violation at sprint termination, and the doctrine-meta agent would have read it as evidence for the A9 candidate.

**How to apply:**
- At every run termination (success, abort, exception, GeneratorExit), call a `closure_check()` that runs each postcondition independently (one failure doesn't skip others).
- Required checks at minimum: 0 child PIDs from this run's pgroups, 0 stale agent-worktrees, 0 stale gate-worktrees, 0 dangling agent branches, 0 docker containers labeled with this run_id (requires labeling — separate work), `traces_archive/<run_id>/` exists, `done/<run_id>.json` exists.
- Violations get `orchestrator.closure_violation` events with `kind`, `resource`, `detail`. Doctrine-meta reads these.

The five components needing closure checks today: `claude_agent`, `regression_gate_svc`, `indexing.graphify`, `indexing.claude_context`, `orchestrator.run_brief` itself.

Source: `ARCHITECTURE_INVARIANTS.md` § I-3.
