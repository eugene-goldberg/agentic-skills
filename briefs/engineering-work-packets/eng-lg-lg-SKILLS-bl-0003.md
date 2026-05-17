# Engineering Work Packet: BL-0003

## Run

- Run ID: `eng-lg-lg-SKILLS-bl-0003`
- Engineering Skill: `lg-SKILLS`
- Target Repo: `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/target-repos/lg-graph-test`
- Baseline Commit: `a1bdd317e7c5a8d55ecec1d5fec4c7d707d2220e`
- Backlog Item: `BL-0003`

## Source Context

- Requirements: `REQUIREMENTS.md`
- Backlog: `.agile-v/BACKLOG.md`
- Sprint Plan: `.agile-v/sprints/C1/SPRINT_PLAN_C1.md`
- Engineering guide: `ENGINEERING_GUIDE.md` (if present)

## Selected Backlog Item

## BL-0003: JWT Authentication and Login
**Type:** Feature · **Priority:** CRITICAL · **REQ:** REQ-0001
**Story:** As a registered user, I want to log in and receive a JWT access token so that I can access protected endpoints.
**Acceptance:**
1. `POST /auth/login` returns a JWT with `sub` claim on valid credentials.
2. Invalid credentials return HTTP 401.
3. Protected endpoints reject missing/invalid tokens with HTTP 401.
4. Token expiration is enforced (configurable).
**Effort:** 2 · **Dependencies:** BL-0002 · **Status:** Ready

---


## Related Requirements

(no REQ excerpts available)

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
