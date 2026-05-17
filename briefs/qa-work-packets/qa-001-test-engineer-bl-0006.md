# QA Work Packet: QA-001 BL-0006 Task CRUD, Status, And Assignment Rules

## Run

- Run ID: `qa-001-test-engineer-bl-0006`
- QA Skill: `qa-001-test-engineer`
- Target Repo: `target-repos/project-tracker-v1-engineering-baseline`
- Target Commit: `7f6d104` (BL-0006 closing commit)
- Engineering BL Under Test: `BL-0006`

## Objective

Gate the BL-0006 task CRUD surface and the architectural refactor that landed at this BL. Carry forward the 46-scenario suite from the BL-0005 cycle, add task-surface journeys, **probe the refactor for behavior parity**, **probe the activated cascade and assignee-clearing behavior**, and extend the systemic-defect-class probes to the task tier (Class A: huge-task-ID overflow; Class B: concurrent task-delete race).

This is QA cycle 5 of 6 for `QA-001`. It is the most consequential cycle yet because it gates the largest engineering delta (refactor + feature + two activations).

## Source Context

- Engineering work packet: `briefs/engineering-work-packets/bl-0006-task-crud-status-and-assignment-rules.md`
- Engineering run: `runs/eng-001-incremental-implementation-bl-0006/` (scored Pass 74/75 — engineering's high score; the BL-0006 refactor lifted the maintainability ceiling)
- Prior QA run: `runs/qa-001-test-engineer-bl-0005/` (scored Pass 74/75 + axes 40/40)
- QA evaluation protocol: `docs/qa_evaluation_protocol.md`
- QA journey catalogue: `docs/qa_journey_catalogue.md` (BL-0006 section)
- QA skill: `skills/qa/qa-001-test-engineer/SKILLS.md` (SHA-256 `1e6d69462066eac39c7f19f8ad13b527dc8db6c2266dc551b4002e99b8096745`)
- **Carry-forward suite**: `runs/qa-001-test-engineer-bl-0005/journey_suite/` — copy into `runs/qa-001-test-engineer-bl-0006/journey_suite/`.

## Carry-Forward Expectations Regarding Known Bugs

Four known propagating bugs continue from prior cycles. Use the existing `KNOWN_BUGS` registry pattern.

- `BUG-QA001-BL2-001` (High) — `GET /workspaces/{2**63}` → 500.
- `BUG-QA001-BL3-001` (Critical) — concurrent dual-admin member-removal both return 204.
- `BUG-QA001-BL5-001` (High) — `GET /workspaces/{ws}/projects/{2**63}` → 500.
- `BUG-QA001-BL5-002` (High) — concurrent dual-admin project-delete both return 204.

**Important note about line numbers**: `BUG-QA001-BL3-001`'s original repro cited `app.py:429-444`. At `7f6d104` the code lives in `routers/members.py` after the refactor. The defect is structurally the same; the suite probes it via behavior (HTTP) not by line, so the carry-forward scenario will continue to find it without modification.

Do NOT re-file the four known bugs. Reference them in `bug_report.md` as still-active. New unique findings get `BUG-QA001-BL6-XXX` IDs.

## Mandatory Inputs The QA Agent Must Execute At Target Commit

Inside `target-repos/project-tracker-v1-engineering-baseline` after `git checkout 7f6d104`:

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl0001.py
.venv/bin/python verify_bl0002.py
.venv/bin/python verify_bl0003.py
.venv/bin/python verify_bl0005.py
.venv/bin/python verify_bl0006.py
.venv/bin/python scripts/full_http_smoke.py --port 8838
```

Capture exit code + verbatim stdout. Non-zero exit is a finding.

**Note at `7f6d104`**: the refactor landed. Files now include `database.py`, `models.py`, `schemas.py`, `security.py`, and `routers/{auth,workspaces,members,projects,tasks}.py`. Tests: `test_auth.py`, `test_members.py`, `test_projects.py`, `test_tasks.py`. Verifiers `verify_bl0001/0002/0003/0005/0006.py` were rewritten as behavior-based `TestClient` probes. `pytest -q` should be 73 passed at this commit.

## In-Scope Feature Surface (BL-0006)

Verbatim-equivalent from the engineering work packet's In Scope:

- `Task` model with `project_id` FK, optional `description`, `assignee_email`, `status` enum (`todo`/`in_progress`/`done`).
- `POST /workspaces/{ws}/projects/{pid}/tasks` — admin/editor; viewer → 403; non-member → 404.
- `GET .../tasks` and `GET .../tasks/{tid}` — any workspace member; non-member → 404.
- `PATCH .../tasks/{tid}` — admin/editor; viewer → 403; non-member → 404.
- `DELETE .../tasks/{tid}` — admin/editor; viewer → 403; non-member → 404.
- Invalid status (both create + PATCH) → 400 (engineer's chosen code).
- Non-member `assignee_email` (both create + PATCH) → 400; null assignee allowed.
- Bearer auth on all task endpoints; missing → 401.

Inherited BL-0001/0002/0003/0005 surfaces remain in scope.

### Activated previously-deferred behavior

- **BL-0003 AC 6/7/8**: member removal now clears `assignee_email` on the removed user's tasks in that workspace; tasks themselves remain; re-adding does not auto-reassign.
- **BL-0005 AC 7 (task portion)**: deleting a project now removes its tasks via the cascade hook.

The activation tests are part of the BL-0006 in-scope behavior at this commit.

## Required Journeys

### Carry-forward (must continue to pass against `7f6d104`, except known bugs)

All 46 scenarios from the BL-0005 cycle. The four known bugs continue to fail as documented. **Any new regression in non-known-bug scenarios is a finding — including a regression introduced by the refactor.** This is the refactor parity probe (J-TASK-008 in spirit).

### New required (from `docs/qa_journey_catalogue.md` BL-0006 section)

- **J-TASK-001** Status enum enforcement — create task with each valid status → 201; with any invalid value (case-shifted, unicode, integer, SQL-ish string) → 400; same on PATCH.
- **J-TASK-002** Assignee must be a current workspace member — create with non-member email → 400, no task created; with member email → 201; PATCH assignee to non-member → 400, prior assignee retained.
- **J-TASK-003** Null assignee allowed — create with `assignee_email: null` → 201; PATCH named → null → 200; PATCH null → member → 200.
- **J-TASK-004** Role × HTTP matrix sweep for tasks — same shape as J-PRJ-001.
- **J-TASK-005** Cross-workspace and cross-project task isolation — task in ws1/P1 not reachable via ws1/P2/tid or ws2/P1/tid → 404, no leak.
- **J-TASK-006** Member-removal assignee clearing (BL-0003 AC 6/7/8 now active) — admin removes editor with assigned tasks → tasks remain → assignee_email is null on removed user's prior tasks → re-add → old tasks remain null-assigned.
- **J-TASK-007** Project delete cascades tasks (BL-0005 AC 7 task portion now active) — project with multiple tasks → delete project → tasks no longer listable in any project under the workspace → DB row check confirms.
- **J-TASK-008** Refactor parity probe — already implicitly covered by the 46-scenario carry-forward. Make this explicit by re-running the suite and reporting any regression as a refactor-parity finding with the `regression` category.

### Cross-BL adversarial (next tier for systemic defect classes)

- **NEW J-ADV-OVERFLOW-TASK-001** Class A at task tier — `GET /workspaces/{ws}/projects/{pid}/tasks/{2**63}` → expected 404 with no stack trace; observed 500 with `OverflowError` would confirm the defect propagates to task tier. **Predicted to recur.**
- **NEW J-ADV-CONCURRENCY-TASK-001** Class B at task tier — two admins simultaneously DELETE the same task (`threading.Barrier(2)`). Assert: exactly one 200/204, the other 404 or 409. **Predicted to recur.**
- **NEW J-ADV-CASCADE-RACE-001** Cascade race — admin starts `DELETE /workspaces/{ws}/projects/{pid}` while a second admin posts `POST .../projects/{pid}/tasks` (`threading.Barrier(2)`). Assert: either the task is created before project delete (task should then be cascade-deleted), or the post returns 404 because the project is gone. The forbidden outcome is a task left orphaned in the DB.

### Activation probes

These belong to J-TASK-006 and J-TASK-007 above but call them out explicitly: the BL-0003 and BL-0005 hooks have not been exercised against real tables until this commit. If the activation does not work — e.g., assignee_email is not cleared on removal, or tasks remain after project delete — file as critical findings.

### Cross-BL adversarial (carry-forward; continue to apply)

- **J-ADV-PRIVACY-001 (task tier)** Extend existence-leak sweep to task endpoints. Non-member task operations return 404 byte-identical to operations against non-existent IDs.
- **J-ADV-ROLE-001 (re-run against task surface)** Stale token after role change applied to task endpoints.

Skills are scored on what they add beyond. Suggested additions: status case-sensitivity (`Todo`, `TODO`, `done ` with trailing space), title and description validation (empty, oversize, unicode), assignee-email case-normalization parity with login, large-N task listing per project, PATCH with status transitions in unconventional order (done → todo — is it allowed?), idempotent DELETE.

## Required Implementation Of The Journey Suite

The journey suite lives at `runs/qa-001-test-engineer-bl-0006/journey_suite/`. It must:

- **Start from the BL-0005 suite copy.** Extend in place.
- Subprocess Uvicorn + real HTTP + fresh tmp SQLite per scenario, ports `8839+` (engineer uses `8838` at this BL).
- Continue using `KNOWN_BUGS` registry. New known-bug discoveries (e.g., if the Class A or Class B predictions confirm at task tier) get added to the registry similarly.
- Pass all non-known-bug carry-forward scenarios — including the refactor parity check.
- Add all required BL-0006 journeys plus the three new adversarial scenarios above.
- Add at least 2 beyond-minimum scenarios.
- Remain deterministic.
- Emit `runs/qa-001-test-engineer-bl-0006/journey_results.json`.
- Exit non-zero ONLY on unknown failures.

## Out Of Scope

- Patching engineer code.
- Testing BL-0007 features (comments — do not exist yet at `7f6d104`).
- Re-grading the engineering BL-0006 scorecard.
- Implementing workspace deletion (BL-0004 not closed).
- Testing the cascade portion that depends on comments — that's BL-0007.

## Expected Artifacts

Under `runs/qa-001-test-engineer-bl-0006/`:

- `engineer_stack_results.txt`
- `gap_audit.md`
- `journey_suite/` (46 carried + new BL-0006 scenarios)
- `journey_results.json`
- `bug_report.md` (references 4 prior known bugs; new findings `BUG-QA001-BL6-XXX`)
- `raw_logs/invocation.md`
- `metadata.yaml`

## Done Criteria

- Every command in mandatory inputs ran; exit code + stdout recorded.
- `gap_audit.md` enumerates gaps in `tests/test_tasks.py`, `verify_bl0006.py`, the BL-0006 block in `scripts/full_http_smoke.py`, AND the rewritten BL-0001/0002/0003/0005 verifiers (now behavior-based — they may have new gaps).
- All 8 J-TASK-* journeys plus the three new adversarial scenarios plus the cross-BL re-runs implemented and run.
- Carry-forward parity verified — explicit refactor-parity report in `raw_logs/invocation.md`.
- Each new bug report entry is reproducible.
- `metadata.yaml` filled.

## Execution Rules Reminder

- Do NOT advance the target repo past `7f6d104`. When done, `git checkout main`. Verify `HEAD == 87939ad`.
- Do NOT modify planning artifacts or engineer code.
- Do NOT use `TestClient(app)` in the journey suite.
- Do NOT skip the engineer-authored verification stack.
- Do NOT remove or soften known-bug scenarios or carry-forward scenarios. Real regressions (including refactor-introduced ones) are findings.
- Class A and Class B recurrence at task tier are PREDICTED. If they confirm, file as `BUG-QA001-BL6-XXX` AND note the systemic pattern in the bug report. If they do NOT recur (engineering centralized a fix), that is a meaningful positive finding to document.
