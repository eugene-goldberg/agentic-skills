# QA Work Packet: BL-0005

## Run

- Run ID: `qa-lg-lg-SKILLS-bl-0005`
- Target Repo: `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/target-repos/lg-graph-test`
- Target Commit: `38d0890ee67e75d136a1926b1413ab69f67ead2d` (engineering closing commit for BL-0005)
- Engineering Run: `eng-lg-lg-SKILLS-bl-0005`
- Engineering BL Under Test: `BL-0005`
- Carry-Forward Suite: `qa-lg-lg-SKILLS-bl-0004` (copied into `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0005/journey_suite/`)

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


## Mandatory Inputs

Run inside the target repo at commit `38d0890ee67e75d136a1926b1413ab69f67ead2d`. Capture exit code + verbatim stdout for each:

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl0005.py
.venv/bin/python scripts/full_http_smoke.py
```

Plus any earlier-BL verifier present at this commit (e.g. `verify_bl0001.py`, etc.).

## Journey suite

Lives at `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0005/journey_suite/`. Already contains the prior cycle's suite — extend it in place. Requirements:

- Use subprocess Uvicorn + real HTTP + fresh tmp SQLite per scenario. Do NOT use `TestClient(app)`.
- Authenticate via real `/signup` and `/login`.
- Cover the BL acceptance criteria with multi-step flows; add adversarial scenarios for the role × HTTP matrix, existence-leak parity, and concurrency where applicable.
- Top-level entry: `run.py`. Emit `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0005/journey_results.json` with per-scenario pass/fail.
- Exit non-zero on any unknown failure. Known-bug failures (carried forward from prior cycles) can be annotated with a `known_bug_id` field and excluded from the exit code.
- All prior-BL scenarios must continue to pass against this commit, except those marked `known_bug_id`. Any new regression is a finding.

## Deliverables

Under `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0005/`:

- `engineer_stack_results.txt`
- `gap_audit.md`
- `journey_suite/` (full implementation)
- `journey_results.json`
- `bug_report.md`
- `raw_logs/invocation.md`
- `metadata.yaml`

## Scope rules

- Do NOT modify any engineer-authored artifact in the target repo. You report findings; engineering fixes.
- Do NOT advance the target repo past `38d0890ee67e75d136a1926b1413ab69f67ead2d`. Use `git checkout 38d0890ee67e75d136a1926b1413ab69f67ead2d` if needed and restore the prior HEAD when done.
- Do NOT use `TestClient(app)` in your journey suite.
- Do NOT skip the engineer-authored verification stack.

## Final report

Return an assistant message (no tool calls) summarizing: engineer stack pass/fail per command, journey suite total/pass/fail with known-bug call-out, bug count by severity, top finding, and any decisions on ambiguous points.
