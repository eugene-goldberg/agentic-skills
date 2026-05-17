# QA Work Packet: BL-0009

## Run

- Run ID: `qa-lg-lg-SKILLS-bl-0009`
- Target Repo: `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/target-repos/lg-graph-test`
- Target Commit: `52f5c4a9112c7696ca7da3d92ff64c10cc2b55bb` (engineering closing commit for BL-0009)
- Engineering Run: `eng-lg-lg-SKILLS-bl-0009`
- Engineering BL Under Test: `BL-0009`
- Carry-Forward Suite: `qa-lg-lg-SKILLS-bl-0008` (copied into `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0009/journey_suite/`)

## Selected Backlog Item

## BL-0009: Task CRUD within Project
**Type:** Feature · **Priority:** HIGH · **REQ:** REQ-0007, REQ-0009
**Story:** As a workspace Member or Owner, I want to create, read, update, and delete tasks within a project so that I can track work items.
**Acceptance:**
1. `POST /workspaces/{id}/projects/{project_id}/tasks` creates a task; title is required (missing → 422).
2. `GET .../tasks` and `GET .../tasks/{task_id}` read tasks.
3. `PATCH .../tasks/{task_id}` updates a task.
4. `DELETE .../tasks/{task_id}` deletes a task.
5. Task status defaults to `todo`; allowed values are `todo`, `in_progress`, `done`; invalid → 422.
6. Non-member on any task endpoint → 404.
7. Unauthenticated → 401.
**Effort:** 3 · **Dependencies:** BL-0008 · **Status:** Ready

---


## Mandatory Inputs

Run inside the target repo at commit `52f5c4a9112c7696ca7da3d92ff64c10cc2b55bb`. Capture exit code + verbatim stdout for each:

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl0009.py
.venv/bin/python scripts/full_http_smoke.py
```

Plus any earlier-BL verifier present at this commit (e.g. `verify_bl0001.py`, etc.).

## Journey suite

Lives at `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0009/journey_suite/`. Already contains the prior cycle's suite — extend it in place. Requirements:

- Use subprocess Uvicorn + real HTTP + fresh tmp SQLite per scenario. Do NOT use `TestClient(app)`.
- Authenticate via real `/signup` and `/login`.
- Cover the BL acceptance criteria with multi-step flows; add adversarial scenarios for the role × HTTP matrix, existence-leak parity, and concurrency where applicable.
- Top-level entry: `run.py`. Emit `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0009/journey_results.json` with per-scenario pass/fail.
- Exit non-zero on any unknown failure. Known-bug failures (carried forward from prior cycles) can be annotated with a `known_bug_id` field and excluded from the exit code.
- All prior-BL scenarios must continue to pass against this commit, except those marked `known_bug_id`. Any new regression is a finding.

## Deliverables

Under `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0009/`:

- `engineer_stack_results.txt`
- `gap_audit.md`
- `journey_suite/` (full implementation)
- `journey_results.json`
- `bug_report.md`
- `raw_logs/invocation.md`
- `metadata.yaml`

## Scope rules

- Do NOT modify any engineer-authored artifact in the target repo. You report findings; engineering fixes.
- Do NOT advance the target repo past `52f5c4a9112c7696ca7da3d92ff64c10cc2b55bb`. Use `git checkout 52f5c4a9112c7696ca7da3d92ff64c10cc2b55bb` if needed and restore the prior HEAD when done.
- Do NOT use `TestClient(app)` in your journey suite.
- Do NOT skip the engineer-authored verification stack.

## Final report

Return an assistant message (no tool calls) summarizing: engineer stack pass/fail per command, journey suite total/pass/fail with known-bug call-out, bug count by severity, top finding, and any decisions on ambiguous points.
