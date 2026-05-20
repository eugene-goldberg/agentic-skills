---
name: brownfield-known-gotchas
description: Three issues encountered during BL-0001 that will recur unless mitigated
metadata:
  type: feedback
---

Three gotchas discovered while running the first full PO → Engineer →
QA → Scorer cycle against `full-stack-fastapi-template`. Each has a
mitigation pattern future runs should follow.

## 1. Don't gitignore the doctrine artifact dir

**Why:** I initially bootstrapped the brownfield target with
`_brownfield/` in `.gitignore` as a defensive measure against pushing
artifacts back to upstream master. The gitignore silently dropped every
PO/Engineer/QA artifact from `git add -A`. Agents wrote files; commits
didn't carry them; worktrees forked off the agent branch came up empty;
the role hand-off chain (Engineer → QA reads eng_patterns.md) broke.

**How to apply:** When bootstrapping a new brownfield target, only
gitignore secrets and machine-local state. The `agent_branch` IS the
boundary that keeps artifacts off `master`. Removing the gitignore was
committed as `72fd7de` on the full-stack-fastapi-template clone — use
this as the template for new brownfields.

## 2. Regression gate needs a runnable test command

**Why:** Engineer's auto-merge gate runs `pytest -q` pre/post in a
disposable worktree. `full-stack-fastapi-template` actually runs tests
inside its own Docker stack. Two failure modes:
(a) `pytest` not on PATH → gate crashes the SSE stream (fixed in
    `regression_gate.py` by wrapping the spawn in try/except);
(b) `docker compose exec backend pytest` returns exit 15 with no
    parseable test output because the compose stack isn't running →
    gate now reports `kind=inconclusive` rather than misleading
    `kind=green`.

**How to apply:** Before relying on the regression gate, verify the
configured `test_cmd` actually runs from a fresh subprocess of the
uvicorn process (not just from your shell). For Docker-based test infra,
either keep the compose stack up via `docker compose up -d`, or accept
that the gate will be inconclusive and use the force-merge endpoint /
add a `disable_regression_gate` flag.

## 3. Engineer often skips characterization tests

**Why:** The Engineer skill says "characterization tests when touching
legacy" but the BL-0001 engineer shipped 9 happy-path/relationship tests
and left adversarial coverage (orphan FK, cross-owner isolation, alembic
linearity, boundary lengths) for QA to add. The scorer correctly
docked points for the role-axis "test discipline" and brownfield
"characterization tests" dimensions.

**How to apply:** Watch for this pattern repeating. If it does on
BL-0002 / BL-0003, consider strengthening the Engineer prompt's
ENG_COMPLETION_PROTOCOL with an explicit `at minimum N adversarial /
characterization tests; QA-added counts deduct from your score` line.
