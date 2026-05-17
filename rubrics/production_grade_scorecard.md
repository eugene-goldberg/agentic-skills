# Production-Grade Skill Evaluation Rubric

Use this rubric for every role skill evaluation. Score each dimension from `0` to `5`.

## Score Scale

| Score | Meaning |
|---:|---|
| 0 | Missing, unusable, or actively harmful |
| 1 | Very weak; major requirements missed |
| 2 | Partially useful but unreliable |
| 3 | Acceptable baseline; meaningful gaps remain |
| 4 | Strong; minor issues only |
| 5 | Excellent; production-grade for the tested scope |

## Core Dimensions

| Dimension | What To Check |
|---|---|
| Brief comprehension | Preserves explicit requirements, hidden constraints, acceptance criteria, and domain intent |
| Scope control | Does not overbuild, underbuild, drift, or invent conflicting requirements |
| Correctness | Output satisfies the functional behavior requested by the brief |
| Verification quality | Tests or checks are meaningful, executable, and aligned with the risk profile |
| Security and privacy | Handles auth, authorization, validation, secrets, and data exposure correctly |
| Data integrity | Handles cascades, transactions, persistence, and cross-actor isolation correctly |
| Maintainability | Code or docs are clear, idiomatic, cohesive, and easy to modify |
| Integration quality | Fits the target repo structure, conventions, dependencies, and runtime |
| Production readiness | Buildable, runnable, documented enough, operationally sane |
| Autonomy | Handles ordinary obstacles without excessive human rescue |

## Role-Specific Dimensions

### Product Owner

| Dimension | What To Check |
|---|---|
| Requirement decomposition | Converts brief into coherent epics, stories, milestones, or tasks |
| Acceptance criteria | Produces testable, unambiguous completion criteria |
| Ambiguity handling | Identifies unclear points and recommends safe decisions |
| Risk discovery | Surfaces edge cases, privacy rules, security concerns, and dependency risks |
| Developer usefulness | Produces artifacts an engineer can implement without reinterpreting the brief |

### Engineer

| Dimension | What To Check |
|---|---|
| Implementation completeness | Produces the requested runnable artifacts |
| Architectural fit | Uses simple, suitable structure for the target repo and task |
| Test compatibility | Passes canonical tests or provides high-quality tests that would catch real defects |
| Debugging behavior | Iterates effectively when failures occur |
| Dependency discipline | Chooses stable, compatible dependencies and records them correctly |

### QA

| Dimension | What To Check |
|---|---|
| Test strategy | Defines high-signal coverage across happy paths, negative paths, and edge cases |
| Bug discovery | Finds severe defects rather than only superficial issues |
| Reproducibility | Provides exact steps, inputs, expected results, and observed results |
| Regression value | Produces tests that remain useful after the immediate run |
| Noise control | Avoids low-value findings and distinguishes product, test, and environment failures |

## Gate Conditions

A run cannot be considered production-grade if any of these are true:

- Required artifact is missing.
- Main artifact does not parse or compile.
- App or package cannot start because of generated code defects.
- Canonical tests fail due to product behavior.
- Security or privacy requirement is violated.
- Non-member or cross-tenant data exposure occurs.
- Output requires large human rewrite to become runnable.

## Human Rescue Level

Record the highest level of human rescue required:

| Level | Meaning |
|---:|---|
| 0 | None |
| 1 | Environment-only help, no artifact changes |
| 2 | Minor dependency or command correction |
| 3 | Small code/test patch |
| 4 | Major code/test repair |
| 5 | Human effectively completed the task |

## Overall Decision

Choose one:

- `Pass`: production-grade for the tested scope.
- `Pass With Reservations`: useful but has important caveats.
- `Needs Rerun`: evaluation was inconclusive due to tool or environment problems.
- `Fail`: output did not meet minimum quality bar.
- `Blocked`: candidate could not be evaluated.

