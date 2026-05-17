# QA Work Packet: QA-001 BL-0005 Project CRUD Within A Workspace

## Run

- Run ID: `qa-001-test-engineer-bl-0005`
- QA Skill: `qa-001-test-engineer`
- Target Repo: `target-repos/project-tracker-v1-engineering-baseline`
- Target Commit: `f600039` (BL-0005 closing commit)
- Engineering BL Under Test: `BL-0005`

## Objective

Gate the BL-0005 project CRUD surface. Carry forward the 33-scenario suite from the BL-0003 cycle, add project-surface journeys, and exercise the cross-BL adversarial journeys against the new role × HTTP × resource boundary.

This is QA cycle 4 of 6 for `QA-001`.

Note: BL-0004 (workspace deletion cascade) was never closed by engineering due to dependency ordering. BL-0005 is the next closed BL after BL-0003.

## Source Context

- Engineering work packet: `briefs/engineering-work-packets/bl-0005-project-crud-within-a-workspace.md`
- Engineering run: `runs/eng-001-incremental-implementation-bl-0005/` (scored Pass 72/75)
- Prior QA run: `runs/qa-001-test-engineer-bl-0003/` (scored Pass 74/75 + axes 40/40)
- QA evaluation protocol: `docs/qa_evaluation_protocol.md`
- QA journey catalogue: `docs/qa_journey_catalogue.md` (BL-0005 section)
- QA skill: `skills/qa/qa-001-test-engineer/SKILLS.md` (SHA-256 `1e6d69462066eac39c7f19f8ad13b527dc8db6c2266dc551b4002e99b8096745`)
- **Carry-forward suite**: `runs/qa-001-test-engineer-bl-0003/journey_suite/` — copy into `runs/qa-001-test-engineer-bl-0005/journey_suite/`.

## Carry-Forward Expectations Regarding Known Bugs

Two known propagating bugs continue from prior cycles. Both are expected to remain failing at `f600039`. Use the `KNOWN_BUGS` registry pattern introduced in the BL-0003 cycle.

- **`BUG-QA001-BL2-001`** (High) — `GET /workspaces/{2**63}` raises `OverflowError` → 500.
- **`BUG-QA001-BL3-001`** (Critical) — concurrent dual-admin `DELETE` both return 204, last-admin invariant broken.

Do NOT re-file these. Reference them in `bug_report.md` as still-active. New unique findings get `BUG-QA001-BL5-XXX` IDs.

## Mandatory Inputs The QA Agent Must Execute At Target Commit

Inside `target-repos/project-tracker-v1-engineering-baseline` after `git checkout f600039`:

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl0001.py
.venv/bin/python verify_bl0002.py
.venv/bin/python verify_bl0003.py
.venv/bin/python verify_bl0005.py
.venv/bin/python scripts/full_http_smoke.py --port 8836
```

Capture exit code + verbatim stdout. Non-zero exit is a finding.

**Note at `f600039`**: still single-file `app.py` (the refactor lands at BL-0006). `tests/test_auth.py`, `tests/test_members.py`, `tests/test_projects.py` exist. `verify_bl0001/0002/0003/0005.py` exist. No `tests/test_tasks.py`, no `routers/`, no `models.py`. Tasks and comments tables do not exist yet, so the BL-0005 defensive cascade hook (`cascade_delete_project_descendants`) is a runtime no-op for both — the suite should not assert task or comment cascade behavior at this BL.

## In-Scope Feature Surface (BL-0005)

Verbatim from the engineering work packet's In Scope:

- Persist projects scoped to a workspace (workspace_id FK, project name, optional description, timestamps).
- `POST /workspaces/{ws_id}/projects` — admin/editor only; viewer → 403; non-member → 404.
- `GET /workspaces/{ws_id}/projects` — any workspace member; non-member → 404.
- `GET /workspaces/{ws_id}/projects/{project_id}` — any workspace member; non-member → 404; cross-workspace project lookup → 404.
- `PATCH /workspaces/{ws_id}/projects/{project_id}` — admin/editor only; viewer → 403; non-member → 404.
- `DELETE /workspaces/{ws_id}/projects/{project_id}` — admin/editor only; viewer → 403; non-member → 404.
- Bearer auth on all project endpoints; missing → 401.

Inherited BL-0001/0002/0003 surfaces remain in scope.

## Required Journeys

### Carry-forward (must continue to pass against `f600039`, except known bugs)

All 33 scenarios from the BL-0003 cycle. The two known bugs continue to fail as documented. Any new regression in non-known-bug scenarios is a finding.

### New required (from `docs/qa_journey_catalogue.md` BL-0005 section)

- **J-PRJ-001** Role × HTTP matrix sweep — for each of POST/GET/PATCH/DELETE on project surfaces: admin → success, editor → success on mutation, viewer → 403 on mutation / 200 on read, non-member → 404 on every surface with no project ID/name leak, missing bearer → 401.
- **J-PRJ-002** Cross-workspace project isolation — A creates ws1 with project P1, A creates ws2 with project P2; request P1 with ws2 in path → 404, no project name leak.
- **J-PRJ-003** Update field preservation — A updates P1's name → `workspace_id` and `id` unchanged → other fields not in payload unchanged.
- **J-PRJ-004** Delete removes from list — A deletes P1 → `GET .../projects` no longer includes it → `GET .../projects/P1` returns 404.

### Cross-BL adversarial (apply at this BL)

- **J-ADV-PRIVACY-001 (project tier)** — extend existence-leak sweep to project endpoints. Non-member `GET /workspaces/{ws}/projects/{pid}` and mutation paths return 404 with response body byte-identical (modulo volatile headers) to the same operation against a non-existent project ID or a non-existent workspace ID.
- **J-ADV-ROLE-001 (re-run against project surface)** — stale token after role change should also apply to project endpoints. B is editor in W, A removes B, B's token still presented — project endpoints should now return 404 (or 401), not 200.
- **J-ADV-CONCURRENCY-001 (carry-forward — still failing)** — already known. Continue to execute.
- **NEW J-ADV-CONCURRENCY-002 (project surface)** — two admins simultaneously DELETE the same project (`threading.Barrier(2)`). Assert: exactly one 200/204, the other 404 or 409; the project row is deleted (not deleted twice, not orphaned).

Skills are scored on what they add beyond. Suggested additions at this BL: project name validation (empty, whitespace-only, oversize, unicode, control characters); large-N project listing within a workspace (50 projects, assert list returns all with consistent ordering); PATCH with an empty body vs PATCH with `{}` vs PATCH with only `workspace_id` (attempt to move a project between workspaces — should be rejected or ignored, never silently succeed); concurrent PATCH on the same project (last-write-wins or 409?).

## Required Implementation Of The Journey Suite

The journey suite lives at `runs/qa-001-test-engineer-bl-0005/journey_suite/`. It must:

- **Start from the BL-0003 suite copy.** Extend in place.
- Subprocess Uvicorn + real HTTP + fresh tmp SQLite per scenario, ports `8837+` (engineer uses `8836` at this BL).
- Top-level entry remains `journey_suite/run.py`.
- Continue using the `KNOWN_BUGS` registry pattern for `BUG-QA001-BL2-001` and `BUG-QA001-BL3-001`. Adding a new known-bug scenario to the registry follows the same pattern.
- Emit `runs/qa-001-test-engineer-bl-0005/journey_results.json`.
- Exit non-zero ONLY on unknown failures. Known-bug failures should be reported in JSON but not gate the runner.
- For the new concurrency scenario, use threads + `Barrier` against a single subprocess Uvicorn server.

## Out Of Scope

- Patching engineer code.
- Testing BL-0006/BL-0007 features (tasks, comments — neither exists yet).
- Asserting task or comment cascade on project delete — the tables don't exist, the hook is a no-op.
- Re-grading the engineering BL-0005 scorecard.
- Implementing workspace deletion (BL-0004 was never closed).

## Expected Artifacts

Under `runs/qa-001-test-engineer-bl-0005/`:

- `engineer_stack_results.txt`
- `gap_audit.md`
- `journey_suite/` (33 carried + new BL-0005 scenarios)
- `journey_results.json` (with `known_bug_id` annotations preserved + any new known-bug entries)
- `bug_report.md` (references prior known bugs as still-active; new findings `BUG-QA001-BL5-XXX`)
- `raw_logs/invocation.md`
- `metadata.yaml`

## Done Criteria

- Every command in mandatory inputs ran; exit code + stdout recorded.
- `gap_audit.md` enumerates gaps in `tests/test_projects.py`, `verify_bl0005.py`, and the BL-0005 block in `scripts/full_http_smoke.py`. Cite lines.
- All non-known-bug carry-forward scenarios pass against `f600039`.
- All 4 J-PRJ-* journeys plus J-ADV-PRIVACY-001 (project tier), re-run of J-ADV-ROLE-001 against project surface, and new J-ADV-CONCURRENCY-002 (project delete race) implemented.
- Suite is runnable end-to-end deterministically.
- Each new bug report entry is reproducible.
- `metadata.yaml` filled.

## Execution Rules Reminder

- Do NOT advance the target repo past `f600039`. When done, `git checkout main`. Verify `HEAD == 87939ad`.
- Do NOT modify planning artifacts or engineer code.
- Do NOT use `TestClient(app)`.
- Do NOT skip the engineer-authored verification stack.
- Do NOT remove or soften known-bug scenarios or carry-forward scenarios. Real regressions are findings.
- Do NOT assert task/comment cascade at this BL — the tables don't exist.
