# QA Work Packet: BL-0001

## Run

- Run ID: `qa-lg-lg-SKILLS-bl-0001`
- Target Repo: `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/target-repos/lg-graph-test`
- Target Commit: `3a6147257ace6c1dfd9d62804f42e9b3cc2a3ef3` (engineering closing commit for BL-0001)
- Engineering Run: `eng-lg-lg-SKILLS-bl-0001`
- Engineering BL Under Test: `BL-0001`
- Carry-Forward Suite: none (first QA cycle)

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


## Mandatory Inputs

Run inside the target repo at commit `3a6147257ace6c1dfd9d62804f42e9b3cc2a3ef3`. Capture exit code + verbatim stdout for each:

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl0001.py
.venv/bin/python scripts/full_http_smoke.py
```

Plus any earlier-BL verifier present at this commit (e.g. `verify_bl0001.py`, etc.).

## Journey suite

Lives at `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0001/journey_suite/`. Author it fresh in this cycle. Requirements:

- Use subprocess Uvicorn + real HTTP + fresh tmp SQLite per scenario. Do NOT use `TestClient(app)`.
- Authenticate via real `/signup` and `/login`.
- Cover the BL acceptance criteria with multi-step flows; add adversarial scenarios for the role × HTTP matrix, existence-leak parity, and concurrency where applicable.
- Top-level entry: `run.py`. Emit `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0001/journey_results.json` with per-scenario pass/fail.
- Exit non-zero on any unknown failure. Known-bug failures (carried forward from prior cycles) can be annotated with a `known_bug_id` field and excluded from the exit code.
- All prior-BL scenarios must continue to pass against this commit, except those marked `known_bug_id`. Any new regression is a finding.

## Deliverables

Under `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0001/`:

- `engineer_stack_results.txt`
- `gap_audit.md`
- `journey_suite/` (full implementation)
- `journey_results.json`
- `bug_report.md`
- `raw_logs/invocation.md`
- `metadata.yaml`

## Scope rules

- Do NOT modify any engineer-authored artifact in the target repo. You report findings; engineering fixes.
- Do NOT advance the target repo past `3a6147257ace6c1dfd9d62804f42e9b3cc2a3ef3`. Use `git checkout 3a6147257ace6c1dfd9d62804f42e9b3cc2a3ef3` if needed and restore the prior HEAD when done.
- Do NOT use `TestClient(app)` in your journey suite.
- Do NOT skip the engineer-authored verification stack.

## Final report

Return an assistant message (no tool calls) summarizing: engineer stack pass/fail per command, journey suite total/pass/fail with known-bug call-out, bug count by severity, top finding, and any decisions on ambiguous points.
