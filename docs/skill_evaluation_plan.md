# Agentic Skills Evaluation Plan

## Project Goal

Evaluate agentic role skills, written in `SKILLS.md` format, across a small set of distinct repositories to determine which Product Owner, Engineer, and QA skill variants produce the most reliable production-grade output.

The project is designed as a controlled comparison. For each experiment, we change one skill variable at a time while holding the repo, brief, model, and evaluation rubric constant.

## Candidate Evaluation Strategy

Use the candidate list in `docs/agentic-skills-repos.md` as the source queue, but evaluate only one candidate source at a time.

A candidate source is one repository or collection that may contain one or more role-relevant `SKILLS.md` files. Examples include `Agile-V/agile_v_skills` for Product Owner skills or `addyosmani/agent-skills` for Engineer/QA skills.

For each candidate source:

1. Select one role from that source: `PO`, `Engineer`, or `QA`.
2. Identify the single best-matching `SKILLS.md` file for that role.
3. Snapshot and hash that skill file.
4. Run the full evaluation cycle for that one skill.
5. Score and document the result before moving to the next candidate.

Do not evaluate multiple candidate sources in the same run. Do not mix role skills from multiple repositories in the same run. A full cycle must finish with artifacts, verification results, scorecard, and progress-tracker entry before the next candidate starts.

This keeps the comparison legible:

```text
one candidate source -> one role -> one skill file -> one brief -> one complete scorecard
```

## Core Experiment Shape

Each evaluation run should follow this unit:

```text
(repo, role, skill_variant, brief) -> output_artifacts + objective_scorecard
```

Only one role skill is tested at a time:

- `PO`: requirement interpretation, decomposition, acceptance criteria, risk discovery.
- `Engineer`: implementation quality, code correctness, maintainability, integration discipline.
- `QA`: test design, regression discovery, edge-case coverage, verification quality.

## Controlled Variables

For a valid comparison, the following must remain fixed across runs in the same batch:

- Same target repository and baseline commit.
- Same normalized brief.
- Same model and model settings.
- Same runtime environment.
- Same evaluation rubric.
- Same time/token budget where possible.
- Same artifact expectations.

The only intended variable in a comparison run is the `SKILLS.md` content for the selected role.

## Required Run Metadata

Each run must record:

- `run_id`
- `date`
- `repo_id`
- `repo_url`
- `repo_baseline_commit`
- `role`
- `skill_source_repo`
- `skill_file_path`
- `skill_hash`
- `brief_id`
- `brief_hash`
- `model`
- `tooling/runtime`
- `time_budget`
- `token_budget`, if available
- `output_artifacts_path`
- `test_command`
- `test_result`
- `scorecard_path`
- `failure_mode_labels`
- `human_reviewer`
- `review_notes`

## Suggested Directory Layout

```text
agentic-skills/
  docs/
    skill_evaluation_plan.md
    progress_tracker.md
  skills/
    po/
    engineer/
    qa/
  briefs/
  target-repos/
  runs/
  rubrics/
  reports/
```

## Standard Workflow

1. Select the next candidate source from the candidate queue.
2. Select exactly one role to evaluate for that candidate: `PO`, `Engineer`, or `QA`.
3. Select exactly one `SKILLS.md` file for that role.
4. Select a target repo and record its baseline commit.
5. Select one normalized brief and hash it.
6. Hash and snapshot the skill file.
7. Submit the brief using only that role skill as the tested variable.
8. Capture all generated artifacts and logs.
9. Run the prescribed verification commands.
10. Score the output with the standard rubric.
11. Label failure modes.
12. Record results in the progress tracker.
13. Mark the candidate-cycle status as complete, blocked, or needs rerun.
14. Move to the next candidate only after this cycle is closed.

## Objective Evaluation Dimensions

Score each run on a consistent 0-5 scale unless a rubric says otherwise.

- Brief comprehension: preserves explicit and implicit requirements.
- Scope control: avoids overbuilding, underbuilding, or changing the assignment.
- Correctness: implementation or role output satisfies functional requirements.
- Test quality: tests cover success paths, failure paths, edge cases, and regressions.
- Security and privacy: handles auth, authorization, data exposure, secrets, and validation correctly.
- Maintainability: code or documents are clear, idiomatic, and easy to extend.
- Integration quality: fits the repo structure, conventions, dependencies, and existing contracts.
- Production readiness: runnable, observable, documented enough, and free of obvious operational hazards.
- Autonomy: resolves ordinary obstacles without unnecessary human rescue.
- Reliability: produces consistent quality across repeated runs.

## Failure Mode Labels

Use one or more labels when a run fails or partially succeeds:

- `requirements_missed`
- `scope_drift`
- `incomplete_artifact`
- `syntax_error`
- `dependency_error`
- `test_failure`
- `weak_tests`
- `privacy_or_auth_bug`
- `cascade_or_data_integrity_bug`
- `tooling_failure`
- `environment_failure`
- `excessive_human_rescue`
- `non_reproducible`

## Role-Specific Signals

### Product Owner

Evaluate whether the skill produces:

- Accurate restatement of goals.
- Clear acceptance criteria.
- Ambiguity discovery with recommended decisions.
- Edge-case identification.
- Useful prioritization.
- Testable user stories or scenarios.

### Engineer

Evaluate whether the skill produces:

- Runnable implementation.
- Minimal but complete architecture.
- Correct data modeling.
- Correct error semantics.
- Good dependency choices.
- Focused tests or support for canonical tests.
- Clean integration with the target repo.

### QA

Evaluate whether the skill produces:

- High-signal test plan.
- Meaningful automated tests.
- Negative and cross-user/access-control cases.
- Regression probes.
- Clear bug reports.
- Reproduction steps.
- Distinction between product bugs, test bugs, and environment issues.

## Comparison Method

Within a batch, rank skills by:

1. Passing objective verification.
2. Total rubric score.
3. Severity-weighted defect count.
4. Amount of human rescue required.
5. Consistency across repeated runs.

A skill that produces slightly less ambitious but consistently correct output should usually outrank a skill that produces impressive but brittle output.

## Initial Research Questions

- Which PO skills best preserve complex constraints without bloating the implementation plan?
- Which Engineer skills most reliably produce runnable code under the same brief?
- Which QA skills catch the highest-severity defects with the least noise?
- Which skills fail because of reasoning versus tooling versus environment assumptions?
- Do skills that perform well on greenfield tasks also perform well on brownfield tasks?
