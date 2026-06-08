---
name: arch_target_beaverhabits
description: "Second brownfield target (Exp-2 substrate realism) — real third-party FastAPI app daya0576/beaverhabits, wired + gate-verified 2026-06-07"
metadata: 
  node_type: memory
  type: project
  originSessionId: be51e21b-1239-4b56-b567-6fbcd02be99e
---

**Exp-2 substrate** = first REAL third-party brownfield target (vs the
purpose-built toy `project-management-app`). Repo: `daya0576/beaverhabits`
(habit tracker, BSD-3, ~1.8k★). Stack: FastAPI + fastapi-users +
SQLAlchemy-async + **aiosqlite (SQLite)**, NiceGUI server-rendered frontend
(Python, NOT React). ~62 app .py files / ~7.9k LOC — tractable to index.

Location: `~/dev/ai-projects/brownfield-targets/beaverhabits` (outside
agentic-skills, per the boundary). Symlinked at
`webapp/backend/repos/beaverhabits` (gitignored). Branch model: pristine
`main`, fork/merge sink `integration` (both carry the bootstrap config).

Baseline test command (the repo's own CI): `DATABASE_URL=
"sqlite+aiosqlite:///:memory:" HABITS_STORAGE="USER_DISK" uv run pytest`
→ **48 passed, Docker-free, ~6s**. `test_gui` uses NiceGUI's in-process
harness (no real browser/webdriver despite selenium dep).

Two gotchas found during onboarding (both handled):
1. **Python pin landmine.** Upstream ships `.python-version = 3.14.0` (a
   pre-release) → `uv` segfaults C-extensions on this host (exit 139, zero
   output). Overridden to `3.12` in the bootstrap commit. ALWAYS verify the
   pin is stable, not just that `requires-python` allows it.
2. **Gate couldn't run it** until [[arch_gate_multitoken_testcmd]] (A57)
   shipped — its `test_cmd` is multi-token (`uv run pytest`) and needs env
   (`DATABASE_URL`/`HABITS_STORAGE`); the old gate kept only `test_cmd[0]`
   and had no env path.

`.agentic-skills.json`: agent_branch=integration, main_ref=main,
doctrine=brownfield, test_cmd=`["uv","run","pytest"]`, test_env sets the two
SQLite/storage vars. Gate proven green live through the real harness
(`run_gate` 48/48 0-regressions; `run_bl_tests` green on a probe branch).

Candidate Exp-2 feature (non-telegraphed, discovery-style like Exp 1b):
streak freeze/skip-days + retroactive backfill → streak recompute across
day-boundaries/timezones + backfill idempotency. Not yet briefed/launched.

See [[arch_target_pm_app]] (the toy target this complements), [[arch_horizon_run]].
