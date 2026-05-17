# QA Work Packet: BL-0007

## Run

- Run ID: `qa-lg-lg-SKILLS-bl-0007`
- Target Repo: `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/target-repos/lg-graph-test`
- Target Commit: `4ccbc83f425ca700b1c98728769185518854fcbf` (engineering closing commit for BL-0007)
- Engineering Run: `eng-lg-lg-SKILLS-bl-0007`
- Engineering BL Under Test: `BL-0007`
- Carry-Forward Suite: `qa-lg-lg-SKILLS-bl-0006` (copied into `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0007/journey_suite/`)

## Selected Backlog Item

## BL-0007: Workspace Membership Invite and Remove
**Type:** Feature · **Priority:** CRITICAL · **REQ:** REQ-0004, REQ-0013
**Story:** As a workspace Owner, I want to invite and remove members so that I can control who has access to my workspace.
**Acceptance:**
1. `POST /workspaces/{id}/members` invites an existing user by username; invited user becomes Member.
2. `DELETE /workspaces/{id}/members/{user_id}` removes a member.
3. Only Owners may invite or remove; non-owners → 403.
4. Inviting a non-existent user → 404.
5. Removing a non-member → 404.
6. Duplicate invite of an existing member → 409.
7. On member removal, all tasks assigned to that user within the workspace have assignee cleared (set to null).
8. Tasks in other workspaces are unaffected.
**Effort:** 3 · **Dependencies:** BL-0005 · **Status:** Ready

---


## Mandatory Inputs

Run inside the target repo at commit `4ccbc83f425ca700b1c98728769185518854fcbf`. Capture exit code + verbatim stdout for each:

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl0007.py
.venv/bin/python scripts/full_http_smoke.py
```

Plus any earlier-BL verifier present at this commit (e.g. `verify_bl0001.py`, etc.).

## Journey suite

Lives at `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0007/journey_suite/`. Already contains the prior cycle's suite — extend it in place. Requirements:

- Use subprocess Uvicorn + real HTTP + fresh tmp SQLite per scenario. Do NOT use `TestClient(app)`.
- Authenticate via real `/signup` and `/login`.
- Cover the BL acceptance criteria with multi-step flows; add adversarial scenarios for the role × HTTP matrix, existence-leak parity, and concurrency where applicable.
- Top-level entry: `run.py`. Emit `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0007/journey_results.json` with per-scenario pass/fail.
- Exit non-zero on any unknown failure. Known-bug failures (carried forward from prior cycles) can be annotated with a `known_bug_id` field and excluded from the exit code.
- All prior-BL scenarios must continue to pass against this commit, except those marked `known_bug_id`. Any new regression is a finding.

## Deliverables

Under `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/runs/qa-lg-lg-SKILLS-bl-0007/`:

- `engineer_stack_results.txt`
- `gap_audit.md`
- `journey_suite/` (full implementation)
- `journey_results.json`
- `bug_report.md`
- `raw_logs/invocation.md`
- `metadata.yaml`

## Scope rules

- Do NOT modify any engineer-authored artifact in the target repo. You report findings; engineering fixes.
- Do NOT advance the target repo past `4ccbc83f425ca700b1c98728769185518854fcbf`. Use `git checkout 4ccbc83f425ca700b1c98728769185518854fcbf` if needed and restore the prior HEAD when done.
- Do NOT use `TestClient(app)` in your journey suite.
- Do NOT skip the engineer-authored verification stack.

## Final report

Return an assistant message (no tool calls) summarizing: engineer stack pass/fail per command, journey suite total/pass/fail with known-bug call-out, bug count by severity, top finding, and any decisions on ambiguous points.
