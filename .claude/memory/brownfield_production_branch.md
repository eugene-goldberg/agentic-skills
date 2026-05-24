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

## Active brownfield target

- `~/dev/ai-projects/brownfield-targets/full-stack-fastapi-template/`
- Symlinked at `webapp/backend/repos/full-stack-fastapi-template`
- Sprint branch progression:
  - `master` — pristine upstream, never touched
  - `agentic-skills-work` — Sprint 1 (Team Collaboration Module, 12 merged BLs)
  - `agentic-skills-work-v2` — Sprint 2 archive
  - `agentic-skills-work-v3` — Sprint 3 + Sprint 4 (Notifications & Activity System); current sprint tip at `bdaf4c4` + Sprint 4 advances post-poll

## Recent sprint completions

- Sprint 1: Team Collaboration on `agentic-skills-work`, 12+1 BLs merged, mean score ~92/100.
- Sprint 2: full collab dogfood on `agentic-skills-work-v2`.
- Sprint 3: Notifications & Activity System — **aborted** at BL-0005 non-FF; recovered manually.
- Sprint 4 (active): Notifications continuation — BL-0001..BL-0005 closed (mix of no_op and merged_full), BL-0006 retry loop active for layout-shift regression in pre-existing Playwright tests. Hardening validations all green so far.

Source: branch list in `CLAUDE.md`, git log on `sprint-2-orchestrator` + `architect-prereqs`, `ARCHITECT_TRACKER.md`.
