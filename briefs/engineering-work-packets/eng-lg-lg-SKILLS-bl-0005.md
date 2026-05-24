# Engineering Work Packet: BL-0005

## Run

- Run ID: `eng-lg-lg-SKILLS-bl-0005`
- Engineering Skill: `lg-SKILLS`
- Target Repo: `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/target-repos/lg-graph-test`
- Baseline Commit: `2f21f8a6a6b0607f256906aee7121ee18d164a27`
- Backlog Item: `BL-0005`

## Source Context

- Requirements: `REQUIREMENTS.md`
- Backlog: `.agile-v/BACKLOG.md`
- Sprint Plan: `.agile-v/sprints/C1/SPRINT_PLAN_C1.md`
- Engineering guide: `ENGINEERING_GUIDE.md` (if present)

## Selected Backlog Item

## BL-0005: Workspace Listing and Detail
**Type:** Feature · **Priority:** CRITICAL · **REQ:** REQ-0008, REQ-0020, REQ-0022
**Story:** As a workspace member, I want to list my workspaces and view a specific workspace so that I can navigate my teams.
**Acceptance:**
1. `GET /workspaces` lists only workspaces the caller belongs to.
2. `GET /workspaces/{ws_id}` returns workspace details for members.
3. Non-member requests to either endpoint return `404` (not `403`).
4. No workspace data leaks to non-members.
**Effort:** 3 · **Dependencies:** BL-0004 · **Status:** Ready


## Related Requirements

## REQ-0008 Workspace Listing And Detail

- **Requirement:** A user can list and retrieve only workspaces they belong to.
- **Constraint:** Non-members see nothing from the workspace.
- **Verification Criteria:** `GET /workspaces` lists only the caller's memberships; `GET /workspaces/{ws_id}` returns `404` to non-members.
- **Done Criteria:** No workspace data leaks to non-members.

## REQ-0020 Cross-Tenant Privacy

- **Requirement:** A non-member sees no workspace, project, task, comment, assignment, or summary data from a workspace.
- **Constraint:** Workspace-scoped paths return `404` to non-members, not `403`.
- **Verification Criteria:** Cross-user attempts against workspace, project, task, comment, `/me/tasks`, and summary surfaces reveal no data.
- **Done Criteria:** Privacy behavior is consistent across all endpoints.

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
- Running or fixing `verify_blNNNN.py` for any BL other than this one. Cross-BL regression coverage is the QA role's responsibility, not engineering's. If a prior-BL verifier appears broken due to environment/tooling noise, IGNORE it — do not modify it, do not investigate it. Your only verifier is `verify_bl0005.py` for this BL.

## Expected Artifacts

- Updated source files in the target repo.
- New or updated tests under `tests/`.
- A `verify_bl0005.py` BL-specific sanity checker at the repo root.
- Updated `scripts/full_http_smoke.py` (if it exists, extend its coverage for this BL).

## Verification Commands

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl0005.py
.venv/bin/python scripts/full_http_smoke.py
```

Run these inside the target repo. All must pass before you declare the cycle complete.

## Done Criteria

- Every Acceptance criterion in the BL block above is covered by at least one test.
- All verification commands exit zero.
- The target repo is on a new commit that begins with `Implement BL-0005`.
- No file in `REQUIREMENTS.md`, `.agile-v/BACKLOG.md`, or `.agile-v/sprints/C1/SPRINT_PLAN_C1.md` has been modified.
