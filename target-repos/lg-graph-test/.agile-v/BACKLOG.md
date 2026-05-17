# BACKLOG.md

## BL-0001: Authentication foundation and current-user access
**Type:** Feature · **Priority:** CRITICAL · **REQ:** REQ-0001, REQ-0002
**Story:** As a user, I want to register and log in so that I can securely access protected Project Tracker features.
**Acceptance:** 1) A new user can register with a unique username and password and receives user identity data without password fields. 2) Duplicate usernames are rejected with a client error. 3) A registered user can log in and receive a bearer token. 4) Invalid credentials are rejected. 5) At least one protected endpoint validates the bearer token and rejects unauthenticated access.
**Effort:** 5 SP · **Dependencies:** none · **Status:** Ready
**Notes:** Foundation item for all protected workspace, project, task, comment, and /me flows. Pattern: reference app/main.py wires auth and protected routers in a standard FastAPI layout.

## BL-0002: Workspace creation and my-workspaces listing
**Type:** Feature · **Priority:** CRITICAL · **REQ:** REQ-0003, REQ-0006
**Story:** As an authenticated user, I want to create a private workspace and list my workspaces so that I can organize work inside private team spaces.
**Acceptance:** 1) An authenticated user can create a workspace. 2) The creator is stored as owner membership at creation time. 3) The my-workspaces endpoint returns all and only workspaces where the current user is a member. 4) Workspaces of other users are not exposed. 5) Unauthenticated requests to protected workspace endpoints are rejected.
**Effort:** 5 SP · **Dependencies:** BL-0001 · **Status:** Ready
**Notes:** Pattern: reference workspaces router creates workspace plus owner membership in one flow.

## BL-0003: Workspace membership add with privacy-preserving authorization
**Type:** Feature · **Priority:** CRITICAL · **REQ:** REQ-0004, REQ-0017
**Story:** As a workspace owner, I want to add an existing user to my workspace so that teammates can collaborate without exposing private workspace existence to outsiders.
**Acceptance:** 1) A workspace owner can add an existing user as a member. 2) A known workspace member who is not owner receives 403 when attempting membership management. 3) A caller who is not a workspace member receives 404 when targeting the workspace. 4) Adding a non-existent user is rejected without creating membership. 5) Authorization behavior preserves explicit 404 versus 403 privacy semantics.
**Effort:** 3 SP · **Dependencies:** BL-0002 · **Status:** Ready
**Notes:** Pattern: reference workspaces router distinguishes non-member 404 from member-without-role 403.

## BL-0004: Workspace member removal with assignee clearing
**Type:** Feature · **Priority:** CRITICAL · **REQ:** REQ-0005, REQ-0017, REQ-0018
**Story:** As a workspace owner, I want to remove a member and clear their task assignments so that workspace access and task ownership remain accurate.
**Acceptance:** 1) A workspace owner can remove a member from the workspace. 2) A removed member no longer appears as having access to the workspace. 3) Any tasks in that workspace assigned to the removed member have assignee cleared. 4) A known member who is not owner receives 403 for member removal. 5) A non-member targeting the workspace receives 404. 6) No invalid assignee references remain after removal.
**Effort:** 5 SP · **Dependencies:** BL-0003, BL-0007 · **Status:** Backlog
**Notes:** Pattern: reference workspaces router clears assignee_id on tasks before deleting membership. Depends on task model existing.

## BL-0005: Project creation inside a private workspace
**Type:** Feature · **Priority:** CRITICAL · **REQ:** REQ-0007, REQ-0017, REQ-0018
**Story:** As a workspace member, I want to create a project in my workspace so that I can group related tasks.
**Acceptance:** 1) A workspace member can create a project in the workspace. 2) The project is linked to the correct workspace. 3) A non-member targeting the private workspace receives 404. 4) Cross-workspace parent linkage is rejected. 5) Authorization behavior does not reveal private workspace existence to non-members.
**Effort:** 3 SP · **Dependencies:** BL-0002 · **Status:** Ready
**Notes:** Exploratory only in target repo, but reference shows a thin router pattern for workspace-scoped creation.

## BL-0006: Project listing within workspace
**Type:** Feature · **Priority:** HIGH · **REQ:** REQ-0008, REQ-0017
**Story:** As a workspace member, I want to list projects in my workspace so that I can navigate work without seeing other tenants' data.
**Acceptance:** 1) A workspace member can list projects for the targeted workspace. 2) Only projects from that workspace are returned. 3) A non-member targeting the private workspace receives 404. 4) The response does not include projects from other workspaces.
**Effort:** 2 SP · **Dependencies:** BL-0005 · **Status:** Ready
**Notes:** Small follow-on slice after project creation.

## BL-0007: Task creation with workspace-scoped assignee validation
**Type:** Feature · **Priority:** CRITICAL · **REQ:** REQ-0009, REQ-0017, REQ-0018
**Story:** As a workspace member, I want to create tasks in a project and optionally assign them to workspace members so that work can be tracked safely within a tenant boundary.
**Acceptance:** 1) A workspace member can create a task in a project in their workspace. 2) A task can be created without an assignee. 3) If an assignee is provided, the assignee must be a current member of the same workspace. 4) Providing an assignee who is not a workspace member is rejected with 404. 5) A non-member targeting the workspace or project receives 404. 6) The created task is linked to the correct project and workspace scope.
**Effort:** 5 SP · **Dependencies:** BL-0005, BL-0003 · **Status:** Ready
**Notes:** Pattern: reference tasks router uses a shared workspace-membership check and returns 404 for non-member assignee cases.

## BL-0008: Task listing and detail retrieval
**Type:** Feature · **Priority:** HIGH · **REQ:** REQ-0010, REQ-0011, REQ-0017
**Story:** As a workspace member, I want to list tasks in a project and open a task detail so that I can track work without leaking private resource existence.
**Acceptance:** 1) A workspace member can list tasks for a project in their workspace. 2) Only tasks from the specified project are returned. 3) A workspace member can retrieve a single in-scope task. 4) Requesting an out-of-scope workspace or task returns 404. 5) Requesting a missing in-scope task also returns 404.
**Effort:** 3 SP · **Dependencies:** BL-0007 · **Status:** Backlog
**Notes:** Pattern: reference tasks router has separate list and get handlers sharing scoped membership checks.

## BL-0009: Task update including assign and clear assignee
**Type:** Feature · **Priority:** HIGH · **REQ:** REQ-0012, REQ-0017, REQ-0018
**Story:** As a workspace member, I want to update task fields and manage assignees so that task state stays current.
**Acceptance:** 1) A workspace member can update task title, description, and status. 2) A workspace member can assign a task to another current workspace member. 3) A workspace member can clear the assignee. 4) Assigning to a non-member is rejected with 404. 5) A non-member targeting the task receives 404. 6) Updated task data remains scoped to the same workspace and project lineage.
**Effort:** 5 SP · **Dependencies:** BL-0007 · **Status:** Backlog
**Notes:** Pattern: reference tasks router supports status changes and assignee validation in one update flow.

## BL-0010: Task deletion with dependent comment cleanup
**Type:** Feature · **Priority:** HIGH · **REQ:** REQ-0013, REQ-0018, REQ-0017
**Story:** As a workspace member, I want to delete a task safely so that obsolete work and its dependent records do not remain.
**Acceptance:** 1) A workspace member can delete a task in their workspace. 2) The deleted task is no longer retrievable. 3) Dependent comments are removed or otherwise invalidated according to the chosen persistence strategy. 4) A non-member targeting the task receives 404. 5) No invalid child references remain after deletion.
**Effort:** 3 SP · **Dependencies:** BL-0008, BL-0011 · **Status:** Backlog
**Notes:** Depends on comment model behavior being present to verify referential cleanup.

## BL-0011: Comment creation and listing on tasks
**Type:** Feature · **Priority:** HIGH · **REQ:** REQ-0014, REQ-0015, REQ-0017, REQ-0018
**Story:** As a workspace member, I want to add and read comments on tasks so that collaboration stays attached to the correct work item.
**Acceptance:** 1) A workspace member can add a comment to a task in their workspace. 2) The comment is linked to the correct task and author. 3) A workspace member can list comments for a task in their workspace. 4) Only comments for the specified task are returned. 5) A non-member targeting the task receives 404. 6) Comments cannot be created across workspace boundaries.
**Effort:** 5 SP · **Dependencies:** BL-0008 · **Status:** Backlog
**Notes:** New architectural layer; keep as a single vertical slice because create/list pair is tightly coupled.

## BL-0012: My assigned tasks endpoint
**Type:** Feature · **Priority:** HIGH · **REQ:** REQ-0016, REQ-0017
**Story:** As an authenticated user, I want a /me/tasks view of only tasks assigned to me so that I can focus on my work queue.
**Acceptance:** 1) The endpoint returns only tasks whose assignee is the current user. 2) Visible but unassigned tasks are not returned. 3) Tasks assigned to other users are not returned. 4) Tasks from workspaces where the user is no longer a member are not returned. 5) The endpoint behavior is strictly “my assigned tasks,” not “tasks I can see.”
**Effort:** 3 SP · **Dependencies:** BL-0007 · **Status:** Backlog
**Notes:** Preserve brief requirement that /me/tasks is assignee-based only.
