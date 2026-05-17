# Engineering Work Packet: BL-0004

## Run

- Run ID: `eng-lg-lg-SKILLS-bl-0004`
- Engineering Skill: `lg-SKILLS`
- Target Repo: `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/target-repos/lg-graph-test`
- Baseline Commit: `6c9984ac980bf530316e373176165ce92998d35a`
- Backlog Item: `BL-0004`

## Source Context

- Requirements: `REQUIREMENTS.md`
- Backlog: `.agile-v/BACKLOG.md`
- Sprint Plan: `.agile-v/sprints/C1/SPRINT_PLAN_C1.md`
- Engineering guide: `ENGINEERING_GUIDE.md` (if present)

## Selected Backlog Item

## BL-0004: Database Models and Migrations (Users, Workspaces, Memberships)
**Type:** Technical · **Priority:** CRITICAL · **REQ:** REQ-0003, REQ-0004, REQ-0005
**Story:** As a developer, I want persistent models for users, workspaces, and memberships so that workspace and membership features can be built on a stable schema.
**Acceptance:**
1. SQLAlchemy (or equivalent ORM) models exist for User, Workspace, and WorkspaceMembership.
2. WorkspaceMembership links a User to a Workspace with a role (`owner` | `member`).
3. Migration scripts or auto-create mechanism is in place.
4. Database connection is configurable via environment variable.
**Effort:** 3 · **Dependencies:** BL-0001 · **Status:** Ready

---


## Related Requirements

(no REQ excerpts available)

## In Scope

Implement only the behavior in this BL item's Acceptance section. Stay within the BL's stated REQ references.

## Out Of Scope

- Anything from other backlog items.
- Refactors, dependency bumps, or hygiene changes not required to deliver this slice.
- Running or fixing `verify_blNNNN.py` for any BL other than this one. Cross-BL regression coverage is the QA role's responsibility, not engineering's. If a prior-BL verifier appears broken due to environment/tooling noise, IGNORE it — do not modify it, do not investigate it. Your only verifier is `verify_bl0004.py` for this BL.

## Expected Artifacts

- Updated source files in the target repo.
- New or updated tests under `tests/`.
- A `verify_bl0004.py` BL-specific sanity checker at the repo root.
- Updated `scripts/full_http_smoke.py` (if it exists, extend its coverage for this BL).

## Verification Commands

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl0004.py
.venv/bin/python scripts/full_http_smoke.py
```

Run these inside the target repo. All must pass before you declare the cycle complete.

## Done Criteria

- Every Acceptance criterion in the BL block above is covered by at least one test.
- All verification commands exit zero.
- The target repo is on a new commit that begins with `Implement BL-0004`.
- No file in `REQUIREMENTS.md`, `.agile-v/BACKLOG.md`, or `.agile-v/sprints/C1/SPRINT_PLAN_C1.md` has been modified.
