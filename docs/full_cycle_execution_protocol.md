# Full Cycle Execution Protocol

Use this protocol for every candidate evaluation. Do not begin a second candidate until the current cycle is closed.

## Cycle Definition

Each cycle evaluates:

```text
candidate source + role + selected skill file + target repo + normalized brief
```

The cycle ends only when these artifacts exist:

- Skill snapshot and hash.
- Brief snapshot and hash.
- Run metadata record.
- Raw model/tool logs.
- Generated output artifacts.
- Verification output.
- Completed scorecard.
- Progress tracker update.

## Step 1: Select Candidate

Take the next `Queued` item from `docs/progress_tracker.md`.

Record:

- Queue ID.
- Role.
- Candidate source repository.
- Priority.
- Status changed to `Selecting Skill`.

## Step 2: Inspect Candidate Source

Clone or inspect the candidate repository.

Find all plausible `SKILLS.md` files for the selected role. Choose exactly one skill file for the cycle.

Selection criteria:

- Direct role match.
- Clear operational instructions.
- Low ambiguity.
- Production-oriented behavior.
- Fits the intended evaluation brief.

If no suitable skill exists, mark the queue item `Blocked` or `Skipped` and explain why.

## Step 3: Snapshot Skill

Copy the selected skill into the project under:

```text
skills/<role>/<skill_id>/SKILLS.md
```

Record:

- Original source repo.
- Original path.
- Commit SHA or release tag.
- SHA-256 hash of the copied skill file.
- Any local normalization performed.

Do not edit the skill after hashing unless creating a new skill variant ID.

## Step 4: Select Brief and Target Repo

Choose one normalized brief and one target repo.

Record:

- Target repo URL.
- Baseline commit.
- Brief path.
- Brief hash.
- Verification command.
- Expected artifact shape.

## Step 5: Run Evaluation

Submit the brief using only the selected skill as the tested role variable.

Capture:

- Prompt or invocation.
- Model and model settings.
- Tool/runtime environment.
- Raw transcript or logs.
- Generated files.
- Any human intervention.

## Step 6: Verify Output

Run objective verification commands.

Examples:

- `pytest`
- `npm test`
- `ruff`
- `mypy`
- API smoke tests
- Build commands
- Canonical hidden or semi-hidden tests, when available

Record exact commands and outputs.

## Step 7: Score

Complete `templates/scorecard_template.md` using `rubrics/production_grade_scorecard.md`.

Include:

- Dimension scores.
- Critical defects.
- Failure mode labels.
- Overall decision.
- Human rescue level.

## Step 8: Close Cycle

Update:

- `docs/progress_tracker.md`
- Run log entry.
- Candidate queue status.
- Skill inventory.
- Reports, if this cycle completes a comparison batch.

Allowed terminal statuses:

- `Scored`
- `Blocked`
- `Skipped`
- `Needs Rerun`

Do not start the next candidate until the current status is terminal.

