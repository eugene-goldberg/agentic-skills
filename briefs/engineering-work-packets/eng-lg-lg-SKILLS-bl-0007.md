# Engineering Work Packet: BL-0007

## Run

- Run ID: `eng-lg-lg-SKILLS-bl-0007`
- Engineering Skill: `lg-SKILLS`
- Target Repo: `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/target-repos/lg-graph-test`
- Baseline Commit: `666ad7c37e86bab5997901b26adc762d6a469075`
- Backlog Item: `BL-0007`

## Source Context

- Requirements: `REQUIREMENTS.md`
- Backlog: `.agile-v/BACKLOG.md`
- Sprint Plan: `.agile-v/sprints/C1/SPRINT_PLAN_C1.md`
- Engineering guide: `ENGINEERING_GUIDE.md` (if present)

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


## Related Requirements

(no REQ excerpts available)

## In Scope

Implement only the behavior in this BL item's Acceptance section. Stay within the BL's stated REQ references.

## Out Of Scope

- Anything from other backlog items.
- Refactors, dependency bumps, or hygiene changes not required to deliver this slice.
- Running or fixing `verify_blNNNN.py` for any BL other than this one. Cross-BL regression coverage is the QA role's responsibility, not engineering's. If a prior-BL verifier appears broken due to environment/tooling noise, IGNORE it — do not modify it, do not investigate it. Your only verifier is `verify_bl0007.py` for this BL.

## Expected Artifacts

- Updated source files in the target repo.
- New or updated tests under `tests/`.
- A `verify_bl0007.py` BL-specific sanity checker at the repo root.
- Updated `scripts/full_http_smoke.py` (if it exists, extend its coverage for this BL).

## Verification Commands

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl0007.py
.venv/bin/python scripts/full_http_smoke.py
```

Run these inside the target repo. All must pass before you declare the cycle complete.

## Done Criteria

- Every Acceptance criterion in the BL block above is covered by at least one test.
- All verification commands exit zero.
- The target repo is on a new commit that begins with `Implement BL-0007`.
- No file in `REQUIREMENTS.md`, `.agile-v/BACKLOG.md`, or `.agile-v/sprints/C1/SPRINT_PLAN_C1.md` has been modified.
