# Engineering Work Packet: BL-0002

## Run

- Run ID: `eng-lg-lg-SKILLS-bl-0002`
- Engineering Skill: `lg-SKILLS`
- Target Repo: `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/target-repos/lg-graph-test`
- Baseline Commit: `3a6147257ace6c1dfd9d62804f42e9b3cc2a3ef3`
- Backlog Item: `BL-0002`

## Source Context

- Requirements: `REQUIREMENTS.md`
- Backlog: `.agile-v/BACKLOG.md`
- Sprint Plan: `.agile-v/sprints/C1/SPRINT_PLAN_C1.md`
- Engineering guide: `ENGINEERING_GUIDE.md` (if present)

## Selected Backlog Item

## BL-0002: Authentication Signup and Login
**Type:** Feature · **Priority:** CRITICAL · **REQ:** REQ-0001, REQ-0002, REQ-0022
**Story:** As a user, I want to sign up with email and password and log in to receive a bearer token so that I can access protected resources.
**Acceptance:**
1. `POST /auth/signup` creates a user with hashed password; duplicate email returns `400` or `409`.
2. `POST /auth/login` returns a bearer token for valid credentials and `401` for invalid credentials.
3. Password is never returned in any API response.
4. Protected endpoints reject missing or invalid tokens with `401`.
**Effort:** 5 · **Dependencies:** BL-0001 · **Status:** Ready


## Related Requirements

## REQ-0001 Authentication Signup

- **Requirement:** A user can sign up with a unique email and password.
- **Constraint:** Email must be unique. Passwords must be stored only as hashes.
- **Verification Criteria:** Creating a new account returns a user without password fields and enables authenticated access.
- **Done Criteria:** Duplicate email is rejected; password is never returned by any API response.

## REQ-0002 Authentication Login

- **Requirement:** A user can log in with valid credentials and receive a bearer token.
- **Constraint:** Invalid credentials return `401`.
- **Verification Criteria:** Valid credentials return a token; invalid credentials do not.
- **Done Criteria:** Token can be used on protected routes.

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
- Running or fixing `verify_blNNNN.py` for any BL other than this one. Cross-BL regression coverage is the QA role's responsibility, not engineering's. If a prior-BL verifier appears broken due to environment/tooling noise, IGNORE it — do not modify it, do not investigate it. Your only verifier is `verify_bl0002.py` for this BL.

## Expected Artifacts

- Updated source files in the target repo.
- New or updated tests under `tests/`.
- A `verify_bl0002.py` BL-specific sanity checker at the repo root.
- Updated `scripts/full_http_smoke.py` (if it exists, extend its coverage for this BL).

## Verification Commands

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl0002.py
.venv/bin/python scripts/full_http_smoke.py
```

Run these inside the target repo. All must pass before you declare the cycle complete.

## Done Criteria

- Every Acceptance criterion in the BL block above is covered by at least one test.
- All verification commands exit zero.
- The target repo is on a new commit that begins with `Implement BL-0002`.
- No file in `REQUIREMENTS.md`, `.agile-v/BACKLOG.md`, or `.agile-v/sprints/C1/SPRINT_PLAN_C1.md` has been modified.
