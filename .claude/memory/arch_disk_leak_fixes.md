---
name: arch-disk-leak-fixes
description: "A48 disk-leak prevention — the four shipped fixes that keep Docker.raw under the 60 GB Mac VM cap during multi-BL brownfield sprints. Lowercase acceptance compose name, worktree-spawned-compose reaper, orchestrator SIGTERM handler, pre-existing pre-flight + volume reaper + DiskFull classifier from earlier A48 work."
metadata: 
  node_type: memory
  type: project
  originSessionId: 68d7b58a-c1db-43e1-bf9a-cac442cd4c1d
---

## Why this exists

Docker Desktop on macOS allocates a fixed-size VM disk (`~/Library/Containers/com.docker.docker/Data/vms/0/data/Docker.raw`). Default cap is ~60 GB. A 12-BL brownfield sprint can fill this cap before sprint_complete if compose stacks leak — and the orchestrator + agents + gate spawn many.

Today (2026-06-02) we hit ENOSPC three times across 5 sprint attempts on Financial_Management before identifying and fixing the leak classes.

## The four shipped fixes (commit `02ebd7b`)

| # | Fix | Code location | Leak it closes |
|---|---|---|---|
| 1 | **Lowercase acceptance compose project name** (`.lower()`) | `orchestrator.py:1199` | ISO-8601 run_ids have uppercase T/Z → fail `volume_reaper._PROJECT_NAME_RE = ^[a-z0-9][a-z0-9_-]*$` → reaper no-ops on every acceptance run → postgres data volume leaks ~2-3 GB per run. Verified earlier: live error `"invalid project name 'acceptance-...T...Z'; must match docker compose lowercase"`. |
| 2 | **Worktree-spawned compose reaper** in `remove_worktree` | `git_worktree.py::_reap_worktree_compose_stacks` | Engineer/QA/scorer agents have Bash access in their worktree and may `docker compose up` to test code interactively. Default project name = basename(cwd) = task_id. Two passes: (a) `docker compose -p <task_id> down -v` for default-name case, (b) label-based sweep on `com.docker.compose.project.working_dir=<wt.path>` for explicit-`-p` cases. Verified BL-0006 leftover `9b04804af277-db-1` ran 2h pre-fix. |
| 3 | **Orchestrator SIGTERM shutdown handler** | `main.py::_reap_orchestrator_compose_stacks` (FastAPI `@app.on_event("shutdown")`) | Force-kill of uvicorn doesn't propagate SIGTERM cleanly; gate scripts' `trap cleanup EXIT INT TERM` doesn't fire; compose stacks orphan. Handler scans `docker ps -a` for projects starting with `agentic-skills-` or `acceptance-` and runs `down -v --remove-orphans` for each, dedup'd. |
| (earlier A48 work, shipped 2026-06-01) |  |  |  |
| pre-flight | `disk_preflight.check()` at `/run-brief` submission | `disk_preflight.py` | Refuses sprint if free disk below floor (default 5 GB) + per-BL estimate (1 GB × n_bls). |
| reaper | `volume_reaper.reap(project)` | `volume_reaper.py` | `docker volume prune --filter label=com.docker.compose.project=<project>`. Called after every gate + after acceptance archive. |
| classifier | DiskFull-aware regression_gate verdict | `regression_gate.py:_classify_disk_full` | Distinguishes "host ENOSPC" from "real test regression" so the orchestrator doesn't blame the engineer for an infra failure. |

## Test posture

11 new tests for the 4-fix shipment:
- `test_worktree_reaper.py` (7) — pass 1 + pass 2 sweep, error swallowing, ordering (reaper before git worktree remove)
- `test_shutdown_reaper.py` (4) — dedup, empty docker ps, docker absent, project prefix filtering

Plus the 23 pre-existing A48 tests (disk_preflight 10, volume_reaper 13).

## The remaining gap (sibling to A48)

**Force-kill of uvicorn doesn't trigger the worktree reaper.** Fix #3 (SIGTERM handler) reaps Docker stacks but the per-worktree `_reap_worktree_compose_stacks` only fires from `remove_worktree`. Today (2026-06-02) I had to manually `git worktree remove --force` 5 leftover worktrees from the day's killed sprints.

**Mitigation for now:** use Ctrl+C (SIGTERM) to kill uvicorn, not `kill -9`. SIGTERM fires the FastAPI shutdown handler + lets the orchestrator's `finally` blocks run, which call `remove_worktree`.

**Permanent fix would be:** extend the SIGTERM handler to walk `<repo>/.agent-worktrees/` and `<repo>/.gate-worktrees/` and `git worktree remove --force` each. Worth filing as a follow-up to A48.

## How to apply

If a future sprint or session experiences mid-sprint ENOSPC despite this work:

1. **First check:** is the leak class one of the four covered above? Run `docker system df` + check `_PROJECT_NAME_RE`.
2. **Then check:** are there leftover compose projects matching `agentic-skills-*`, `acceptance-*`, or worktree-task-id pattern? `docker ps -a --format '{{.Names}}\t{{.Label "com.docker.compose.project"}}'`.
3. **If yes:** it's the force-kill worktree leak (sibling above) or a new class. Either way, manual `docker compose -p <project> down -v` then file a new arch entry.

## Code locations
- `webapp/backend/app/services/git_worktree.py` (Fix #2)
- `webapp/backend/app/main.py` (Fix #3)
- `webapp/backend/app/services/orchestrator.py:1199` (Fix #1)
- `webapp/backend/app/services/disk_preflight.py` (earlier)
- `webapp/backend/app/services/volume_reaper.py` (earlier)
- `webapp/backend/app/services/regression_gate.py` (earlier classifier)
- Tests: `webapp/backend/tests/test_worktree_reaper.py`, `test_shutdown_reaper.py`, `test_disk_preflight.py`, `test_volume_reaper.py`, `test_disk_full_classifier.py`
- Ledger entry: see `DESIGN_SHORTCOMINGS.md` A48 entries
