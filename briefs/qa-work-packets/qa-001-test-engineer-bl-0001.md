# QA Work Packet: QA-001 BL-0001 Authentication Foundation

## Run

- Run ID: `qa-001-test-engineer-bl-0001`
- QA Skill: `qa-001-test-engineer`
- Target Repo: `target-repos/project-tracker-v1-engineering-baseline`
- Target Commit: `5baf798f2681745ab3ab551c576335da0ac84bee` (BL-0001 implementation plus the smoke runner; commit just before BL-0002 began)
- Engineering BL Under Test: `BL-0001`

## Objective

Gate the BL-0001 authentication foundation. Run the entire engineer-authored verification stack at this commit, audit it for gaps, build the **first cycle** of the accumulating QA journey suite — multi-feature, real-Uvicorn, real-HTTP E2E flows — and file bug reports for any finding.

This is the **first** QA cycle for `QA-001`. There is no carry-forward suite. The journey suite produced here becomes the seed for the BL-0002 cycle.

## Source Context

- Engineering work packet: `briefs/bl-0001-authenticated-account-foundation.md`
- Engineering run: `runs/eng-001-incremental-implementation/` (scorecard 64/75 Pass)
- QA evaluation protocol: `docs/qa_evaluation_protocol.md`
- QA journey catalogue: `docs/qa_journey_catalogue.md` (BL-0001 section)
- QA skill: `skills/qa/qa-001-test-engineer/SKILLS.md` (SHA-256 `1e6d69462066eac39c7f19f8ad13b527dc8db6c2266dc551b4002e99b8096745`)
- Carry-forward suite: none (first cycle)

## Mandatory Inputs The QA Agent Must Execute At Target Commit

Run these inside `target-repos/project-tracker-v1-engineering-baseline` after `git checkout 5baf798`. Capture exit code and verbatim stdout for each:

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl0001.py
.venv/bin/python scripts/full_http_smoke.py --port 8830
```

A non-zero exit from any of these is a finding. After capturing, return the repo to commit `5baf798` (do not advance it).

**Note**: at this commit there is no `verify_bl0002/0003/0005/0006/0007.py`, no `tests/test_members.py`, no `tests/test_projects.py`, no `tests/test_tasks.py`, no `tests/test_comments.py`, and no `models.py`/`schemas.py`/`security.py`/`database.py`/`routers/` split. The codebase is single-file `app.py`. Do not look for files that do not exist at this commit.

## In-Scope Feature Surface (BL-0001)

Verbatim from the engineering work packet's In Scope:

- User model with email and password hash.
- Password hashing via PBKDF2-SHA256 with per-user salt.
- `POST /signup` returning bearer token plus normalized user.
- `POST /login` returning bearer token.
- `GET /me` returning current user from bearer token.
- Email normalization to lowercase.
- Duplicate-email rejection.
- 401 on missing or invalid bearer.
- Plaintext-never-stored guarantee in SQLite.
- Pydantic email validation (422 on malformed).

Anything outside this surface is BL-0002+ and is not yet implemented.

## Required Journeys (from `docs/qa_journey_catalogue.md` BL-0001 section)

The accumulated journey suite for this cycle must include at minimum:

- **J-AUTH-001** Signup-login-me roundtrip with case-normalized email.
- **J-AUTH-002** Duplicate signup hardening.
- **J-AUTH-003** Login failure modes (wrong password, unknown email, malformed payload).
- **J-AUTH-004** Token negative space (no header, malformed bearer, truncated token).
- **J-AUTH-005** Persistence across Uvicorn restart against same DB file.
- **J-AUTH-006** Password storage probe via direct SQLite inspection (no plaintext, PBKDF2 hash format).

Plus applicable adversarial journeys:

- **J-ADV-INPUT-001** Malformed payload survives across signup, login, /me (malformed JSON, missing required fields, wrong content type, oversized payload — deterministic HTTP codes, no stack traces in body).

Skills are scored on what they add beyond. Suggested additions: header-case sensitivity, whitespace handling in emails, empty-password rejection, repeated rapid-fire signups for the same email, signup then immediately delete the DB file and assert behavior is deterministic.

## Required Implementation Of The Journey Suite

The journey suite lives at `runs/qa-001-test-engineer-bl-0001/journey_suite/`. It must:

- Use Python (the project's runtime) and have a single top-level entry point: `journey_suite/run.py`.
- Start the FastAPI app under subprocess Uvicorn against a fresh SQLite database — DO NOT use `TestClient(app)`.
- Use real HTTP (`urllib.request` or `httpx` — your choice) for every request.
- Obtain bearer tokens via real `/signup` and `/login` calls; never construct tokens by hand.
- Emit results as JSON to `runs/qa-001-test-engineer-bl-0001/journey_results.json` with the schema:
  ```json
  {
    "scenarios": [
      {"id": "J-AUTH-001", "title": "...", "passed": true, "duration_ms": 123, "steps": [...]},
      ...
    ],
    "total": N, "passed": N, "failed": M, "started_at": "...", "ended_at": "..."
  }
  ```
- Exit non-zero on any scenario failure.
- Be runnable from a fresh clone with `cd runs/qa-001-test-engineer-bl-0001/journey_suite && python run.py` (after the engineering target repo's `.venv` is on PATH or otherwise activated).

## Out Of Scope

- Patching engineer code. QA reports findings; engineering fixes.
- Testing BL-0002+ features (they do not exist at commit `5baf798`).
- Re-grading the engineering scorecard.

## Expected Artifacts

- `runs/qa-001-test-engineer-bl-0001/engineer_stack_results.txt`
- `runs/qa-001-test-engineer-bl-0001/gap_audit.md`
- `runs/qa-001-test-engineer-bl-0001/journey_suite/` (full implementation)
- `runs/qa-001-test-engineer-bl-0001/journey_results.json`
- `runs/qa-001-test-engineer-bl-0001/bug_report.md` (use the format in `docs/qa_evaluation_protocol.md`)
- `runs/qa-001-test-engineer-bl-0001/raw_logs/invocation.md`
- `runs/qa-001-test-engineer-bl-0001/metadata.yaml` per `templates/qa_work_packet_template.md` schema

## Done Criteria

- Every command in the mandatory inputs section ran and its exit code + stdout is recorded.
- `gap_audit.md` enumerates concrete gaps in the engineer-authored test/verifier/smoke coverage with file:line references where applicable.
- All required journeys (J-AUTH-001..006 and J-ADV-INPUT-001) implemented in the suite.
- Suite is runnable end-to-end against the target commit and produces a deterministic JSON result.
- Each bug report entry is reproducible from the steps given.
- `metadata.yaml` filled with `verification.engineer_stack_result`, `verification.journey_suite_result`, scenario counts, and severity-bucketed bug counts. Outcome left empty for scoring.

## Execution Rules Reminder

- Do NOT advance the target repo past commit `5baf798`.
- Do NOT modify `REQUIREMENTS.md`, `.agile-v/BACKLOG.md`, sprint plan, or any planning artifact.
- Do NOT use `TestClient(app)` in the journey suite — that is engineering's verification style, not QA's.
- Do NOT skip the engineer-authored verification stack.
- If a journey reveals a real BL-0001 defect, that is the desired outcome — file it. Do not soften journey assertions to "make tests pass."
