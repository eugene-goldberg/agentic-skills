---
name: arch-acceptance-agent
description: ABL-0014 Acceptance Agent — OPERATIONAL since 2026-05-31; Items 1+2 (API-acceptance + UI-coverage check) landed 2026-06-01 across Batches A/B/C/D. UI journeys exercise what users can reach; api_journeys exercise every merged backend BL via authenticated portal client; sprint_complete carries coverage_subtype (full|partial) and ratio. Closes A46 (per-BL isolation gap; Client_Portal sprint proof point) and Item 1/2 (backend-without-UI assurance + operator visibility).
metadata:
  type: project
---

## Status

- **Batch A** (skill loader + validator + flow skeleton + tests): SHIPPED at `4a5c108`. 14 tests pass.
- **Batch B** (worktree + agent spawn + R10.1 retry + archive + closure_check ext + 2 new tests): SHIPPED at `f1bdb8b`. 31 acceptance-related tests pass; 56 backend total no regressions.
- **Batch C** (frontend + 7 docs + memory): SHIPPED at `c504e4f`.
- **Calibration smokes** (3/3 PASSED 2026-05-31): smoke-1 (5 gap fixes at `aa0e9ef`), smoke-2 (1 gap fix at `eb075ad`), smoke-3 (zero gaps, validator_ok=True attempt 1).
- **Default flipped to `run_acceptance=True`** at `8499dd3` — ABL-0014 OPERATIONAL (UI-only scope).
- **Production proof-of-class** at `run-20260531T134012Z-dd4864` (health-version, 2026-05-31): acceptance found 3 real `product_bug` findings per-BL QA had missed (missing VersionPill.tsx, missing click-copy, broken cross-actor e2e).
- **Item 1 Batch A** (validator contract for `api_journeys.yaml` + SKILLS.md "API Acceptance" section + 12 tests): SHIPPED at `2282c69`. Backward-compatible: `validate_acceptance(acc_dir)` unchanged when no `backend_bls` supplied.
- **Item 1 Batch B** (orchestrator computes backend_bls via `_compute_backend_bls`, threads through `_build_acceptance_task` + `validate_acceptance`, `RunAcceptanceRequest.backend_bls_override`, 9 new tests): SHIPPED at `3cc52ca`.
- **Item 2 Batch C** (UI-coverage check at sprint_complete; `_compute_ui_coverage`; `RunBriefRequest.min_ui_coverage_ratio: float = 0.0`; new `orchestrator.coverage_check` event + `coverage_subtype` on sprint_complete; 7 new tests): SHIPPED at `25a8d33`.
- **Item 2 Batch D** (frontend AppV2 coverage tile + min_ui_coverage_ratio input + backend_bls surfacing on acceptance tile + HARNESS.md §5.6.2 split into §5.6.2.1 API Acceptance + §5.6.2.2 UI-coverage + this memory): SHIPPED in current commit.
- **Test posture**: 94/94 backend pass after Batch D (was 64 pre-Item-1).

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
- **Calibration smokes for Item 1 (API-acceptance path)**: Batch B proof-point in flight against Client_Portal sprint. Two more clean runs required before Item 1 can be declared "operational" with same confidence as UI-only ABL-0014.
- **ABL-0015 (still deferred)**: auto-dispatch follow-up engineer on `product_bug` findings — closes the find→fix loop.
- **A48 pre-flight disk-free check** — filed but not yet implemented; acceptance runs are heavy on docker volume churn.
- **Acceptance trace observability gaps** (filed informally): no `retrieval.jsonl`, no `phase_events.jsonl`, tool invocations don't show in `stream.jsonl`. Currently a black box for diagnostics.
- **Findings feedback ledger**: no mechanism today to bound the agent's false-positive rate over multi-sprint windows.
- Retrieval MCP wiring (currently `allowed_tools="Bash,Read,Write,Edit"`; agent uses pre-existing test helpers via Read).

## Item 1+2 design rationale (Batch D consolidated)

- **Why Item 1 (API-acceptance) is mandatory not optional**: A46 was framed as "per-BL QA misses cross-component bugs." Hidden assumption was bugs manifest in UI. Client_Portal sprint exposed the gap: 4 of 10 BLs shipped backend with no UI — acceptance honestly flagged `capability_gaps` but couldn't *exercise* those backends, leaving their assurance to per-BL QA, which is exactly what ABL-0014 was created to backstop. Item 1 closes that.
- **Why coverage assertion is on the validator, not the prompt**: prompts are advisory; validators are enforced. A coverage gap triggers R10.1 retry with the missing BLs named, mirroring `doctrine_validator.build_fix_prompt`.
- **Why Item 2 doesn't flip terminal_status**: `sprint_complete` has a strong downstream contract (UI tile renderers, doctrine-meta-agent inputs, closure_check trigger). Adding a new value would force every consumer to handle it. Subtype on the same event is cheaper, simpler, and equally operator-visible. A future tighter mode is reachable via a `hard_gate_on_partial` flag.
- **Why default `min_ui_coverage_ratio=0.0`**: same opt-in discipline as ABL-0014's original 3-smoke calibration. Operator can dial up after watching a few sprints' actual ratios.
- **Repo-configurable globs**: `RepoConfig.api_route_globs` and `ui_globs` default to FastAPI/React shapes; targets with Django/Rails/Next.js can override in `.agentic-skills.json` without code change.
