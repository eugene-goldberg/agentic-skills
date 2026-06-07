---
name: arch-target-pm-app
description: Current brownfield target — project-management-app (Docker-free FastAPI+SQLite+React); how it's wired and gated
metadata:
  type: project
---

The active brownfield target as of 2026-06-06, purpose-built to replace the
removed `full-stack-fastapi-template`. Operator constraints: FastAPI / React /
SQLite, "simple project management app", **API-first**, **no Docker**.

## Location & wiring
- Repo: `~/dev/ai-projects/brownfield-targets/project-management-app/`
- Symlink: `webapp/backend/repos/project-management-app` → above
- `.agentic-skills.json`: `agent_branch=integration`, `main_ref=main`,
  `doctrine=brownfield`, `test_cmd=[<abs>/.venv/bin/pytest, backend/tests, -q]`

## Stack (least-complicated, per operator)
- Backend: FastAPI + SQLModel + **SQLite** file (`app.db`). **No auth**
  (open API, no User model — domain is just Project → Task). **No Alembic** —
  schema via `SQLModel.metadata.create_all` on startup.
- Frontend: React + Vite + TypeScript; typed `api.ts` client; dev server
  proxies `/api` to backend :8000. One vitest test (NOT yet `npm install`ed/run).
- One root `pyproject.toml` carries deps + `[tool.pytest.ini_options]
  pythonpath=["backend"]` so `import app` resolves to the worktree's source.

## Why no-Docker gating works (verified live)
`run_bl_tests` checks `compose.yml && compose.gate.yml`; this repo has
neither → it takes the native branch: `[test_cmd[0], "-v", *bl_test_files]`
run in a detached gate worktree. The gate worktree has **no `.venv`** (gitignored),
so `test_cmd[0]` is the **absolute** path to the main checkout's venv pytest;
app code is imported from the *worktree* via the repo-root `pythonpath`.
Proven by simulating the exact invocation in a detached worktree off
`integration`: 8 per-BL + 16 full-suite passed, no Docker.

## Branch model
- `main` — pristine baseline; never receives crew commits (gate diff target +
  rollback point).
- `integration` — agents fork worktrees off it and auto-merge green BLs into it.

## State
Created 2026-06-06; baseline backend suite green (16 tests, native pytest,
~0.15s). **No sprints run yet.** First sprint should (re)generate
`BROWNFIELD_PROGRESS.md` for this target.

## Caveats
1. `test_cmd` hard-codes an absolute venv path → brittle if the target moves;
   the venv must exist there (README documents recreating it).
2. Per-BL gate is Python-only (`_bl_test_files` matches `test_*.py`); frontend
   BLs get `no_tests` and are exercised at the acceptance phase instead.
   Consistent with the API-first emphasis.
3. System python was 3.14; hit + fixed a SQLModel relationship bug caused by
   `from __future__ import annotations` (stringized `list['Task']`). models.py
   deliberately omits that import.

See [[brownfield-production-branch]], [[agentic-skills-json-convention]],
[[feedback-simple-gating-model]].
