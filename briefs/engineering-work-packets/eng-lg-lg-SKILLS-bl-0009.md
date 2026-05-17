# Engineering Work Packet: BL-0009

## Run

- Run ID: `eng-lg-lg-SKILLS-bl-0009`
- Engineering Skill: `lg-SKILLS`
- Target Repo: `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/target-repos/lg-graph-test`
- Baseline Commit: `798afb5d449719e80ed46017c9b5fc4b938a58fd`
- Backlog Item: `BL-0009`

## Source Context

- Requirements: `REQUIREMENTS.md`
- Backlog: `.agile-v/BACKLOG.md`
- Sprint Plan: `.agile-v/sprints/C1/SPRINT_PLAN_C1.md`
- Engineering guide: `ENGINEERING_GUIDE.md` (if present)

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


## Related Requirements

(no REQ excerpts available)

## In Scope

Implement only the behavior in this BL item's Acceptance section. Stay within the BL's stated REQ references.

## Out Of Scope

- Anything from other backlog items.
- Refactors, dependency bumps, or hygiene changes not required to deliver this slice.
- Running or fixing `verify_blNNNN.py` for any BL other than this one. Cross-BL regression coverage is the QA role's responsibility, not engineering's. If a prior-BL verifier appears broken due to environment/tooling noise, IGNORE it — do not modify it, do not investigate it. Your only verifier is `verify_bl0009.py` for this BL.

## Expected Artifacts

- Updated source files in the target repo.
- New or updated tests under `tests/`.
- A `verify_bl0009.py` BL-specific sanity checker at the repo root.
- Updated `scripts/full_http_smoke.py` (if it exists, extend its coverage for this BL).

## Verification Commands

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl0009.py
.venv/bin/python scripts/full_http_smoke.py
```

Run these inside the target repo. All must pass before you declare the cycle complete.

## Done Criteria

- Every Acceptance criterion in the BL block above is covered by at least one test.
- All verification commands exit zero.
- The target repo is on a new commit that begins with `Implement BL-0009`.
- No file in `REQUIREMENTS.md`, `.agile-v/BACKLOG.md`, or `.agile-v/sprints/C1/SPRINT_PLAN_C1.md` has been modified.
