# QA Work Packet: BL-0004

## Run

- Run ID: `qa-lg-lg-SKILLS-bl-0004`
- Target Repo: `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/target-repos/lg-graph-test`
- Target Commit: `f027ccd3d2b976c7cb42718fd3af8f77335998d2` (engineering closing commit for BL-0004)
- Engineering Run: `eng-lg-lg-SKILLS-bl-0004`
- Engineering BL Under Test: `BL-0004`
- Carry-Forward Suite: `qa-lg-lg-SKILLS-bl-0003` (copied into `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0004/journey_suite/`)

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


## Mandatory Inputs

Run inside the target repo at commit `f027ccd3d2b976c7cb42718fd3af8f77335998d2`. Capture exit code + verbatim stdout for each:

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl0004.py
.venv/bin/python scripts/full_http_smoke.py
```

Plus any earlier-BL verifier present at this commit (e.g. `verify_bl0001.py`, etc.).

## Journey suite

Lives at `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0004/journey_suite/`. Already contains the prior cycle's suite — extend it in place. Requirements:

- Use subprocess Uvicorn + real HTTP + fresh tmp SQLite per scenario. Do NOT use `TestClient(app)`.
- Authenticate via real `/signup` and `/login`.
- Cover the BL acceptance criteria with multi-step flows; add adversarial scenarios for the role × HTTP matrix, existence-leak parity, and concurrency where applicable.
- Top-level entry: `run.py`. Emit `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0004/journey_results.json` with per-scenario pass/fail.
- Exit non-zero on any unknown failure. Known-bug failures (carried forward from prior cycles) can be annotated with a `known_bug_id` field and excluded from the exit code.
- All prior-BL scenarios must continue to pass against this commit, except those marked `known_bug_id`. Any new regression is a finding.

## Deliverables

Under `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0004/`:

- `engineer_stack_results.txt`
- `gap_audit.md`
- `journey_suite/` (full implementation)
- `journey_results.json`
- `bug_report.md`
- `raw_logs/invocation.md`
- `metadata.yaml`

## Scope rules

- Do NOT modify any engineer-authored artifact in the target repo. You report findings; engineering fixes.
- Do NOT advance the target repo past `f027ccd3d2b976c7cb42718fd3af8f77335998d2`. Use `git checkout f027ccd3d2b976c7cb42718fd3af8f77335998d2` if needed and restore the prior HEAD when done.
- Do NOT use `TestClient(app)` in your journey suite.
- Do NOT skip the engineer-authored verification stack.

## Final report

Return an assistant message (no tool calls) summarizing: engineer stack pass/fail per command, journey suite total/pass/fail with known-bug call-out, bug count by severity, top finding, and any decisions on ambiguous points.
