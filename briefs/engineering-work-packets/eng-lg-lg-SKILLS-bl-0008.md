# Engineering Work Packet: BL-0008

## Run

- Run ID: `eng-lg-lg-SKILLS-bl-0008`
- Engineering Skill: `lg-SKILLS`
- Target Repo: `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/target-repos/lg-graph-test`
- Baseline Commit: `4ccbc83f425ca700b1c98728769185518854fcbf`
- Backlog Item: `BL-0008`

## Source Context

- Requirements: `REQUIREMENTS.md`
- Backlog: `.agile-v/BACKLOG.md`
- Sprint Plan: `.agile-v/sprints/C1/SPRINT_PLAN_C1.md`
- Engineering guide: `ENGINEERING_GUIDE.md` (if present)

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


## Related Requirements

(no REQ excerpts available)

## In Scope

Implement only the behavior in this BL item's Acceptance section. Stay within the BL's stated REQ references.

## Out Of Scope

- Anything from other backlog items.
- Refactors, dependency bumps, or hygiene changes not required to deliver this slice.
- Running or fixing `verify_blNNNN.py` for any BL other than this one. Cross-BL regression coverage is the QA role's responsibility, not engineering's. If a prior-BL verifier appears broken due to environment/tooling noise, IGNORE it — do not modify it, do not investigate it. Your only verifier is `verify_bl0008.py` for this BL.

## Expected Artifacts

- Updated source files in the target repo.
- New or updated tests under `tests/`.
- A `verify_bl0008.py` BL-specific sanity checker at the repo root.
- Updated `scripts/full_http_smoke.py` (if it exists, extend its coverage for this BL).

## Verification Commands

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl0008.py
.venv/bin/python scripts/full_http_smoke.py
```

Run these inside the target repo. All must pass before you declare the cycle complete.

## Done Criteria

- Every Acceptance criterion in the BL block above is covered by at least one test.
- All verification commands exit zero.
- The target repo is on a new commit that begins with `Implement BL-0008`.
- No file in `REQUIREMENTS.md`, `.agile-v/BACKLOG.md`, or `.agile-v/sprints/C1/SPRINT_PLAN_C1.md` has been modified.
