# QA Work Packet: QA-001 BL-0002 Workspace Privacy Boundary

## Run

- Run ID: `qa-001-test-engineer-bl-0002`
- QA Skill: `qa-001-test-engineer`
- Target Repo: `target-repos/project-tracker-v1-engineering-baseline`
- Target Commit: `c5e89e370cfd2ea79de9da885e5e4c2632e71a98` (BL-0002 closing commit)
- Engineering BL Under Test: `BL-0002`

## Objective

Gate the BL-0002 workspace creation, listing, detail, and cross-tenant privacy boundary. Run the engineer-authored verification stack at this commit, audit gaps, **carry forward the 11-scenario BL-0001 journey suite**, add workspace-specific journeys, and confirm the prior-cycle scenarios still pass against this commit. File bug reports for any finding.

This is QA cycle 2 of 6 for `QA-001`. The accumulated suite is the deliverable that grows across all six cycles.

## Source Context

- Engineering work packet: `briefs/engineering-work-packets/bl-0002-workspace-privacy-boundary.md`
- Engineering run: `runs/eng-001-incremental-implementation-bl-0002/` (scorecard 66/75 Pass)
- Prior QA run: `runs/qa-001-test-engineer-bl-0001/` (scored Pass 74/75)
- QA evaluation protocol: `docs/qa_evaluation_protocol.md`
- QA journey catalogue: `docs/qa_journey_catalogue.md` (BL-0002 section)
- QA skill: `skills/qa/qa-001-test-engineer/SKILLS.md` (SHA-256 `1e6d69462066eac39c7f19f8ad13b527dc8db6c2266dc551b4002e99b8096745`)
- **Carry-forward suite**: `runs/qa-001-test-engineer-bl-0001/journey_suite/` — copy into `runs/qa-001-test-engineer-bl-0002/journey_suite/` as the starting point.

## Mandatory Inputs The QA Agent Must Execute At Target Commit

Inside `target-repos/project-tracker-v1-engineering-baseline` after `git checkout c5e89e3`:

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl0001.py
.venv/bin/python verify_bl0002.py
.venv/bin/python scripts/full_http_smoke.py --port 8832
```

A non-zero exit from any of these is a finding. Capture exit code + verbatim stdout for each.

**Note**: at `c5e89e3` the only test file is `tests/test_auth.py` (which contains both auth and workspace tests at this commit). No `tests/test_members.py`, no router split, no `models.py`. `app.py` is single-file. Do not look for files that do not exist at this commit.

## In-Scope Feature Surface (BL-0002)

Verbatim from the engineering work packet's In Scope:

- Workspace persistence (workspace model with name).
- Workspace membership persistence sufficient for creator-as-admin.
- `POST /workspaces` — authenticated users only.
- `GET /workspaces` — lists only the caller's workspaces.
- `GET /workspaces/{ws_id}` — workspace detail for members.
- Bearer auth required for all workspace endpoints (401 on missing/invalid token).
- Non-member workspace detail returns `404` (not `403`).
- No workspace data leaks to non-members.

BL-0001 surface (auth) remains in scope as inherited; QA-001 BL-0001's 11 scenarios must continue to pass against `c5e89e3`.

## Required Journeys

### Carry-forward (must continue to pass against `c5e89e3`)

All 11 scenarios from the BL-0001 suite. If any regress against this commit, **that is the desired outcome of suite continuity** — file the regression as a finding, do not soften the scenario.

### New required (from `docs/qa_journey_catalogue.md` BL-0002 section)

- **J-WS-001** Creator becomes admin (signup → create workspace → 201 → GET /workspaces returns it with role:admin → GET /workspaces/{id} returns detail).
- **J-WS-002** Cross-user invisibility (signup A and B → A creates workspace → B's list is empty → B's detail returns 404 with no name/description leak in body or headers).
- **J-WS-003** Token required on workspace endpoints (every workspace endpoint with no bearer → 401; with malformed bearer → 401).
- **J-WS-004** Multi-workspace isolation (A creates ws1, A creates ws2, B creates ws3 → A's list = ws1+ws2 only, B's list = ws3 only, with correct roles).
- **J-WS-005** Inherited BL-0001 invariants under workspace use (after creating workspaces, `/me`, `/login`, `/signup` still behave per BL-0001 journeys — this is a composition test, not just re-running J-AUTH-* in isolation).

### Adversarial (applicable now that workspace surface exists)

- **J-ADV-PRIVACY-001 (workspace tier)** Existence-leak sweep on workspace-scoped resources at this BL: non-member `GET /workspaces/{ws_id}` for an existing workspace returns 404 with response body containing nothing that distinguishes "exists in another workspace" from "does not exist." Compare response body byte-for-byte against a `GET /workspaces/{non_existent_id}` request — they should be indistinguishable.

Skills are scored on what they add beyond. Suggested additions for this BL: workspace name validation (empty, whitespace-only, oversize, unicode), `Content-Type` negotiation, workspace ID type confusion (string vs int vs UUID-looking value), duplicate workspace name handling (currently no constraint — verify behavior is deterministic), large-N workspace listing (create 50 workspaces, assert list returns all of them with consistent ordering).

## Required Implementation Of The Journey Suite

The journey suite lives at `runs/qa-001-test-engineer-bl-0002/journey_suite/`. It must:

- **Start from the BL-0001 suite copy.** First action: copy `runs/qa-001-test-engineer-bl-0001/journey_suite/` to `runs/qa-001-test-engineer-bl-0002/journey_suite/`. Then extend.
- Use the same architectural rules as BL-0001: subprocess Uvicorn, real HTTP, fresh tmp SQLite per scenario, dynamic ports starting at `8833` (port `8832` is reserved for the engineer smoke at this BL). Reuse the helper functions from the BL-0001 suite.
- Top-level entry remains `journey_suite/run.py`. Add the new scenarios to the existing runner.
- Emit results to `runs/qa-001-test-engineer-bl-0002/journey_results.json`.
- Exit non-zero on any scenario failure.

## Out Of Scope

- Patching engineer code.
- Testing BL-0003+ features (member management, projects, tasks, comments — none exist at `c5e89e3`).
- Re-grading the engineering BL-0002 scorecard.

## Expected Artifacts

Under `runs/qa-001-test-engineer-bl-0002/`:

- `engineer_stack_results.txt`
- `gap_audit.md`
- `journey_suite/` (BL-0001 11 scenarios + new BL-0002 scenarios)
- `journey_results.json`
- `bug_report.md`
- `raw_logs/invocation.md`
- `metadata.yaml`

## Done Criteria

- Every command in mandatory inputs ran; exit code + stdout recorded.
- `gap_audit.md` enumerates gaps in `tests/test_auth.py` (BL-0002 portion), `verify_bl0002.py`, and the BL-0002 block in `scripts/full_http_smoke.py`. Cite line numbers.
- All 11 BL-0001 scenarios still pass against `c5e89e3` (if not, regressions filed as findings).
- All 5 new required journeys (J-WS-001..005) and J-ADV-PRIVACY-001 implemented and passing.
- Suite is runnable end-to-end deterministically.
- Each bug report entry is reproducible.
- `metadata.yaml` filled with engineer-stack result, journey suite result, scenario counts (total = BL-0001 carry-forward + BL-0002 additions), and severity-bucketed bug counts. Outcome left empty for scoring.

## Execution Rules Reminder

- Do NOT advance the target repo past `c5e89e3`. When done, `git checkout main` to restore to `87939ad`. Verify `git rev-parse HEAD == 87939ad`.
- Do NOT modify planning artifacts or engineer code.
- Do NOT use `TestClient(app)`.
- Do NOT skip the engineer-authored verification stack.
- Do NOT soften BL-0001 carry-forward scenarios to make them pass — a real regression is a finding.
