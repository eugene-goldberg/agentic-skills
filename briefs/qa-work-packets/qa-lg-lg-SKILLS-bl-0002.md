# QA Work Packet: BL-0002

## Run

- Run ID: `qa-lg-lg-SKILLS-bl-0002`
- Target Repo: `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/target-repos/lg-graph-test`
- Target Commit: `a1bdd317e7c5a8d55ecec1d5fec4c7d707d2220e` (engineering closing commit for BL-0002)
- Engineering Run: `eng-lg-lg-SKILLS-bl-0002`
- Engineering BL Under Test: `BL-0002`
- Carry-Forward Suite: `qa-lg-lg-SKILLS-bl-0001` (copied into `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0002/journey_suite/`)

## Selected Backlog Item

## BL-0002: User Registration Endpoint
**Type:** Feature · **Priority:** CRITICAL · **REQ:** REQ-0002
**Story:** As a new user, I want to register with a unique username and password so that I can later authenticate and use the system.
**Acceptance:**
1. `POST /auth/register` accepts `{username, password}` and creates a user.
2. Password is hashed before persistence (e.g., bcrypt).
3. Duplicate username returns HTTP 409.
4. Response does not include the password hash.
**Effort:** 2 · **Dependencies:** BL-0001 · **Status:** Ready

---


## Mandatory Inputs

Run inside the target repo at commit `a1bdd317e7c5a8d55ecec1d5fec4c7d707d2220e`. Capture exit code + verbatim stdout for each:

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
- Do NOT advance the target repo past `a1bdd317e7c5a8d55ecec1d5fec4c7d707d2220e`. Use `git checkout a1bdd317e7c5a8d55ecec1d5fec4c7d707d2220e` if needed and restore the prior HEAD when done.
- Do NOT use `TestClient(app)` in your journey suite.
- Do NOT skip the engineer-authored verification stack.

## Final report

Return an assistant message (no tool calls) summarizing: engineer stack pass/fail per command, journey suite total/pass/fail with known-bug call-out, bug count by severity, top finding, and any decisions on ambiguous points.
