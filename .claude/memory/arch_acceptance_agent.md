---
name: arch-acceptance-agent
description: ABL-0014 Acceptance Agent — OPERATIONAL (2026-05-31). Runs after sprint_complete; reads brief as whole; infers end-to-end user journeys; seeds realistic state; exercises each via playwright with screenshots. Batches A+B+C + 2 calibration commits shipped. Default `run_acceptance=True` flipped after 3 clean smokes against time-tracking (smoke-1 surfaced 5 validator gaps, smoke-2 1 gap, smoke-3 zero gaps + validator_ok=True on attempt 1). Closes A45 (per-BL-isolation gap; BL-0007 REQ-0502 worked example).
metadata:
  type: project
---

## Status

- **Batch A** (skill loader + validator + flow skeleton + tests): SHIPPED at `4a5c108`. 14 tests pass.
- **Batch B** (worktree + agent spawn + R10.1 retry + archive + closure_check ext + 2 new tests): SHIPPED at `f1bdb8b`. 31 acceptance-related tests pass; 56 backend total no regressions.
- **Batch C** (frontend + 7 docs + memory): SHIPPED at `c504e4f`.
- **Calibration smokes** (3/3 PASSED 2026-05-31): smoke-1 (5 gap fixes at `aa0e9ef`), smoke-2 (1 gap fix at `eb075ad`), smoke-3 (zero gaps, validator_ok=True attempt 1).
- **Default flipped to `run_acceptance=True`** (this commit) — ABL-0014 OPERATIONAL.

## Why the role exists
Operator critique 2026-05-30: regression-clean gates ≠ functionality tested end-to-end as a real user would. Per-BL QA is structurally limited because it tests one BL in isolation and cannot exercise cross-BL user journeys. Real teams hand off to a UAT pass after dev-done; the framework needs an analog.

## Design (implemented)
- Runs after `sprint_complete`, before `closure_check`/`doctrine_meta`
- Advisory only (§E.1 Q3): exceptions become `acceptance.error`; sprint never aborts on acceptance failure
- Frame: the original brief as a whole (NOT per-BL contexts — that's the framing bias)
- Output: `_brownfield/features/<slug>/acceptance/` with `journeys.yaml + report.md + report.json + tests/_acceptance/*.spec.ts + screenshots/ + fixtures/seed_log.txt`
- Read-only on code: no merges, no commits to `agent_branch`; runs in detached worktree off `agent_branch` (§E.1 Q1)
- Sandbox tests in separate dir so they cannot pollute the regression gate
- Realistic seeding: ≥3 users, ≥1 month activity, varied roles, realistic skew
- One honest pass per journey (no in-agent retry) — failures classified as `product_bug / test_bug / data_bug / infra_bug / uncertain`
- R10.1 retry budget (max 2) applies to validator-incomplete on the *artifact contract*, not on journey failures
- Cost cap: ≤8 journeys × ≤15 steps (§E.1 Q4); two-layer enforcement (SKILLS.md + `acceptance_validator.py`)
- Timeout: 3600s default, configurable per-call (§E.1 Q2)
- Default: `run_acceptance=False` for first 3 sprints (§E.1 Q6) — flip after calibration confirms low FP rate
- COMPOSE_PROJECT_NAME=`acceptance-<run_id>` so `closure_check` enumerates leaks (§E.1 Q7+Q9)

## Operator-locked answers to §E.1 Q1-Q7 (2026-05-30)
1. Detached worktree off `agent_branch` (matches I-1/I-3)
2. Timeout 3600s default, configurable
3. Advisory failure semantics, never blocking
4. Cost cap 8×15, two-layer enforced
5. Report-only v1; auto-dispatch deferred to ABL-0015
6. `run_acceptance=False` default for first 3 sprints, then flip
7. Defensive `docker ps` pre-flight on `gate-<run_id>`; skip with `gate_stack_still_up`

## Code locations
- SKILLS.md: `skills/brownfield/brownfield-acceptance-agent/SKILLS.md`
- Skill registration: `webapp/backend/app/services/prompts_brownfield.py` (`SKILL_PATHS["acceptance"]`)
- Validator: `webapp/backend/app/services/acceptance_validator.py`
- Flow: `webapp/backend/app/services/orchestrator.py::_acceptance_flow`
- Pre-flight: `_gate_stack_present` (same file)
- Closure scans: `closure_check.scan_orphan_acceptance_containers` + `scan_stale_acceptance_worktrees`
- Plumbing: `RunBriefRequest.run_acceptance` in `app/routers/projects.py`
- Plan: `ABL-0014_ACCEPTANCE_AGENT_IMPLEMENTATION.md` (root of repo)
- Tests: `tests/test_acceptance_validator.py`, `test_acceptance_flow.py`, `test_run_brief_acceptance_wiring.py`, `test_closure_check_acceptance_stack.py`

## Worked example that motivates the role
BL-0007 REQ-0502: superuser self-approval test exposed a real cross-component bug (ReviewTimesheet keeps dialog open on error → Radix Dialog sets aria-hidden on sibling content → queue rows vanish from a11y tree). QA's 3 R10 retries couldn't fix it because QA cannot request an engineer-side UX change. Test is now `.skip`'d. Acceptance Agent would have classified this as `product_bug` with operator visibility at sprint close instead of silent skip.

## Open follow-ups
- 3 calibration smoke sprints with `run_acceptance=True` before flipping the default
- ABL-0015 (deferred): auto-dispatch follow-up engineer on `product_bug` findings
- Retrieval MCP wiring (currently `allowed_tools="Bash,Read,Write,Edit"`; agent uses pre-existing test helpers via Read)
