# Engineering Work Packet: BL-0003

## Run

- Run ID: `eng-lg-lg-SKILLS-bl-0003`
- Engineering Skill: `lg-SKILLS`
- Target Repo: `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/target-repos/lg-graph-test`
- Baseline Commit: `fe978ab7f5c383cf684419dd6cc34367033bf991`
- Backlog Item: `BL-0003`

## Source Context

- Requirements: `REQUIREMENTS.md`
- Backlog: `.agile-v/BACKLOG.md`
- Sprint Plan: `.agile-v/sprints/C1/SPRINT_PLAN_C1.md`
- Engineering guide: `ENGINEERING_GUIDE.md` (if present)

## Selected Backlog Item

## BL-0003: Current User Endpoint
**Type:** Feature · **Priority:** CRITICAL · **REQ:** REQ-0003, REQ-0022
**Story:** As an authenticated user, I want to call `GET /me` so that I can see my own account details.
**Acceptance:**
1. `GET /me` returns the current user's email and id without password fields.
2. Missing or invalid bearer token returns `401`.
3. Response shape is consistent with the user model schema.
**Effort:** 2 · **Dependencies:** BL-0002 · **Status:** Ready


## Related Requirements

## REQ-0003 Current User

- **Requirement:** An authenticated user can call `GET /me` to see their own account.
- **Constraint:** Missing or invalid bearer token returns `401`.
- **Verification Criteria:** `/me` returns only the current user and no password fields.
- **Done Criteria:** Unauthenticated requests fail.

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
- Running or fixing `verify_blNNNN.py` for any BL other than this one. Cross-BL regression coverage is the QA role's responsibility, not engineering's. If a prior-BL verifier appears broken due to environment/tooling noise, IGNORE it — do not modify it, do not investigate it. Your only verifier is `verify_bl0003.py` for this BL.

## Expected Artifacts

- Updated source files in the target repo.
- New or updated tests under `tests/`.
- A `verify_bl0003.py` BL-specific sanity checker at the repo root.
- Updated `scripts/full_http_smoke.py` (if it exists, extend its coverage for this BL).

## Verification Commands

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl0003.py
.venv/bin/python scripts/full_http_smoke.py
```

Run these inside the target repo. All must pass before you declare the cycle complete.

## Done Criteria

- Every Acceptance criterion in the BL block above is covered by at least one test.
- All verification commands exit zero.
- The target repo is on a new commit that begins with `Implement BL-0003`.
- No file in `REQUIREMENTS.md`, `.agile-v/BACKLOG.md`, or `.agile-v/sprints/C1/SPRINT_PLAN_C1.md` has been modified.
