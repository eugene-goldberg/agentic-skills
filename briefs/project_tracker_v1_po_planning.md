# Project Tracker v1 PO Planning Brief

## Role Under Test

Product Owner.

## Assignment

Use the approved requirements in the target repository's `REQUIREMENTS.md` to produce delivery-planning artifacts for Project Tracker v1.

The product is a standalone FastAPI service for tracking projects and tasks across private team workspaces. Workspaces contain projects, projects contain tasks, tasks have comments and assignees. The requirements are already approved for this planning exercise.

## Expected Output Artifacts

Create only these files:

- `.agile-v/BACKLOG.md`
- `.agile-v/sprints/C1/SPRINT_PLAN_C1.md`

Do not create implementation code. Do not create tests. Do not create sprint review, retrospective, release, or compliance artifacts for this run. This is a planning-only PO evaluation.

## Planning Rules

- Every backlog item must map to one or more `REQ-XXXX` identifiers from `REQUIREMENTS.md`.
- Every requirement in `REQUIREMENTS.md` must be covered by at least one backlog item.
- Backlog items must be written as user stories or technical-enabler stories with clear acceptance criteria.
- Acceptance criteria must be testable and must preserve the security, privacy, cascade, role, and cross-tenant isolation requirements.
- Identify dependencies, priority, and estimated effort for each backlog item.
- Split work into a realistic first cycle sprint plan.
- Use conservative capacity assumptions if no team capacity is provided.
- Preserve the explicit 404 versus 403 privacy semantics in planning and acceptance criteria.
- Preserve the assignee-clearing behavior when a member is removed from a workspace.
- Preserve `/me/tasks` as strictly "my assigned tasks", not "tasks I can see".

## Success Criteria

The output is successful when:

- `BACKLOG.md` exists and has complete `REQ-XXXX` traceability.
- `SPRINT_PLAN_C1.md` exists and commits a coherent subset of backlog items.
- No backlog item lacks a requirement mapping.
- No requirement is omitted.
- High-risk privacy and authorization rules are visible in acceptance criteria.
- The output stays inside the requested planning scope.
