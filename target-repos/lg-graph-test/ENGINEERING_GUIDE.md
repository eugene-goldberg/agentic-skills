# Engineering Guide

## Purpose
Project Tracker v1 is a standalone FastAPI service for private team workspaces containing projects, tasks, comments, and assignees. Build only against the backlog item currently being executed, preserving REQ traceability and private-workspace semantics.

## Expected project layout
Use a conventional FastAPI structure unless the repo already establishes one:
- `app/main.py` for FastAPI app wiring
- `app/routers/` for route modules (`auth`, `me`, `workspaces`, `projects`, `tasks`, optional `comments`)
- `app/models.py` or `app/models/` for ORM entities
- `app/schemas.py` or `app/schemas/` for request/response models
- `app/database.py` for engine/session/base
- `tests/` for API and authorization tests

## Runtime expectations
- Python 3.12 virtualenv already exists in `.venv`.
- Prefer FastAPI + SQLAlchemy + pytest unless the repo already dictates otherwise.
- Keep startup simple; local SQLite is acceptable for initial slices unless a stronger repo convention appears.
- Each BL item should be implemented as a vertical slice with tests and minimal incidental scope.

## Non-negotiable product rules
- Preserve explicit private-workspace privacy semantics: non-members get `404` for workspace-scoped resources; `403` is reserved for known members lacking owner-only membership permissions.
- Preserve cross-tenant isolation across workspaces, projects, tasks, comments, and assignees.
- Preserve assignee clearing when a member is removed from a workspace.
- Preserve `/me/tasks` as strictly tasks assigned to the current user, not all visible tasks.
- Do not leak password data in responses.

## Delivery conventions
- Implement only `Ready` backlog items, in `.agile-v/BACKLOG.md` order.
- Reference the BL id and REQ ids in PRs/commits/tests where practical.
- Derive tests directly from backlog acceptance criteria and `REQUIREMENTS.md` verification criteria.
- Keep endpoints and models small; prefer shared authorization helpers for workspace membership checks to avoid inconsistent 404/403 behavior.

## Suggested first-pass domain model
- User
- Workspace
- WorkspaceMembership (with owner/member role)
- Project (belongs to workspace)
- Task (belongs to project, optional assignee user, status)
- Comment (belongs to task, author user)

## Notes on sequencing
The first sprint is intended to establish auth, workspace privacy, membership management, project basics, and task creation. Later slices add task retrieval/update/delete, comments, member-removal cleanup, and `/me/tasks`.
