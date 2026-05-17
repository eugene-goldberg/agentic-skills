# QA Work Packet: QA-001 BL-0007 Task Comments For All Workspace Members

## Run

- Run ID: `qa-001-test-engineer-bl-0007`
- QA Skill: `qa-001-test-engineer`
- Target Repo: `target-repos/project-tracker-v1-engineering-baseline`
- Target Commit: `87939ad` (BL-0007 closing commit; current `main` HEAD)
- Engineering BL Under Test: `BL-0007`

## Objective

Final catch-up cycle for `QA-001`. Gate the BL-0007 task-comments surface, including the **viewer-mutation exception** (only viewer-can-mutate surface in v1), **author retention after removal**, and the **full project-delete cascade** (comments AND tasks both cleared — BL-0005 AC 7 now fully active). Carry forward the 62-scenario suite from BL-0006, add comment-surface journeys, and extend the three systemic-defect-class probes to the comment tier.

After this cycle scores Pass, `QA-001` becomes a forward gate on the engineering pipeline — the next engineering BL opens with QA gating built in from the start.

## Source Context

- Engineering work packet: `briefs/engineering-work-packets/bl-0007-task-comments-for-all-workspace-members.md`
- Engineering run: `runs/eng-001-incremental-implementation-bl-0007/` (scored Pass 74/75 — tied with BL-0006 for highest engineering score)
- Prior QA run: `runs/qa-001-test-engineer-bl-0006/` (scored Pass 74/75 + axes 40/40)
- QA evaluation protocol: `docs/qa_evaluation_protocol.md`
- QA journey catalogue: `docs/qa_journey_catalogue.md` (BL-0007 section)
- QA skill: `skills/qa/qa-001-test-engineer/SKILLS.md` (SHA-256 `1e6d69462066eac39c7f19f8ad13b527dc8db6c2266dc551b4002e99b8096745`)
- **Carry-forward suite**: `runs/qa-001-test-engineer-bl-0006/journey_suite/` — copy into `runs/qa-001-test-engineer-bl-0007/journey_suite/`.

## Special Note: Target Commit Is Currently `main` HEAD

This cycle's target commit `87939ad` is the **current `main` HEAD** of the engineering target repo. The QA agent does NOT need to `git checkout` — the repo is already at the target commit. Verify with `git rev-parse HEAD` → must equal `87939ad`. After the cycle finishes, no `git checkout` is needed either; the repo should be left at `87939ad` (the current `main` HEAD) with a clean working tree.

## Carry-Forward Expectations Regarding Known Bugs

Five known propagating bugs continue from prior cycles. Use the existing `KNOWN_BUGS` registry pattern.

- `BUG-QA001-BL2-001` (High) — `GET /workspaces/{2**63}` → 500 (Class A workspace tier).
- `BUG-QA001-BL3-001` (Critical) — concurrent dual-admin member-removal both 204 (Class B member tier).
- `BUG-QA001-BL5-001` (High) — `GET .../projects/{2**63}` → 500 (Class A project tier).
- `BUG-QA001-BL5-002` (High) — concurrent dual-admin project-delete both 204 (Class B project tier).
- `BUG-QA001-BL6-001` (High) — `GET .../tasks/{2**63}` → 500 (Class A task tier).

Plus `BUG-QA001-BL6-002` (Low positive observation — Class B did NOT recur at task tier) carried as a passing-by-default scenario.
Plus `BUG-QA001-BL6-003` (Medium) — whitespace task title bypasses `min_length=1` (Class C, task tier).

Do NOT re-file. Reference in `bug_report.md`. New findings get `BUG-QA001-BL7-XXX` IDs.

## Mandatory Inputs The QA Agent Must Execute At Target Commit

Inside `target-repos/project-tracker-v1-engineering-baseline` at `87939ad`:

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl0001.py
.venv/bin/python verify_bl0002.py
.venv/bin/python verify_bl0003.py
.venv/bin/python verify_bl0005.py
.venv/bin/python verify_bl0006.py
.venv/bin/python verify_bl0007.py
.venv/bin/python scripts/full_http_smoke.py --port 8840
```

Capture exit code + verbatim stdout. Non-zero exit is a finding.

Pytest should be 88 at this commit. Six BL verifiers (`verify_bl0001..0007.py`).

## In-Scope Feature Surface (BL-0007)

- `Comment` model with `task_id` FK, `author_email` (no FK to users), `body` (cap 4096), `created_at`. No edit/delete endpoints in v1.
- `POST /workspaces/{ws}/projects/{pid}/tasks/{tid}/comments` — **any workspace member including viewer**; non-member → 404; missing token → 401.
- `GET .../comments` — any workspace member; non-member → 404. Ordering: `created_at` ascending.
- Empty body, whitespace-only body, oversize body → 400 (engineer's chosen code from BL-0006).
- Task-delete cascade now removes comments.
- Project-delete cascade now removes both tasks AND comments (BL-0005 AC 7 fully active; engineering replaced the defensive `comments.project_id` branch with a task-mediated cascade).
- Comments persist after author is removed from workspace (REQ-0017 done criteria; original `author_email` preserved).

Inherited BL-0001/0002/0003/0005/0006 surfaces remain in scope.

## Required Journeys

### Carry-forward (must continue to pass against `87939ad`, except known bugs)

All 62 scenarios from the BL-0006 cycle. The 5 known bugs continue to fail. The BL-0006 positive-observation scenario continues to pass.

### New required (from `docs/qa_journey_catalogue.md` BL-0007 section)

- **J-COM-001** Viewer mutation exception — workspace with C viewer → C creates comment on a task → 201, comment appears in list → C attempts to mutate the task → 403. The exception is comment-create only, nothing else.
- **J-COM-002** Cross-actor comment list — A admin, B editor, C viewer all post comments → any lists comments → all three present, ordered by `created_at` ascending → non-member X → 404 with no comment text or count leak.
- **J-COM-003** Validation rejection — empty body → 400, whitespace-only body → 400, body of length `COMMENT_BODY_MAX + 1` → 400, body exactly at cap → 201. **This is the Class C probe at the comment tier — if engineering centralized the strip-after-validate fix, whitespace-only must return 400 (not 201 storing empty string).**
- **J-COM-004** Author retention after removal — C viewer posts comment → A removes C → comment list still includes the comment with original `author_email` → C cannot list (404), A and B see C's comment intact.
- **J-COM-005** Task delete cascades comments — task with several comments → delete task → comments gone from DB → other tasks' comments untouched.
- **J-COM-006** Project delete cascades both (BL-0005 AC 7 fully active) — project with tasks and comments → delete project → all comments AND all tasks for that project gone from DB → other projects untouched.
- **J-COM-007** No cross-task comment leak — comment on task T1 not in T2's list, even within same project.

### Cross-BL adversarial (next tier for systemic defect classes)

- **NEW J-ADV-OVERFLOW-COMMENT-001** Class A at comment tier — `GET .../tasks/{tid}/comments` where the path contains a huge ID at any segment (workspace, project, task) — already covered by prior cycles for workspace/project/task IDs. **New probe**: if a future endpoint accepts a `comment_id` path parameter (none in v1), test the huge ID. Since v1 has no comment-id path endpoint, the formal Class A probe at comment tier is N/A — document this fact in the bug report.
- **NEW J-ADV-CLASSC-COMMENT-001** Class C at comment tier — `POST .../comments` with body `"   "` (whitespace only). Per the packet, engineer is supposed to reject with 400. **If engineering centralized the strip-after-validate fix, this passes**; **if Class C recurs at comment tier**, file as `BUG-QA001-BL7-XXX`.
- **NEW J-ADV-CASCADE-FULL-001** Full project-delete cascade integrity — create workspace with 3 projects, each with 5 tasks, each with 4 comments → delete one project → assert DB row counts: that project's tasks AND comments are gone; other projects' tasks AND comments untouched; member rows preserved. This finalizes the BL-0005 AC 7 verification.
- **NEW J-ADV-AUTHOR-PERSIST-001** Author retention at scale — multiple removed authors across multiple workspaces; assert all their historical comments persist intact with original `author_email`; new comments by re-added users do not somehow merge with old comments.

### Cross-BL adversarial (carry-forward; continue to apply)

- **J-ADV-PRIVACY-001 (comment tier)** Extend existence-leak sweep to comment endpoints. Non-member POST and GET on comments → 404 byte-identical to operations against non-existent task/project/workspace IDs.
- **J-ADV-ROLE-001 (re-run against comment surface)** Stale token after role change applied to comment endpoints. Stale-token comment-create should NOT succeed.
- **J-ADV-CONCURRENCY-COMMENT-001 (new)** Class B at comment tier. v1 has no comment-delete endpoint, so the classic dual-admin race is N/A. **However**, concurrent comment-create from two threads as the same viewer — assert both succeed deterministically with distinct IDs, no constraint violations, no orphans. This is the closest analog at the comment tier.

Skills are scored on what they add beyond. Suggested additions: comment body with unicode emoji + RTL text; comment body with embedded null bytes (do they survive SQLite roundtrip?); concurrent comment-create + task-delete race (comment created on a task that's being deleted — does it orphan?); list-comments while a thread concurrently posts (consistent snapshot or interleaved view?).

## Required Implementation Of The Journey Suite

The journey suite lives at `runs/qa-001-test-engineer-bl-0007/journey_suite/`. It must:

- **Start from the BL-0006 suite copy.** Extend in place.
- Subprocess Uvicorn + real HTTP + fresh tmp SQLite per scenario, ports `8841+` (engineer uses `8840` at this BL).
- Continue using `KNOWN_BUGS` registry. The 5 propagating known bugs continue to fail; report in JSON but do not gate exit code.
- Pass all non-known-bug carry-forward scenarios.
- Add all 7 J-COM-* journeys plus the new adversarial scenarios.
- Add at least 2 beyond-minimum scenarios.
- Remain deterministic.
- Emit `runs/qa-001-test-engineer-bl-0007/journey_results.json`.
- Exit non-zero ONLY on unknown failures.

## Out Of Scope

- Patching engineer code.
- Testing features beyond BL-0007 (workspace deletion, `/me/tasks`, summary — none closed yet).
- Implementing comment edit/delete (engineering deliberately did not).
- Re-grading the engineering BL-0007 scorecard.
- Implementing centralized fixes for Class A or Class B — finding parity is the deliverable; remediation is engineering's call.

## Expected Artifacts

Under `runs/qa-001-test-engineer-bl-0007/`:

- `engineer_stack_results.txt`
- `gap_audit.md`
- `journey_suite/` (62 carried + new BL-0007 scenarios)
- `journey_results.json`
- `bug_report.md` (references 5 prior known bugs + 1 positive obs + Class C task-tier as still-active; new findings `BUG-QA001-BL7-XXX`)
- `raw_logs/invocation.md`
- `metadata.yaml`

## Done Criteria

- Every command in mandatory inputs ran; exit code + stdout recorded.
- `gap_audit.md` enumerates gaps in `tests/test_comments.py`, `verify_bl0007.py`, the BL-0007 block in `scripts/full_http_smoke.py`, and any extension to BL-0005/0006 verifiers for the activated cascade.
- All 7 J-COM-* journeys plus the new adversarial scenarios implemented.
- Suite is runnable end-to-end deterministically.
- Class C status at comment tier explicitly resolved: confirmed centralized fix OR confirmed recurrence.
- Each new bug report entry is reproducible.
- `metadata.yaml` filled.

## Execution Rules Reminder

- Target commit is `87939ad` which is the current `main` HEAD. NO `git checkout` needed at start; NO restore needed at end. Verify HEAD before and after.
- Do NOT modify planning artifacts or engineer code.
- Do NOT use `TestClient(app)` in the journey suite.
- Do NOT skip the engineer-authored verification stack.
- Do NOT remove or soften known-bug or carry-forward scenarios.
- Class A and Class C recurrence at comment tier are NOT predicted — engineering may or may not have centralized either. If they recur, file as new bugs; if they do not, document as positive observations.
- This is the final catch-up cycle. After scoring, `QA-001` becomes a forward gate.
