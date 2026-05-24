# QA Work Packet: BL-0002

## Run

- Run ID: `qa-lg-lg-SKILLS-bl-0002`
- Target Repo: `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/target-repos/lg-graph-test`
- Target Commit: `fe978ab7f5c383cf684419dd6cc34367033bf991` (engineering closing commit for BL-0002)
- Engineering Run: `eng-lg-lg-SKILLS-bl-0002`
- Engineering BL Under Test: `BL-0002`
- Carry-Forward Suite: `qa-lg-lg-SKILLS-bl-0001` (copied into `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0002/journey_suite/`)

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


## Mandatory Inputs

Run inside the target repo at commit `fe978ab7f5c383cf684419dd6cc34367033bf991`. Capture exit code + verbatim stdout for each:

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl0002.py
.venv/bin/python scripts/full_http_smoke.py
```

Plus any earlier-BL verifier present at this commit (e.g. `verify_bl0001.py`, etc.).

## Journey suite

Lives at `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0002/journey_suite/`. Already contains the prior cycle's suite — extend it in place. Requirements:

- Use subprocess Uvicorn + real HTTP + fresh tmp SQLite per scenario. Do NOT use `TestClient(app)`.
- Authenticate via real `/signup` and `/login`.
- Cover the BL acceptance criteria with multi-step flows; add adversarial scenarios for the role × HTTP matrix, existence-leak parity, and concurrency where applicable.
- Top-level entry: `run.py`. Emit `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0002/journey_results.json` with per-scenario pass/fail.
- Exit non-zero on any unknown failure. Known-bug failures (carried forward from prior cycles) can be annotated with a `known_bug_id` field and excluded from the exit code.
- All prior-BL scenarios must continue to pass against this commit, except those marked `known_bug_id`. Any new regression is a finding.

## Deliverables

Under `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0002/`:

- `engineer_stack_results.txt`
- `gap_audit.md`
- `journey_suite/` (full implementation)
- `journey_results.json`
- `bug_report.md`
- `raw_logs/invocation.md`
- `metadata.yaml`

## Scope rules

- Do NOT modify any engineer-authored artifact in the target repo. You report findings; engineering fixes.
- Do NOT advance the target repo past `fe978ab7f5c383cf684419dd6cc34367033bf991`. Use `git checkout fe978ab7f5c383cf684419dd6cc34367033bf991` if needed and restore the prior HEAD when done.
- Do NOT use `TestClient(app)` in your journey suite.
- Do NOT skip the engineer-authored verification stack.

## Final report

Return an assistant message (no tool calls) summarizing: engineer stack pass/fail per command, journey suite total/pass/fail with known-bug call-out, bug count by severity, top finding, and any decisions on ambiguous points.
