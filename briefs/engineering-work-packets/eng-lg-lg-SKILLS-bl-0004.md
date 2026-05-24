# Engineering Work Packet: BL-0004

## Run

- Run ID: `eng-lg-lg-SKILLS-bl-0004`
- Engineering Skill: `lg-SKILLS`
- Target Repo: `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/target-repos/lg-graph-test`
- Baseline Commit: `87ae85214c968f4c508910e327aa1919abc45991`
- Backlog Item: `BL-0004`

## Source Context

- Requirements: `REQUIREMENTS.md`
- Backlog: `.agile-v/BACKLOG.md`
- Sprint Plan: `.agile-v/sprints/C1/SPRINT_PLAN_C1.md`
- Engineering guide: `ENGINEERING_GUIDE.md` (if present)

## Selected Backlog Item

## BL-0004: Workspace Creation
**Type:** Feature · **Priority:** CRITICAL · **REQ:** REQ-0004, REQ-0022
**Story:** As an authenticated user, I want to create a workspace so that I can organize projects with my team.
**Acceptance:**
1. `POST /workspaces` creates a workspace and sets the creator as the first admin.
2. Created workspace appears in the creator's workspace list with role `admin`.
3. Workspace is private to its members (non-members cannot see it).
**Effort:** 3 · **Dependencies:** BL-0002 · **Status:** Ready


## Related Requirements

## REQ-0004 Workspace Creation

- **Requirement:** An authenticated user can create a workspace.
- **Constraint:** The creator becomes the workspace's first admin.
- **Verification Criteria:** Created workspace appears in the creator's workspace list with admin role.
- **Done Criteria:** Workspace is private to its members.

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
