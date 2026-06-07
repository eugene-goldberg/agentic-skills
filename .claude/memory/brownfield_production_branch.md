---
name: brownfield-production-branch
description: Branch progression of the brownfield doctrine work; current operational tip + active development branches as of 2026-05-23
metadata:
  type: project
---

Brownfield work progressed through three operational tips:

| Branch | Role | State |
|---|---|---|
| `brownfield-production` | Original brownfield doctrine on top of `webapp` | superseded; historical |
| `sprint-2-orchestrator` | ABL-0001 orchestrator + completed 18-item Sprint-2 hardening pass | current operational tip; Sprint 4 ran from here |
| `architect-prereqs` | Architect-mode prerequisites (memory layer + doctrine-meta + framework-reviewer + observer) | **active development** as of 2026-05-23 |

**Why:** The greenfield doctrine on `webapp` produced single-shot CRUD demos. `brownfield-production` introduced low-risk incremental delivery on existing codebases via per-role SKILLS.md + doctrine validator + regression gate + sidecar rubric. `sprint-2-orchestrator` added the ABL-0001 orchestrator and the 18 hardening fixes (commits `f1bb6b1`…`0bf3afb`) after Sprint 3 abort. `architect-prereqs` adds the self-hardening loop so future sprints find shortcomings without me.

**How to apply:** When working on framework code (not target-repo code), branch from current architect tip. When dogfooding the framework on a brownfield target, work proceeds on `agentic-skills-work-v3` inside the target repo (NOT in this checkout).

## Active brownfield target (2026-06-06 → )

- `~/dev/ai-projects/brownfield-targets/project-management-app/`
- Symlinked at `webapp/backend/repos/project-management-app`
- **Docker-free**: FastAPI + SQLModel + SQLite (no auth, `create_all`, no
  Alembic) + React/Vite/TS; API-first "simple project management app"
  (Projects → Tasks). See [[arch-target-pm-app]].
- Branches:
  - `main` — pristine baseline, never touched (gate diff target)
  - `integration` — agent fork point + auto-merge sink (`.agentic-skills.json`)
- Baseline suite green (16 backend tests, native pytest); **no sprints run
  yet**.

## Prior target (removed 2026-06-06) — historical

`full-stack-fastapi-template` (Docker-based, `master`/`agentic-skills-work*`)
hosted Sprints 1–4 (Team Collaboration, Notifications, Financial-Management,
Intelligent-Kanban, Search & Discovery, Item-Comments, Horizon). The clone and
all ~91 crew branches were deleted on operator instruction. The run histories
remain in the historical-run memories ([[arch-horizon-run]],
[[arch-intelligent-kanban-sprint]], [[arch-live-run-invoice-soft-delete]],
[[arch-harness-hardening]]) — those are not rewritten.

Source: branch list in `CLAUDE.md`, git log on `sprint-2-orchestrator` + `architect-prereqs`, `ARCHITECT_TRACKER.md`.
