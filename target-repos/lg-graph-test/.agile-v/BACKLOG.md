# Backlog: Project Tracker v1

## BL-0001: Project Bootstrap and Database Schema
**Type:** Technical · **Priority:** CRITICAL · **REQ:** REQ-0022
**Story:** As a developer, I want a bootstrapped FastAPI project with database models so that the service can run and persist data.
**Acceptance:**
1. FastAPI app starts with `uvicorn` and responds to a health endpoint.
2. SQLAlchemy (or equivalent ORM) models exist for User, Workspace, Membership, Project, Task, and Comment with correct relationships.
3. Database migrations or auto-create tables are configured.
4. Project structure follows standard FastAPI layout (routers, models, schemas, dependencies).
**Effort:** 5 · **Dependencies:** none · **Status:** Ready

## BL-0002: Authentication Signup and Login
**Type:** Feature · **Priority:** CRITICAL · **REQ:** REQ-0001, REQ-0002, REQ-0022
**Story:** As a user, I want to sign up with email and password and log in to receive a bearer token so that I can access protected resources.
**Acceptance:**
1. `POST /auth/signup` creates a user with hashed password; duplicate email returns `400` or `409`.
2. `POST /auth/login` returns a bearer token for valid credentials and `401` for invalid credentials.
3. Password is never returned in any API response.
4. Protected endpoints reject missing or invalid tokens with `401`.
**Effort:** 5 · **Dependencies:** BL-0001 · **Status:** Ready

## BL-0003: Current User Endpoint
**Type:** Feature · **Priority:** CRITICAL · **REQ:** REQ-0003, REQ-0022
**Story:** As an authenticated user, I want to call `GET /me` so that I can see my own account details.
**Acceptance:**
1. `GET /me` returns the current user's email and id without password fields.
2. Missing or invalid bearer token returns `401`.
3. Response shape is consistent with the user model schema.
**Effort:** 2 · **Dependencies:** BL-0002 · **Status:** Ready

## BL-0004: Workspace Creation
**Type:** Feature · **Priority:** CRITICAL · **REQ:** REQ-0004, REQ-0022
**Story:** As an authenticated user, I want to create a workspace so that I can organize projects with my team.
**Acceptance:**
1. `POST /workspaces` creates a workspace and sets the creator as the first admin.
2. Created workspace appears in the creator's workspace list with role `admin`.
3. Workspace is private to its members (non-members cannot see it).
**Effort:** 3 · **Dependencies:** BL-0002 · **Status:** Ready

## BL-0005: Workspace Listing and Detail
**Type:** Feature · **Priority:** CRITICAL · **REQ:** REQ-0008, REQ-0020, REQ-0022
**Story:** As a workspace member, I want to list my workspaces and view a specific workspace so that I can navigate my teams.
**Acceptance:**
1. `GET /workspaces` lists only workspaces the caller belongs to.
2. `GET /workspaces/{ws_id}` returns workspace details for members.
3. Non-member requests to either endpoint return `404` (not `403`).
4. No workspace data leaks to non-members.
**Effort:** 3 · **Dependencies:** BL-0004 · **Status:** Ready

## BL-0006: Workspace Membership Management
**Type:** Feature · **Priority:** CRITICAL · **REQ:** REQ-0005, REQ-0021, REQ-0020, REQ-0022
**Story:** As a workspace admin, I want to add members by email with a role so that my team can collaborate.
**Acceptance:**
1. Admin can add a member by email with role `admin`, `editor`, or `viewer`.
2. Non-admin member attempts return `403`.
3. Non-member attempts return `404`.
4. Added user can access the workspace according to their role.
**Effort:** 4 · **Dependencies:** BL-0005 · **Status:** Ready

## BL-0007: Workspace Member Removal with Assignee Clearing
**Type:** Feature · **Priority:** HIGH · **REQ:** REQ-0006, REQ-0007, REQ-0021, REQ-0020, REQ-0022
**Story:** As a workspace admin, I want to remove a member so that they lose access, and their assigned tasks are unassigned.
**Acceptance:**
1. Admin can remove a member; the member loses workspace access.
2. Last admin cannot be removed (returns `400` or `403`).
3. Tasks assigned to the removed user in that workspace have `assignee_email` set to null.
4. Tasks and comments are not deleted.
5. Re-adding the user does not auto-reassign old tasks.
6. Non-admin/non-member attempts return `403`/`404` respectively.
**Effort:** 4 · **Dependencies:** BL-0006, BL-0013 · **Status:** Backlog

## BL-0008: Workspace Deletion Cascade
**Type:** Feature · **Priority:** HIGH · **REQ:** REQ-0009, REQ-0021, REQ-0020, REQ-0022
**Story:** As a workspace admin, I want to delete a workspace so that all its data is removed.
**Acceptance:**
1. Admin can delete a workspace.
2. Deleting a workspace cascades to all projects, tasks, and comments under it.
3. Non-admin members cannot delete (returns `403`).
4. Non-members receive `404`.
**Effort:** 3 · **Dependencies:** BL-0005 · **Status:** Ready

## BL-0009: Project Creation
**Type:** Feature · **Priority:** HIGH · **REQ:** REQ-0010, REQ-0021, REQ-0020, REQ-0022
**Story:** As a workspace admin or editor, I want to create projects so that I can organize work.
**Acceptance:**
1. Admin and editor can create projects inside a workspace.
2. Viewer creation returns `403`.
3. Non-member access returns `404`.
4. Project belongs to the selected workspace.
**Effort:** 3 · **Dependencies:** BL-0005 · **Status:** Ready

## BL-0010: Project Listing
**Type:** Feature · **Priority:** HIGH · **REQ:** REQ-0011, REQ-0020, REQ-0022
**Story:** As a workspace member, I want to list projects so that I can see what work is organized in my workspace.
**Acceptance:**
1. Any workspace member (admin, editor, viewer) can list projects.
2. Non-member receives `404`.
3. Projects from other workspaces are not included.
**Effort:** 2 · **Dependencies:** BL-0009 · **Status:** Ready

## BL-0011: Project Update and Delete
**Type:** Feature · **Priority:** HIGH · **REQ:** REQ-0012, REQ-0021, REQ-0020, REQ-0022
**Story:** As a workspace admin or editor, I want to update and delete projects so that I can manage my workspace content.
**Acceptance:**
1. Admin and editor can update and delete projects.
2. Viewer mutation returns `403`.
3. Non-member mutation returns `404`.
4. Deleting a project cascades to tasks and comments under it.
**Effort:** 3 · **Dependencies:** BL-0010 · **Status:** Ready

## BL-0012: Task Creation with Assignment
**Type:** Feature · **Priority:** HIGH · **REQ:** REQ-0013, REQ-0014, REQ-0021, REQ-0020, REQ-0022
**Story:** As a workspace admin or editor, I want to create tasks and optionally assign them to workspace members so that work is tracked.
**Acceptance:**
1. Admin and editor can create tasks in a project with status `todo`, `in_progress`, or `done`.
2. Task can optionally include `assignee_email`; assignee must be a workspace member or creation returns `400`.
3. Null assignee is allowed.
4. Viewer creation returns `403`; non-member returns `404`.
**Effort:** 4 · **Dependencies:** BL-0010 · **Status:** Ready

## BL-0013: Task Listing
**Type:** Feature · **Priority:** HIGH · **REQ:** REQ-0015, REQ-0020, REQ-0022
**Story:** As a workspace member, I want to list tasks in a project so that I can see the work items.
**Acceptance:**
1. Any workspace member can list tasks in a project.
2. Non-member receives `404`.
3. Tasks from other workspaces/projects are not included.
**Effort:** 2 · **Dependencies:** BL-0012 · **Status:** Ready

## BL-0014: Task Update and Delete
**Type:** Feature · **Priority:** HIGH · **REQ:** REQ-0016, REQ-0021, REQ-0020, REQ-0022
**Story:** As a workspace admin or editor, I want to update and delete tasks so that I can manage work items.
**Acceptance:**
1. Admin and editor can update and delete tasks.
2. Viewer mutation returns `403`.
3. Non-member mutation returns `404`.
4. Deleted tasks are removed from lists and summaries.
**Effort:** 3 · **Dependencies:** BL-0013 · **Status:** Ready

## BL-0015: Comments on Tasks
**Type:** Feature · **Priority:** MEDIUM · **REQ:** REQ-0017, REQ-0020, REQ-0022
**Story:** As a workspace member, I want to add and list comments on tasks so that my team can discuss work.
**Acceptance:**
1. Any workspace member (including viewers) can add and list comments on a task.
2. Non-member comment access returns `404` without leaking task existence.
3. Comments remain when their author is removed from the workspace.
**Effort:** 3 · **Dependencies:** BL-0013 · **Status:** Ready

## BL-0016: My Assigned Tasks Endpoint
**Type:** Feature · **Priority:** MEDIUM · **REQ:** REQ-0018, REQ-0020, REQ-0022
**Story:** As an authenticated user, I want to call `GET /me/tasks` so that I can see all tasks assigned to me across workspaces.
**Acceptance:**
1. `GET /me/tasks` returns tasks where `assignee_email` equals the current user's email.
2. Results are sorted by `created_at` descending.
3. Tasks from workspaces where the user is not a member never appear.
4. Tasks are never returned merely because the user is an admin, member, or commenter.
**Effort:** 3 · **Dependencies:** BL-0013, BL-0003 · **Status:** Ready

## BL-0017: Workspace Summary Endpoint
**Type:** Feature · **Priority:** MEDIUM · **REQ:** REQ-0019, REQ-0020, REQ-0022
**Story:** As a workspace member, I want to view a summary of task counts per project by status so that I can understand workspace progress.
**Acceptance:**
1. `GET /workspaces/{ws_id}/summary` returns per-project task counts grouped by status.
2. Any workspace member can access it.
3. Non-members receive `404`.
4. Counts match actual task records; no private workspace data leaks.
**Effort:** 3 · **Dependencies:** BL-0013 · **Status:** Ready

## BL-0018: Cross-Tenant Privacy and Role Enforcement Tests
**Type:** Technical · **Priority:** CRITICAL · **REQ:** REQ-0020, REQ-0021, REQ-0022
**Story:** As a QA engineer, I want comprehensive privacy and role enforcement tests so that cross-tenant isolation is verified.
**Acceptance:**
1. Non-member requests to all workspace-scoped paths return `404` (not `403`).
2. Role failures for existing members return `403`.
3. Test matrix covers all endpoints: workspace, project, task, comment, `/me/tasks`, and summary.
4. Privacy behavior is consistent across all endpoints.
**Effort:** 5 · **Dependencies:** BL-0017 · **Status:** Backlog
