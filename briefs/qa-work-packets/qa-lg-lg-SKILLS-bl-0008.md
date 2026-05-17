# QA Work Packet: BL-0008

## Run

- Run ID: `qa-lg-lg-SKILLS-bl-0008`
- Target Repo: `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/target-repos/lg-graph-test`
- Target Commit: `798afb5d449719e80ed46017c9b5fc4b938a58fd` (engineering closing commit for BL-0008)
- Engineering Run: `eng-lg-lg-SKILLS-bl-0008`
- Engineering BL Under Test: `BL-0008`
- Carry-Forward Suite: `qa-lg-lg-SKILLS-bl-0007` (copied into `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0008/journey_suite/`)

## Selected Backlog Item

## BL-0008: Project CRUD within Workspace
**Type:** Feature · **Priority:** HIGH · **REQ:** REQ-0006
**Story:** As a workspace Member or Owner, I want to create, read, update, and delete projects within my workspace so that I can organize work.
**Acceptance:**
1. `POST /workspaces/{id}/projects` creates a project; name must be unique within the workspace (duplicate → 409).
2. `GET /workspaces/{id}/projects` lists projects in the workspace.
3. `GET /workspaces/{id}/projects/{project_id}` returns a project.
4. `PATCH /workspaces/{id}/projects/{project_id}` updates a project.
5. `DELETE /workspaces/{id}/projects/{project_id}` deletes a project.
6. Non-member accessing any project endpoint → 404 (not 403).
7. Unauthenticated → 401.
**Effort:** 3 · **Dependencies:** BL-0005 · **Status:** Ready

---


## Mandatory Inputs

Run inside the target repo at commit `798afb5d449719e80ed46017c9b5fc4b938a58fd`. Capture exit code + verbatim stdout for each:

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl0008.py
.venv/bin/python scripts/full_http_smoke.py
```

Plus any earlier-BL verifier present at this commit (e.g. `verify_bl0001.py`, etc.).

## Journey suite

Lives at `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0008/journey_suite/`. Already contains the prior cycle's suite — extend it in place. Requirements:

- Use subprocess Uvicorn + real HTTP + fresh tmp SQLite per scenario. Do NOT use `TestClient(app)`.
- Authenticate via real `/signup` and `/login`.
- Cover the BL acceptance criteria with multi-step flows; add adversarial scenarios for the role × HTTP matrix, existence-leak parity, and concurrency where applicable.
- Top-level entry: `run.py`. Emit `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0008/journey_results.json` with per-scenario pass/fail.
- Exit non-zero on any unknown failure. Known-bug failures (carried forward from prior cycles) can be annotated with a `known_bug_id` field and excluded from the exit code.
- All prior-BL scenarios must continue to pass against this commit, except those marked `known_bug_id`. Any new regression is a finding.

## Deliverables

Under `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0008/`:

- `engineer_stack_results.txt`
- `gap_audit.md`
- `journey_suite/` (full implementation)
- `journey_results.json`
- `bug_report.md`
- `raw_logs/invocation.md`
- `metadata.yaml`

## Scope rules

- Do NOT modify any engineer-authored artifact in the target repo. You report findings; engineering fixes.
- Do NOT advance the target repo past `798afb5d449719e80ed46017c9b5fc4b938a58fd`. Use `git checkout 798afb5d449719e80ed46017c9b5fc4b938a58fd` if needed and restore the prior HEAD when done.
- Do NOT use `TestClient(app)` in your journey suite.
- Do NOT skip the engineer-authored verification stack.

## Final report

Return an assistant message (no tool calls) summarizing: engineer stack pass/fail per command, journey suite total/pass/fail with known-bug call-out, bug count by severity, top finding, and any decisions on ambiguous points.
