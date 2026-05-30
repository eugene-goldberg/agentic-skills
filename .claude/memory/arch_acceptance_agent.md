---
name: arch-acceptance-agent
description: Proposed ABL-0010 role drafted in skills/brownfield/brownfield-acceptance-agent/SKILLS.md. Runs once at sprint_complete; reads brief as a whole; infers end-to-end user journeys; seeds realistic state; exercises each journey via playwright with screenshots. Closes the per-BL-isolation gap (BL-0007 REQ-0502 worked example). NOT YET wired into orchestrator.
metadata:
  type: project
---

## Why the role exists
Operator critique 2026-05-30: regression-clean gates ≠ functionality tested end-to-end as a real user would. Per-BL QA is structurally limited because it tests one BL in isolation and cannot exercise cross-BL user journeys. Real teams hand off to a UAT pass after dev-done; the framework needs an analog.

## Design (drafted SKILLS.md)
- Runs after `sprint_complete`, before `closure_check`/`doctrine_meta`
- Frame: the original brief as a whole (NOT per-BL contexts — that's the framing bias)
- Output: `_brownfield/features/<slug>/acceptance/` with journeys.yaml + report.md + tests/_acceptance/*.spec.ts + screenshots/ + fixtures/seed.py
- Read-only on code: no merges, no commits to agent_branch
- Sandbox tests in separate dir so they cannot pollute the regression gate
- Realistic seeding: ≥3 users, ≥1 month activity, varied roles, realistic skew
- No retries — one honest pass with classified failures (product_bug / test_bug / data_bug / infra_bug / uncertain)

## Pending operator decisions
1. Wire into orchestrator behind `run_acceptance: bool=True` flag?
2. Build prompt builder + validator + tests next?
3. Smoke-run against time-tracking sprint as first real test?

## Worked example that motivates the role
BL-0007 REQ-0502: superuser self-approval test exposed a real cross-component bug (ReviewTimesheet keeps dialog open on error → Radix Dialog sets aria-hidden on sibling content → queue rows vanish from a11y tree). QA's 3 R10 retries couldn't fix it because QA cannot request an engineer-side UX change. Test is now `.skip`'d. Acceptance Agent would have classified this as `product_bug` with operator visibility at sprint close instead of silent skip.
