# QA Work Packet Template

Use this template to author one QA work packet per engineering BL closing commit. Each packet drives exactly one QA cycle.

## Run

- Run ID: `qa-<NNN>-<skill-id>-bl-<BBBB>`
- QA Skill: `<skill_id>`
- Target Repo: `target-repos/project-tracker-v1-engineering-baseline`
- Target Commit: `<engineering BL closing commit SHA>`
- Engineering BL Under Test: `BL-<BBBB>`

## Objective

State, in one paragraph, what feature surface this QA cycle is gating and what new journeys must be added relative to the prior cycle.

## Source Context

- Engineering work packet: `briefs/engineering-work-packets/bl-<BBBB>-*.md`
- Engineering scorecard: `runs/eng-<NNN>-<skill>-bl-<BBBB>/scorecard.md`
- QA evaluation protocol: `docs/qa_evaluation_protocol.md`
- QA journey catalogue: `docs/qa_journey_catalogue.md`
- Carry-forward journey suite: `runs/<prior-qa-run-id>/journey_suite/` (or `none` if this is the first cycle)

## Mandatory Inputs The QA Agent Must Execute

The QA agent must run the entire engineer-authored verification stack at the target commit and report each result with verbatim stdout:

- `.venv/bin/python -m py_compile app.py`
- `.venv/bin/python -m pytest -q`
- For each `verify_bl*.py` present at the target commit: `.venv/bin/python verify_bl<NNNN>.py`
- `.venv/bin/python scripts/full_http_smoke.py --port <unique port>`

A failure here is a finding. The QA agent does not skip these.

## In-Scope Feature Surface

List the HTTP endpoints, models, and behaviors introduced or modified by this BL. Reference the engineering work packet's "In Scope" section verbatim; do not re-paraphrase.

## Required Journeys

Reference the journeys listed in `docs/qa_journey_catalogue.md` for this BL. List them by ID and state any BL-specific parameters (port, target commit, prior-suite carry-forward).

The QA agent must implement and run **at least** these journeys plus all prior-BL journeys it inherited. Skills are scored on what they add beyond.

## Required Cross-BL Adversarial Journeys

List the `J-ADV-*` journeys from the catalogue that apply at this BL (presence of the target features is the criterion).

## Out Of Scope

- Implementation work beyond writing tests, journey runners, and bug reports. The QA agent does not fix bugs. Findings are reported, not patched.
- Future BL features not yet closed by engineering.
- Re-grading of the engineering scorecard.

## Expected Artifacts

- `runs/<qa-run-id>/engineer_stack_results.txt` — verbatim stdout from each engineer-stack command and its exit code.
- `runs/<qa-run-id>/gap_audit.md` — gaps identified in the engineer-authored verification.
- `runs/<qa-run-id>/journey_suite/` — runnable accumulated journey suite. Top-level `run.sh` (or `run.py`) executes the full suite.
- `runs/<qa-run-id>/journey_results.json` — JSON results per scenario from the latest run.
- `runs/<qa-run-id>/bug_report.md` — one entry per finding using the format in `docs/qa_evaluation_protocol.md`.
- `runs/<qa-run-id>/metadata.yaml` — run metadata per the schema below.
- `runs/<qa-run-id>/scorecard.md` — completed using `templates/scorecard_template.md` and the QA scoring axes in `docs/qa_evaluation_protocol.md`.

## Verification Commands

The QA cycle's verification step (run by the human scorer, not the QA agent) is:

```bash
# Engineer stack at target commit (must pass)
.venv/bin/python -m pytest -q
.venv/bin/python scripts/full_http_smoke.py --port <port>

# QA suite must be runnable end-to-end on a fresh clone
cd runs/<qa-run-id>/journey_suite && ./run.sh

# Re-run sample bug repro to confirm reproducibility
```

## Done Criteria

- All engineer-stack commands ran and their results are reported.
- All required journeys present in the suite for this BL and all inherited BLs.
- All cross-BL adversarial journeys applicable at this BL present.
- Journey suite runs end-to-end deterministically against a fresh clone.
- Bug report compiled with each finding reproducible.
- Scorecard completed with severity-classified findings, suite metrics, and decision.

## Metadata Schema

```yaml
run_id: "qa-<NNN>-<skill>-bl-<BBBB>"
date: "<YYYY-MM-DD>"
status: "executed"   # later set to "scored"

candidate:
  queue_id: "QA-<NNN>"
  role: "QA"
  source_repo: "<github-owner/repo>"
  source_url: "<https url>"
  source_commit: "<sha>"
  selected_skill_path: "<path inside source repo>"
  local_skill_snapshot: "skills/qa/<skill-id>/SKILLS.md"
  skill_sha256: "<sha256>"

target:
  repo_id: "project-tracker-v1-engineering-baseline"
  repo_url: "local:/Users/eugenegoldberg/dev/ai-projects/agentic-skills/target-repos/project-tracker-v1-engineering-baseline"
  baseline_commit: "<engineering BL closing commit>"
  local_path: "target-repos/project-tracker-v1-engineering-baseline"
  engineering_bl: "BL-<BBBB>"
  engineering_brief_path: "briefs/engineering-work-packets/bl-<BBBB>-*.md"
  engineering_run_id: "eng-<NNN>-<skill>-bl-<BBBB>"
  qa_brief_path: "briefs/qa-work-packets/qa-<NNN>-<skill>-bl-<BBBB>.md"
  qa_brief_sha256: "<sha256>"
  carry_forward_suite_from: "<prior qa-run-id or none>"

execution:
  model: ""
  tool_runtime: ""
  human_rescue_level: 0

artifacts:
  engineer_stack_results: "runs/<qa-run-id>/engineer_stack_results.txt"
  gap_audit_path: "runs/<qa-run-id>/gap_audit.md"
  journey_suite_path: "runs/<qa-run-id>/journey_suite/"
  journey_results_path: "runs/<qa-run-id>/journey_results.json"
  bug_report_path: "runs/<qa-run-id>/bug_report.md"
  raw_logs_path: "runs/<qa-run-id>/raw_logs/"
  scorecard_path: "runs/<qa-run-id>/scorecard.md"

verification:
  engineer_stack_result: ""   # pass | fail (any cmd non-zero)
  journey_suite_result: ""    # pass | fail
  total_scenarios: 0
  scenarios_passed: 0
  scenarios_failed: 0
  bug_count_by_severity:
    critical: 0
    high: 0
    medium: 0
    low: 0
    cosmetic: 0

outcome:
  decision: ""
  total_score:
  failure_mode_labels: []
  summary: ""
```
