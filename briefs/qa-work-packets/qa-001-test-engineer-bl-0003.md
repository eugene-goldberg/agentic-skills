# QA Work Packet: QA-001 BL-0003 Workspace Member Management And Role Matrix

## Run

- Run ID: `qa-001-test-engineer-bl-0003`
- QA Skill: `qa-001-test-engineer`
- Target Repo: `target-repos/project-tracker-v1-engineering-baseline`
- Target Commit: `a898011` (BL-0003 closing commit — docstring fix on top of `a10ed95`)
- Engineering BL Under Test: `BL-0003`

## Objective

Gate the BL-0003 workspace member management and role matrix. Carry forward the 20-scenario suite from the BL-0002 cycle, add member-management journeys, and exercise the cross-BL adversarial journeys that become applicable now that role enforcement and member mutation exist.

This is QA cycle 3 of 6 for `QA-001`.

## Source Context

- Engineering work packet: `briefs/engineering-work-packets/bl-0003-workspace-member-management-and-role-matrix.md`
- Engineering run: `runs/eng-001-incremental-implementation-bl-0003/` (scored Pass 72/75)
- Prior QA run: `runs/qa-001-test-engineer-bl-0002/` (scored Pass 74/75 + axes 40/40)
- QA evaluation protocol: `docs/qa_evaluation_protocol.md`
- QA journey catalogue: `docs/qa_journey_catalogue.md` (BL-0003 section)
- QA skill: `skills/qa/qa-001-test-engineer/SKILLS.md` (SHA-256 `1e6d69462066eac39c7f19f8ad13b527dc8db6c2266dc551b4002e99b8096745`)
- **Carry-forward suite**: `runs/qa-001-test-engineer-bl-0002/journey_suite/` — copy into `runs/qa-001-test-engineer-bl-0003/journey_suite/`.

## Carry-Forward Expectation Regarding `BUG-QA001-BL2-001`

The huge-ID 500 scenario from the BL-0002 cycle is **expected to continue failing** against `a898011`. Engineering has not remediated this defect; the bug propagates forward. Filing it again as a finding is appropriate — every cycle from BL-0002 forward continues to surface this until fixed. This is correct gate behavior, **not a suite regression**.

In `bug_report.md`, reference `BUG-QA001-BL2-001` and note that the scenario remains failing against this BL's commit. Do NOT remove the scenario or soften its assertions. New unique findings get new bug IDs (e.g., `BUG-QA001-BL3-001` onward).

## Mandatory Inputs The QA Agent Must Execute At Target Commit

Inside `target-repos/project-tracker-v1-engineering-baseline` after `git checkout a898011`:

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl0001.py
.venv/bin/python verify_bl0002.py
.venv/bin/python verify_bl0003.py
.venv/bin/python scripts/full_http_smoke.py --port 8834
```

A non-zero exit from any of these is a finding. Capture exit code + verbatim stdout per command.

**Note at `a898011`**: `tests/test_auth.py` and `tests/test_members.py` exist. `verify_bl0001/0002/0003.py` exist. `app.py` is still single-file (refactor lands at BL-0006). `routers/`, `models.py`, etc. do not exist yet.

## In-Scope Feature Surface (BL-0003)

Verbatim from the engineering work packet's In Scope:

- Persist workspace memberships with one of `admin`, `editor`, `viewer`.
- `POST /workspaces/{ws_id}/members` — admin-only add by email with role.
- `DELETE /workspaces/{ws_id}/members/{email}` — admin-only remove.
- Reject removing the last admin (engineering chose `409 Conflict`).
- Return `403` when a non-admin member attempts member management.
- Return `404` when a non-member attempts member management (privacy parity with BL-0002).
- Allow added members to access the workspace per BL-0002 listing/detail rules.
- Require bearer auth on all member-management endpoints (401 on missing).

Inherited BL-0001 and BL-0002 surfaces remain in scope.

## Required Journeys

### Carry-forward (must continue to pass against `a898011`, except `BUG-QA001-BL2-001`)

All 20 scenarios from the BL-0002 cycle. The huge-ID scenario continues to fail as documented above; no other BL-0001 or BL-0002 scenario should regress. Any new regression is a finding.

### New required (from `docs/qa_journey_catalogue.md` BL-0003 section)

- **J-MEM-001** Admin add member with each role (admin adds B as `viewer`, C as `editor`, D as `admin` → each sees workspace with correct role).
- **J-MEM-002** Non-admin member 403 (admin A, editor B, viewer C → B and C each attempt add member → 403 → A still can).
- **J-MEM-003** Non-member 404 with no leak (X attempts member-add → 404, response body contains no workspace identifier or name).
- **J-MEM-004** Missing token 401 on member endpoints.
- **J-MEM-005** Last-admin removal rejected (A sole admin → A attempts to remove A → 409 → membership preserved).
- **J-MEM-006** Remove and re-add lifecycle (A removes B → B's list empty, detail 404 → A re-adds B as viewer → B sees workspace with role viewer).
- **J-MEM-007** Role change via remove-and-readd (engineering did not implement role-change endpoints; verify that the resulting role after re-add is the new role, not the prior role).

### Cross-BL adversarial (now applicable)

- **J-ADV-PRIVACY-001 (member tier)** Extend the existence-leak sweep to member endpoints. Non-member attempting `POST .../members` and `DELETE .../members/{email}` returns 404 with response body byte-identical (modulo volatile headers) to the same operation against a non-existent workspace ID.
- **J-ADV-ROLE-001 Stale token after role change**: B is an editor in workspace W with token `T`. A removes B from W. B still presents `T`. Every workspace-scoped endpoint (workspace detail, member add, member remove) using `T` against W must return a deterministic non-200 — preferably 404 to preserve existence-leak parity, but 401 is also acceptable if the engineer's design rejects the token outright. **If any returns 200, file as a privacy finding.**
- **J-ADV-CONCURRENCY-001 (BL-0003+)**: workspace with two admins A1 and A2. A1 and A2 each issue `DELETE /workspaces/{ws}/members/{other}` near-simultaneously (use Python threads). The last-admin invariant must hold: exactly one removal succeeds, the surviving admin's membership is preserved. **If both succeed and the workspace ends with zero admins, file as a critical data-integrity finding.**

Skills are scored on what they add beyond. Suggested additions for this BL: case-sensitivity on email lookup in member operations, role string validation (`Admin`, `ADMIN`, `superadmin` — what does the API accept?), member-add for self (admin adding themselves with a different role), member-remove with a path email that doesn't exist in the workspace, large-N members (add 100, list, remove all but one admin).

## Required Implementation Of The Journey Suite

The journey suite lives at `runs/qa-001-test-engineer-bl-0003/journey_suite/`. It must:

- **Start from the BL-0002 suite copy.** Extend in place.
- Subprocess Uvicorn + real HTTP + fresh tmp SQLite per scenario, ports `8835+` (engineer uses `8834` at this BL).
- Top-level entry remains `journey_suite/run.py`.
- Emit `runs/qa-001-test-engineer-bl-0003/journey_results.json`.
- Exit non-zero on any scenario failure EXCEPT the `BUG-QA001-BL2-001` huge-ID scenario, which is expected to fail and should be marked as a known-bug repro in `journey_results.json` (e.g., `"known_bug_id": "BUG-QA001-BL2-001"`). The runner's exit code logic should treat known-bug failures as non-fatal for suite continuity tracking, but the scenario must still execute and the failure must be captured.
- For the concurrency scenario, use Python's `threading` module against a single subprocess Uvicorn server.

## Out Of Scope

- Patching engineer code.
- Testing BL-0005+ features (projects, tasks, comments — none exist at `a898011`).
- Re-grading the engineering BL-0003 scorecard.
- Implementing a role-change endpoint (engineering did not, deliberately).

## Expected Artifacts

Under `runs/qa-001-test-engineer-bl-0003/`:

- `engineer_stack_results.txt`
- `gap_audit.md`
- `journey_suite/` (20 carried + new BL-0003 scenarios)
- `journey_results.json` (with known-bug annotation for the huge-ID scenario)
- `bug_report.md` (references `BUG-QA001-BL2-001` as still-active; new findings get `BUG-QA001-BL3-XXX` IDs)
- `raw_logs/invocation.md`
- `metadata.yaml`

## Done Criteria

- Every command in mandatory inputs ran; exit code + stdout recorded.
- `gap_audit.md` enumerates gaps in `tests/test_members.py`, `verify_bl0003.py`, and the BL-0003 block in `scripts/full_http_smoke.py`.
- All carry-forward scenarios still pass against `a898011` EXCEPT the known-bug huge-ID scenario.
- All 7 J-MEM-* journeys plus J-ADV-PRIVACY-001 (member tier), J-ADV-ROLE-001, J-ADV-CONCURRENCY-001 implemented and run.
- Suite is runnable end-to-end deterministically.
- Each new bug report entry is reproducible.
- `metadata.yaml` filled.

## Execution Rules Reminder

- Do NOT advance the target repo past `a898011`. When done, `git checkout main`. Verify `HEAD == 87939ad`.
- Do NOT modify planning artifacts or engineer code in the target repo.
- Do NOT use `TestClient(app)`.
- Do NOT skip the engineer-authored verification stack.
- Do NOT remove or soften the `BUG-QA001-BL2-001` huge-ID scenario.
- Do NOT soften BL-0001/0002 carry-forward scenarios to make them pass — a real regression is a finding.
