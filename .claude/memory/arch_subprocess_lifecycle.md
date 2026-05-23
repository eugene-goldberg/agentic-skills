---
name: arch-subprocess-lifecycle
description: I-1 — every subprocess we spawn must register a cleanup hook reached on every exit path
metadata:
  type: project
---

Every external resource the orchestrator brings into being must register a cleanup hook on every exit path: success, abort, exception, consumer-disconnect, kill -9 → restart.

**Why:** B1 fixed orphan claude trees (start_new_session=True + `_kill_pgroup`). Sprint 4 then exposed a 30-hour-old `regression_gate.sh` + docker-compose orphan from a prior abort — same class of bug, different subprocess site. The B1 fix wasn't generalized; it was per-site. The architectural rule is "every spawn uses one primitive that handles lifecycle."

**How to apply:**
- Before adding a new `asyncio.create_subprocess_exec` call, check if a `ManagedSubprocess`-style wrapper exists. If not, that's the right place to refactor first.
- Audit the existing call sites: `claude_agent.stream_agent_task` ✓ (B1 compliant), `regression_gate_svc.run_gate` ✗ (A9 candidate), `indexing.run_graphify_update` ⚠, `indexing.run_claude_context_index` ⚠.
- Closure-check pairing: at run termination, scan for surviving PIDs whose pgid matches the run; surviving = `closure_violation` event. See [[arch-closure-postconditions]].

Sibling resources also in scope: worktrees, gate worktrees, docker containers (need labeling first), MCP config tmp files. Anything created must register removal.

Source: `ARCHITECTURE_INVARIANTS.md` § I-1.
