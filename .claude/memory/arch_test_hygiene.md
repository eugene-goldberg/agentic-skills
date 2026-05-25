---
name: arch-test-hygiene
description: A32 case study + R14 doctrine — QA tests can hang the gate via TestClient(app) connection leaks + Alembic DDL vs session-scoped fixture. Both fixed at framework (pytest --timeout=120) and doctrine (R14 in QA SKILLS.md) layers. Defense-in-depth pattern.
metadata:
  type: project
---

# A32 — gate hangs from QA test design defects (RESOLVED)

## The fact (sprint run-20260524T220528Z-f56070, BL-0001 QA gate)

QA agent wrote `test_workspaces_qa.py` with two patterns that combined
to hang the regression gate for 30+ minutes:

1. **Leaked `TestClient(app)` connections.** The `_add_member` helper
   instantiated `TestClient(app)` inside a function body, called 1+
   times per test across 8 tests — never inside a `with` context
   manager. Each instance opened an ASGI lifespan-bound DB connection
   that never released.

2. **Alembic DDL with session-scoped fixture held open.** The 8th test,
   `test_alembic_upgrade_downgrade_upgrade_round_trip`, called
   `command.downgrade(cfg, "fe56fa70289e")` which `DROP TABLE workspace`.
   `DROP TABLE` requires `AccessExclusiveLock`, blocked indefinitely by
   the leaked connections from the prior 7 tests.

The original gate hung at 64/77 PASSED; reproduction on local stack
confirmed the same hang point with the same root cause.

## Why this matters

A single QA-agent-written test design defect held an entire sprint
hostage for 30+ minutes (would have been hours without operator
intervention). The framework had no defense against this class of
deadlock. Future agents could write the same kind of test and trigger
the same hang.

## The two-layer fix (both shipped 2026-05-24)

**Framework defense** — target commit `c7ea13e` on `agentic-skills-work`:
`scripts/regression_gate.sh` now runs backend pytest with `--timeout=120
--timeout-method=signal` via inline pytest-timeout install. Any
deadlock-prone test now fails as `Failed: Timeout >120s` (a normal
test failure pytest can report) instead of hanging until the
orchestrator's 30-min asyncio wait_for fires. Shell `timeout 900`
backstop kills the whole pytest invocation if pytest itself wedges.

**Doctrine prevention** — agentic-skills commit `7ffad52` on
`architect-prereqs`: new R14 in
`skills/brownfield/brownfield-production-incremental-qa/SKILLS.md`
with three sub-rules:

- **R14.1** — never instantiate `TestClient(app)` outside `with`; use
  the module-scoped `client` fixture from conftest.py
- **R14.2** — no Alembic DDL when the session-scoped `db` fixture is
  open; use isolated module-scoped tear-down, or test via
  script_directory walker, or skip with explanation
- **R14.3** — per-test timeout discipline; default 120s, opt out only
  with explicit `@pytest.mark.timeout(N)` and justification

## How to apply

When debugging future gate hangs:

1. **Check whether a test is hung vs slow** — pytest output frozen at
   N% with no progress for >2 min = hung. Look at the NEXT test in
   pytest order (last reported test's file + position).
2. **If hang exists despite R14 + timeout** — likely a new pattern.
   File as A-class shortcoming, classify against I-2 (doctrine
   contract) or I-3 (closure postconditions), propose fix.
3. **If R14 is violated** — escalate to doctrine-meta-agent at sprint
   end; do not patch the test in-flight (per architect boundary).

## Lessons that generalize

- **Defense-in-depth wins.** Doctrine prevents the pattern; framework
  catches it if doctrine fails. Either alone is insufficient — agents
  can violate doctrine, frameworks can have edge cases doctrine
  documents.
- **Hangs are the worst failure mode.** They burn time, mask the real
  cause, and trigger flaky-test pattern-matching (operator assumes
  infra is slow, not deadlocked). Always bound any subprocess call.
- **Don't blame the agent's code in isolation.** When an agent writes
  broken code that triggers a framework hang, BOTH layers need
  fixing — agent retrains via doctrine, framework hardens via
  defense.

## When to revisit

If the same hang reappears after R14 + 120s timeout are in place:
- Doctrine wasn't loaded by the QA agent (check skill_loader output)
- pytest-timeout install failed silently (check stderr)
- A different test bypassed signal-based timeout (rare; some
  C-extension code blocks signal handling — use thread method as
  fallback)

Cross-ref [[arch-gate-throughput]] for the related gate-time
optimization items (A28-A31).
