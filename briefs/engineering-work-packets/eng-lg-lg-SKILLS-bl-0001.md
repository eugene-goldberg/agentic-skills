# Engineering Work Packet: BL-0001

## Run

- Run ID: `eng-lg-lg-SKILLS-bl-0001`
- Engineering Skill: `lg-SKILLS`
- Target Repo: `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/target-repos/lg-graph-test`
- Baseline Commit: `329d767f9b66b522137fb9d97718299b1a33f112`
- Backlog Item: `BL-0001`

## Source Context

- Requirements: `REQUIREMENTS.md`
- Backlog: `.agile-v/BACKLOG.md`
- Sprint Plan: `.agile-v/sprints/C1/SPRINT_PLAN_C1.md`
- Engineering guide: `ENGINEERING_GUIDE.md` (if present)

## Selected Backlog Item

## BL-0001: Project Bootstrap and Database Schema
**Type:** Technical · **Priority:** CRITICAL · **REQ:** REQ-0022
**Story:** As a developer, I want a bootstrapped FastAPI project with database models so that the service can run and persist data.
**Acceptance:**
1. FastAPI app starts with `uvicorn` and responds to a health endpoint.
2. SQLAlchemy (or equivalent ORM) models exist for User, Workspace, Membership, Project, Task, and Comment with correct relationships.
3. Database migrations or auto-create tables are configured.
4. Project structure follows standard FastAPI layout (routers, models, schemas, dependencies).
**Effort:** 5 · **Dependencies:** none · **Status:** Ready


## Related Requirements

## REQ-0022 HTTP API Surface

- **Requirement:** The API exposes auth, workspace, project, task, comment, `/me/tasks`, and workspace summary routes described in the project brief.
- **Constraint:** All non-auth surfaces require `Authorization: Bearer <token>`.
- **Verification Criteria:** Protected endpoints reject missing tokens with `401`.
- **Done Criteria:** Route behavior is covered through real HTTP requests.

## In Scope

Implement only the behavior in this BL item's Acceptance section. Stay within the BL's stated REQ references.

## Out Of Scope

- Anything from other backlog items.
- Refactors, dependency bumps, or hygiene changes not required to deliver this slice.
- Running or fixing `verify_blNNNN.py` for any BL other than this one. Cross-BL regression coverage is the QA role's responsibility, not engineering's. If a prior-BL verifier appears broken due to environment/tooling noise, IGNORE it — do not modify it, do not investigate it. Your only verifier is `verify_bl0001.py` for this BL.

## Expected Artifacts

- Updated source files in the target repo.
- New or updated tests under `tests/`.
- A `verify_bl0001.py` BL-specific sanity checker at the repo root.
- Updated `scripts/full_http_smoke.py` (if it exists, extend its coverage for this BL).

## Verification Commands

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl0001.py
.venv/bin/python scripts/full_http_smoke.py
```

Run these inside the target repo. All must pass before you declare the cycle complete.

## Done Criteria

- Every Acceptance criterion in the BL block above is covered by at least one test.
- All verification commands exit zero.
- The target repo is on a new commit that begins with `Implement BL-0001`.
- No file in `REQUIREMENTS.md`, `.agile-v/BACKLOG.md`, or `.agile-v/sprints/C1/SPRINT_PLAN_C1.md` has been modified.
