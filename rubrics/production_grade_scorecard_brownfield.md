# Production-Grade Skill Evaluation Rubric — Brownfield

Use this rubric for **every brownfield role skill evaluation**. Score each dimension from `0` to `5`. Replaces the greenfield rubric whenever the target repo is classified `brownfield` by `target_status()`.

The brownfield rubric ADDS five dimensions beyond the standard core (50 max) and role-specific (25 max) scoring; brownfield total is `core (50) + role (25) + brownfield (25) = 100 max`. A run that scores ≥80 with no individual dimension below 3 is "Pass"; a single dimension ≤2 on the brownfield axes flips the verdict to "Fail" regardless of total.

## Score Scale

| Score | Meaning |
|---:|---|
| 0 | Missing, unusable, or actively harmful — broke an invariant or contract |
| 1 | Very weak; pattern violations or regressions present |
| 2 | Partially useful but introduces material brownfield risk |
| 3 | Acceptable baseline; minor pattern drift or coverage gaps |
| 4 | Strong; matches existing conventions with only cosmetic deviation |
| 5 | Indistinguishable from existing high-quality code; regression-clean |

## Core Dimensions (50)

Same ten as the greenfield rubric — see `production_grade_scorecard.md`. Brief comprehension, Scope control, Correctness, Verification quality, Security and privacy, Data integrity, Maintainability, Integration quality, Production readiness, Autonomy.

## Role-Specific Dimensions (25)

Same five per role as the greenfield rubric.

## Brownfield Dimensions (25)

Score each from 0 to 5. **A single score of 2 or below on any brownfield axis forces a Fail verdict** regardless of how high the core/role scores are.

| Dimension | What To Check | Evidence Required |
|---|---|---|
| Pattern Fidelity | New code is stylistically and structurally indistinguishable from the closest existing high-quality implementation in the same codebase | Cite 2+ reference files/functions in the target repo whose patterns were matched (naming, layering, error handling, logging, DI, config conventions) |
| Regression Coverage | The repo's pre-existing test suite still passes; differential test run shows no previously-passing test now failing | Pre-merge and post-merge test result diff; explicit `regressions: 0` line in the QA report |
| Characterization Tests | When legacy behavior was touched, characterization tests were added that pin down current behavior before any modification | List of characterization tests added with file paths; explanation of what legacy behavior each pins |
| Invariant Preservation | Privacy (404 vs 403), tenant isolation, cascading deletes, assignee-clearing, and any other invariant explicitly listed in REQUIREMENTS.md is intact | Adversarial test cases that attempt to violate each invariant and confirm they fail (i.e. the invariant holds) |
| Blast Radius | Change is minimally invasive — additive where possible, feature-flagged where behavior changes, scoped to the smallest reasonable file/module set | File-count delta vs. lines-added/removed ratio; explicit feature flag identifier if any behavior changed |

## Decision Rules (Brownfield)

- **Fail** if:
  - Any brownfield dimension scores 0–2
  - Any pre-existing test that was passing now fails
  - Any invariant is provably violated by an adversarial test
  - The change exceeds 3x the smallest plausible diff for the BL's stated scope
- **Pass W/R** if:
  - All brownfield dimensions ≥ 3 but ≥2 dimensions are exactly 3
  - QA had to add ≥3 characterization tests retroactively (signal that engineer didn't write them up front)
- **Pass** if:
  - All brownfield dimensions ≥ 3 with majority ≥ 4
  - No regressions, all invariants intact, blast radius proportionate to BL scope

## Required Evidence Blocks

Every brownfield scorecard MUST include these sections; absence is itself a Fail signal:

```
## Pattern Fidelity Evidence
- Closest existing analog: <repo-relative path>:<line range>
- Conventions matched: <naming|layering|error_handling|logging|config|di>
- Deviations and justification: <if any>

## Regression Coverage Evidence
- Pre-merge suite: <N passing, M failing>
- Post-merge dry-run suite: <N passing, M failing>
- Regressions introduced: <list, or "none">

## Invariant Verification
- Privacy (404/403): <how verified>
- Tenant isolation: <how verified>
- Cascade behavior: <how verified, or "not touched">
- Other invariants from REQUIREMENTS.md: <list>

## Blast Radius
- Files modified: <N>
- Lines added/removed: <+X / -Y>
- Feature flag used: <name or "none — additive only">
```

## Notes for the Scorer

- The brownfield rubric assumes `target_status()` returned `kind="brownfield"`. If the scorer believes the target is actually greenfield-like for the slice in question (e.g. an entirely new module with no existing analog), it should still apply Pattern Fidelity against the *parent repo's* layering even if no direct analog exists in the touched files.
- Pre-existing failing tests are NOT regressions — only tests that flipped from passing → failing count. The harness provides the pre/post diff in the agent's done event under `regression_gate`.
- The scorer is read-only: do not modify production code, do not modify tests, do not re-run pytest. Trust the `regression_gate` data provided.
