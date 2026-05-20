---
name: brownfield-production-branch
description: Current working branch (brownfield-production) — what it adds, what target repo it operates on, current state
metadata:
  type: project
---

The `brownfield-production` branch (off `webapp`) makes the webapp able to
drive PO/Engineer/QA/Scorer agents through a real legacy codebase using a
distinct "brownfield doctrine."

**Why:** The greenfield doctrine on the `webapp` branch produced
single-shot CRUD demos. Goal here is **traceable, low-risk incremental
delivery on existing real-world codebases**.

**How to apply:** Whenever working in this branch, assume every PO/Eng/QA
agent is configured to read a `SKILLS.md` doctrine file verbatim, write
required artifacts under `_brownfield/`, and is enforced by a hard
pre-merge validator that re-invokes them on missing artifacts.

## First brownfield target

- `~/dev/ai-projects/brownfield-targets/full-stack-fastapi-template/`
  (cloned from `fastapi/full-stack-fastapi-template`)
- Symlinked into webapp as `webapp/backend/repos/full-stack-fastapi-template`
- Branches: `master` (pristine upstream, NEVER touched by agents),
  `agentic-skills-work` (all PO/Engineer/QA/Scorer commits land here)

## Status as of last session

- Phase A–F brownfield plumbing committed (prompts, sidecar rubric,
  retro-config, regression gate, doctrine validator, UI updates).
- BL-0001 (Workspace SQLModel + Alembic revision) **complete**:
  PO 13 BLs / Engineer commit `6abe64e` / QA PASS commit `011baeb` /
  Scorer **92/100 Pass** commit `45464e1`.
- Master remains pristine at `32ebacf`; all agent work lives on
  `agentic-skills-work`.
