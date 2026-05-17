# Engineering Work Packet: BL-0010

## Run

- Run ID: `eng-lg-lg-SKILLS-bl-0010`
- Engineering Skill: `lg-SKILLS`
- Target Repo: `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/target-repos/lg-graph-test`
- Baseline Commit: `52f5c4a9112c7696ca7da3d92ff64c10cc2b55bb`
- Backlog Item: `BL-0010`

## Source Context

- Requirements: `REQUIREMENTS.md`
- Backlog: `.agile-v/BACKLOG.md`
- Sprint Plan: `.agile-v/sprints/C1/SPRINT_PLAN_C1.md`
- Engineering guide: `ENGINEERING_GUIDE.md` (if present)

## Selected Backlog Item

## BL-0010: Task Assignment
**Type:** Feature · **Priority:** HIGH · **REQ:** REQ-0008
**Story:** As a workspace Member or Owner, I want to assign tasks to workspace members (or clear the assignee) so that responsibility is clear.
**Acceptance:**
1. Task create/update accepts an `assignee_id`.
2. Assignee must be a member of the workspace; otherwise → 404 (privacy: do not leak existence).
3. Setting `assignee_id` to `null` clears the assignee.
4. Non-member on task endpoints → 404.
**Effort:** 2 · **Dependencies:** BL-0009 · **Status:** Ready

---


## Related Requirements

(no REQ excerpts available)

## In Scope

Implement only the behavior in this BL item's Acceptance section. Stay within the BL's stated REQ references.

## Out Of Scope

- Anything from other backlog items.
- Refactors, dependency bumps, or hygiene changes not required to deliver this slice.
- Running or fixing `verify_blNNNN.py` for any BL other than this one. Cross-BL regression coverage is the QA role's responsibility, not engineering's. If a prior-BL verifier appears broken due to environment/tooling noise, IGNORE it — do not modify it, do not investigate it. Your only verifier is `verify_bl0010.py` for this BL.

## Expected Artifacts

- Updated source files in the target repo.
- New or updated tests under `tests/`.
- A `verify_bl0010.py` BL-specific sanity checker at the repo root.
- Updated `scripts/full_http_smoke.py` (if it exists, extend its coverage for this BL).

## Verification Commands

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl0010.py
.venv/bin/python scripts/full_http_smoke.py
```

Run these inside the target repo. All must pass before you declare the cycle complete.

## Done Criteria

- Every Acceptance criterion in the BL block above is covered by at least one test.
- All verification commands exit zero.
- The target repo is on a new commit that begins with `Implement BL-0010`.
- No file in `REQUIREMENTS.md`, `.agile-v/BACKLOG.md`, or `.agile-v/sprints/C1/SPRINT_PLAN_C1.md` has been modified.
