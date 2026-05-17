# QA Journey Catalogue

Required end-to-end journeys per engineering BL. Every QA candidate must cover at least these scenarios in its journey suite at the time the corresponding QA cycle runs. **Skills are scored on what they add beyond this minimum**, not on whether they merely hit the minimum.

## Conventions

- Every journey runs against the FastAPI app under subprocess Uvicorn on a fresh SQLite database. No `TestClient(app)`.
- Every journey obtains its bearer tokens via real `/signup` and `/login`.
- Every step asserts both response status AND a substantive content invariant.
- Multi-actor journeys explicitly track which actor each request belongs to.
- After each journey, the suite verifies the DB state matches the cumulative actions (row counts, FK integrity).

## BL-0001 — Authentication Foundation

Target commit: `5baf798` (BL-0001 implementation plus the smoke runner).

### Required journeys

- **J-AUTH-001 Signup-login-me roundtrip**: signup with mixed-case email → login with lowercased email → call `/me` with the issued token → assert normalized email, no password fields, bearer accepted.
- **J-AUTH-002 Duplicate signup hardening**: signup user A → attempt signup with same email different case → assert 409 and no password fields in error → original token still usable on `/me`.
- **J-AUTH-003 Login failure modes**: signup user A → attempt login with wrong password → 401 → attempt login with unknown email → 401 → attempt login with malformed payload → 422 → real login still works.
- **J-AUTH-004 Token negative space**: hit `/me` with no header → 401, with malformed bearer → 401, with truncated token → 401, with token from a logged-out style scenario (if applicable to this BL) → 401.
- **J-AUTH-005 Persistence across restart**: signup → stop Uvicorn → restart against same DB file → login with same credentials → assert success and `/me` returns the same user record.
- **J-AUTH-006 Password storage probe**: signup → open the SQLite file out-of-band → assert no plaintext password, hash format is PBKDF2 (or whatever the engineer documented).

## BL-0002 — Workspace Creation, Listing, Detail, And Privacy Boundary

Target commit: `c5e89e3`. Inherits all BL-0001 journeys.

### Required journeys

- **J-WS-001 Creator becomes admin**: signup A → create workspace → assert 201 → `GET /workspaces` returns it with `role: admin` → `GET /workspaces/{id}` returns detail.
- **J-WS-002 Cross-user invisibility**: signup A and B → A creates workspace → B's `GET /workspaces` is empty → B's `GET /workspaces/{id}` returns 404 with no name/description leak in body or headers.
- **J-WS-003 Token required on workspace endpoints**: every workspace endpoint with no bearer → 401; with malformed bearer → 401.
- **J-WS-004 Multi-workspace isolation**: A creates ws1, A creates ws2, B creates ws3 → `GET /workspaces` for A returns ws1+ws2 only, for B returns ws3 only, with correct roles.
- **J-WS-005 Inherited BL-0001 invariants under workspace use**: after creating workspaces, `/me`, `/login`, `/signup` still behave per BL-0001 journeys.

## BL-0003 — Workspace Member Management And Role Matrix

Target commit: `a898011`. Inherits all BL-0001/0002 journeys.

### Required journeys

- **J-MEM-001 Admin add member with each role**: A admin of ws → add B as `viewer`, add C as `editor`, add D as `admin` → each appears in their own `GET /workspaces` with correct role.
- **J-MEM-002 Non-admin member 403**: A admin, B editor, C viewer → B attempts add member → 403 → C attempts add member → 403 → A still can.
- **J-MEM-003 Non-member 404 with no leak**: A creates ws → X (non-member) attempts to add a member → 404 → response body contains no workspace identifier or name.
- **J-MEM-004 Missing token 401 on member endpoints**: same as J-WS-003 but for member management.
- **J-MEM-005 Last-admin removal rejected**: A sole admin of ws → A attempts to remove A → 409 → membership still present.
- **J-MEM-006 Remove and re-add lifecycle**: A admin, B editor → A removes B → B's `GET /workspaces` empty, `GET /workspaces/{id}` returns 404 → A re-adds B as viewer → B sees workspace with `role: viewer`.
- **J-MEM-007 Role downgrade and upgrade**: at this BL, role change is via remove-and-readd. Assert the resulting role is the re-add role, not the prior role.

## BL-0005 — Project CRUD Within A Workspace

Target commit: `f600039`. Inherits all BL-0001/0002/0003 journeys.

### Required journeys

- **J-PRJ-001 Role × HTTP matrix sweep**: workspace with A admin, B editor, C viewer, X non-member. For each of POST/GET/PATCH/DELETE on project surfaces:
  - A → success.
  - B → success.
  - C → 403 on mutation, 200 on read.
  - X → 404 on every surface, no project ID or name in response body.
  - Missing bearer → 401.
- **J-PRJ-002 Cross-workspace project isolation**: A creates ws1 with project P1, A creates ws2 with project P2 → request P1 with ws2 in path → 404, no project name leak.
- **J-PRJ-003 Update field preservation**: A updates P1's name → `workspace_id` and `id` unchanged → other fields not in payload unchanged.
- **J-PRJ-004 Delete removes from list**: A deletes P1 → `GET .../projects` no longer includes it → `GET .../projects/P1` returns 404.

## BL-0006 — Task CRUD, Status, And Assignment Rules

Target commit: `7f6d104`. Inherits everything above. **`app.py` was refactored at this BL; verify the refactor preserved behavior.**

### Required journeys

- **J-TASK-001 Status enum enforcement**: create task with `status` set to each valid value → 201 → with any invalid value (case-shifted, unicode, integer) → 400 (the BL-0006 chosen code) → assert consistency on PATCH too.
- **J-TASK-002 Assignee must be a current workspace member**: try to create task with assignee email of a non-member → 400, no task created → try with member email → 201 → try to PATCH assignee to a non-member → 400, prior assignee retained.
- **J-TASK-003 Null assignee allowed**: create task with `assignee_email: null` → 201; PATCH from named to null → 200; PATCH from null to member → 200.
- **J-TASK-004 Role × HTTP matrix sweep for tasks**: same shape as J-PRJ-001 across task surfaces.
- **J-TASK-005 Cross-workspace and cross-project task isolation**: task in ws1/P1 cannot be reached via ws1/P2/task_id or ws2/P1/task_id → 404 with no leak.
- **J-TASK-006 Member-removal assignee clearing (BL-0003 AC 6/7/8 now active)**: A admin, B editor with assigned tasks → A removes B → tasks remain → assignee_email is null on B's prior tasks → re-add B → old tasks remain null-assigned, B sees them only if explicitly reassigned.
- **J-TASK-007 Project delete cascades tasks (BL-0005 AC 7 task portion now active)**: project with multiple tasks → delete project → tasks no longer listable in any project under the workspace → DB row check confirms.
- **J-TASK-008 Refactor parity probe**: every BL-0001/0002/0003/0005 journey re-runs against `7f6d104` unchanged. Any regression is a finding.

## BL-0007 — Task Comments For All Workspace Members

Target commit: `87939ad`. Inherits everything above.

### Required journeys

- **J-COM-001 Viewer mutation exception**: workspace with C viewer → C creates comment on a task → 201, comment appears in list → C attempts to mutate the task itself → 403. The exception is comment-create, nothing else.
- **J-COM-002 Cross-actor comment list**: A admin, B editor, C viewer all post comments → any of them lists comments → all three present, ordered by `created_at` ascending → non-member X → 404 with no comment text or count leak.
- **J-COM-003 Validation rejection**: empty body → 400; whitespace-only body → 400; body of length `COMMENT_BODY_MAX + 1` → 400; body exactly at cap → 201.
- **J-COM-004 Author retention after removal**: C viewer posts comment → A admin removes C → comment list still includes the comment with original `author_email` → C cannot list comments (404), but A and B see C's comment intact.
- **J-COM-005 Task delete cascades comments**: task with several comments → delete task → comments gone from list AND DB → other tasks' comments untouched.
- **J-COM-006 Project delete cascades both (BL-0005 AC 7 fully active)**: project with tasks and comments → delete project → all comments AND all tasks for that project gone from DB → other projects untouched.
- **J-COM-007 No cross-task comment leak**: comment on task T1 not in task T2's list, even within same project.

## Required Cross-BL Adversarial Journeys (apply at any BL where target features exist)

- **J-ADV-PRIVACY-001 Existence-leak sweep**: for every workspace-scoped resource type, repeat: non-member request returns 404 with response body containing nothing that distinguishes "exists in another workspace" from "does not exist."
- **J-ADV-ROLE-001 Stale token after role change**: B editor receives token → A admin removes B → B's token still presented → all endpoints should now return 401 or 404 consistently; if any returns 200, finding.
- **J-ADV-INPUT-001 Malformed payload survives**: POST every mutating endpoint with malformed JSON, missing required fields, wrong content type, oversized payload — all responses are deterministic HTTP codes with no stack traces in body.
- **J-ADV-CONCURRENCY-001 (BL-0003+)**: two near-simultaneous admin removals of each other in a two-admin workspace — the last-admin invariant must hold for the surviving admin.

## Scoring Implications

- Hitting the minimum journey set is necessary, not sufficient. The maximum score requires substantive additions across journey depth, breadth, and adversarial categories.
- A journey suite that passes against the BL under test but breaks against a later BL is *correct behavior* — the failure surfaces as a finding for the later BL, with the suite-continuity axis preserved.
