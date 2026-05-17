# QA Evaluation Protocol

This protocol governs every QA candidate evaluation cycle. It pairs with `docs/full_cycle_execution_protocol.md` (the engineering protocol) and `docs/skill_evaluation_plan.md` (the overall comparison methodology). It is mandatory: a QA candidate that does not follow the cycle shape below cannot be scored.

## Core Principle

**QA fires after each engineering BL closes, against that BL's closing commit, and is a gate on the engineering pipeline.** A BL is not truly closed until both engineering and QA have scored `Pass` against it.

This means each QA candidate produces **N consecutive QA cycles**, one per closed engineering BL, in the order engineering closed them. Each cycle uses the engineering commit at which the corresponding BL was scored. Each cycle is independently scored. The QA candidate's journey suite carries forward across cycles — a regression introduced by a later engineering BL must be caught by the existing journey suite, not waited on for a future cycle.

## Cycle Inputs

Per QA cycle, the QA candidate receives:

- The selected QA skill (snapshotted and hashed under `skills/qa/<skill-id>/SKILLS.md`).
- The target repo at the engineering BL's closing commit.
- The engineering work packet that produced that commit (for context on intent and scope).
- The full engineer-authored verification stack at that commit: `tests/test_*.py`, all `verify_bl*.py` files, and `scripts/full_http_smoke.py`.
- The accumulated QA journey suite from the QA candidate's prior cycle (if any).
- A QA work packet (see `templates/qa_work_packet_template.md`) listing the in-scope feature surface, required journeys per `docs/qa_journey_catalogue.md`, verification commands, and quality bar.

## Cycle Deliverables

Every QA cycle must produce, in this order of priority:

### 1. Engineer-stack execution report

The QA candidate runs the **entire engineer-authored verification stack** as-is, captures exact stdout, and reports pass/fail per command. This is non-negotiable input, not a deliverable to be skipped. The QA candidate is allowed and expected to add new pytest cases, smoke checks, or verifier assertions to those files when they identify gaps — committed alongside the engineer's code.

### 2. Gap audit

A written analysis of what the engineer's verification stack does NOT cover. Categories to consider at minimum:

- Negative/adversarial inputs the engineer skipped.
- Cross-feature state interactions the engineer tested in isolation but not in combination.
- Role/auth boundary cases not exercised.
- Cross-tenant ID confusion paths.
- Token lifecycle edge cases.
- Cascade/data-integrity invariants under unusual orderings.
- HTTP-level concerns: header handling, malformed JSON, content-type negotiation.

### 3. QA-owned E2E journey suite

The center of the deliverable. Lives under `runs/<qa-run-id>/journey_suite/`. Must satisfy:

- **Real deployment**: starts the FastAPI app under `python -m uvicorn app:app` in a subprocess on a fresh SQLite database. No `TestClient(app)` in-process shortcuts.
- **Real HTTP**: every step uses the actual network stack (urllib, httpx, requests — skill's choice). Bearer tokens obtained via real `/signup` and `/login` calls.
- **Multi-feature composition**: each scenario exercises at least two features in a single flow, with state evolving between steps and verified at each step.
- **Self-contained runner**: a single command runs the entire accumulated suite and exits non-zero on any failure. Output is JSON-parseable per scenario.
- **Continuity across cycles**: the suite from cycle N is the starting point for cycle N+1. Earlier scenarios must continue to pass against later engineering commits; if they don't, that is a finding to be filed.
- **Deterministic**: re-running against the same commit gives the same result.

The journey suite must cover, at minimum, the required journeys listed in `docs/qa_journey_catalogue.md` for the BL under test. Skills are scored on what they add beyond the minimum.

### 4. Bug report

One entry per finding, regardless of which probe surfaced it (engineer stack, gap audit, or journey suite). Each entry must include:

- Title (one line).
- Severity: `critical`, `high`, `medium`, `low`, `cosmetic`.
- Category: e.g., `privacy_leak`, `role_bypass`, `cascade_gap`, `validation_hole`, `regression`, `cross_tenant`, `auth`, `data_integrity`, `api_contract`.
- Affected endpoint(s) and HTTP method(s).
- Reproduction steps: exact commands or HTTP requests with payloads.
- Expected behavior with reference to the relevant REQ or BL acceptance criterion.
- Observed behavior with verbatim output.
- Evidence: response bodies, log lines, DB row dumps.
- Suggested fix location: file and approximate line range.

False positives (claimed bugs that aren't) are scored against the QA candidate. Findings that turn out to be intended behavior should be reclassified as "noise" before final submission, not after.

## Cycle Step-By-Step

1. **Select candidate.** Take the next `Queued` QA candidate from `docs/progress_tracker.md`.
2. **Inspect candidate source.** Find all plausible QA-relevant `SKILLS.md` files in the source repo. Select exactly one per the candidate-evaluation rules in `docs/skill_evaluation_plan.md`.
3. **Snapshot skill.** Copy into `skills/qa/<skill_id>/SKILLS.md`. Hash with SHA-256. Record source repo, original path, source commit, and hash.
4. **Identify the BL sequence.** Build the ordered list of engineering BL closing commits in the order engineering closed them. Each becomes one QA cycle in order.
5. **For each engineering BL in that sequence, run one QA cycle:**
   1. Author the QA work packet for this BL from `templates/qa_work_packet_template.md`. Reference `docs/qa_journey_catalogue.md` for required journeys at this BL.
   2. Create `runs/<qa-run-id>/` with `journey_suite/`, `output_artifacts/`, `raw_logs/`.
   3. Carry forward the journey suite from the prior cycle (copy or symlink) so accumulation is automatic.
   4. Hand the QA agent: the SKILLS.md, the QA work packet, the engineering work packet for context, the target commit, and the accumulated journey suite.
   5. QA agent executes the layered deliverable.
   6. Capture all outputs to the run directory.
   7. Score with `templates/qa_scorecard_template.md` against the dimensions in this protocol's "Scoring" section.
   8. Update `docs/progress_tracker.md` with the cycle result.
   9. Do not start the next BL's QA cycle until this one is `Scored`, `Blocked`, or `Skipped`.

## Scoring

Use the rubric in `rubrics/production_grade_scorecard.md` for the existing QA-specific dimensions (`Test strategy`, `Bug discovery`, `Reproducibility`, `Regression value`, `Noise control`). Add the following QA-specific scoring axes, each 0-5:

| Axis | What It Measures |
|---|---|
| Journey depth | Average number of meaningful state-changing steps per scenario; does the suite compose features? |
| Journey breadth | Coverage across feature surfaces × user roles × failure modes |
| Real-deployment fidelity | Suite uses subprocess Uvicorn + real HTTP + fresh DB on every run |
| Engineer-stack execution | Ran entire engineer stack, reported results, identified gaps |
| Suite continuity | Prior-cycle scenarios still pass; failures triaged as findings not as suite breakage |
| Suite growth | New scenarios added per cycle, weighted by depth and category coverage |
| Found-without-being-told | Bugs surfaced by the suite or audit, not from inspecting the engineering work packet for hints |
| Repro reliability | Re-running each reported repro reproduces the stated failure |

## Failure Modes Specific To QA

Add these labels to the existing failure-mode vocabulary when scoring QA cycles:

- `inferred_instead_of_executed` — skill described what it would test without running it.
- `engineer_stack_skipped` — engineer-authored tests/verifiers/smoke not run.
- `in_process_only` — journey suite uses `TestClient(app)` exclusively instead of real HTTP.
- `single_feature_only` — no multi-feature scenario in journey suite.
- `suite_not_runnable` — accumulated suite does not execute end-to-end on a fresh clone.
- `unreproducible_finding` — reported bug cannot be reproduced from the steps given.
- `noise_excess` — false-positive findings dominate the report.

## Cross-Skill Comparison

Two QA candidate skills are comparable only if both have completed the same ordered sequence of engineering BL closing commits. Comparing `QA-001` after 3 BLs to `QA-002` after 5 BLs is not a valid comparison.

When comparing finalists, optionally re-run each against a **seeded-defect mutation set** applied to the most recent engineering closing commit. The mutation set lives at `rubrics/qa_defect_seeding_plan.md` (to be authored) and is hidden from the QA candidate. Precision/recall against the seeded set becomes an additional axis for finalist comparison; it does not replace the per-BL cycle scoring.

## Open Items For Future Tightening

- Define the seeded-defect mutation set in `rubrics/qa_defect_seeding_plan.md`.
- Decide a uniform time/token budget per QA cycle once we have data from `QA-001`.
- Decide whether QA findings that surface real engineering bugs trigger re-opening of the engineering BL's scorecard or are tracked separately.
