---
name: arch-harness-hardening
description: "2026-06-04/05 — a live search sprint (search_and_discovery_2) reproduced the A39+A45+A49 compound wedge on BL-0006; shipped A45/A51/A50/End-Sprint/AppV2-review-merge; deferred A39/A49/orchestrator-wedge(#3). The canonical evidence for why these harness gaps block the autonomous loop."
metadata: 
  node_type: memory
  type: project
  originSessionId: 7979a248-b0b3-495b-9685-dc8fd4f1d643
---

First time the autonomous loop wedged on a real run — and it was the **harness**,
not the crew. Search feature on full-stack-fastapi-template (clean fork off
master). 5/6 BLs merged_full; **BL-0006 (frontend) wedged 8h** then never
terminated cleanly.

## The compound failure (all reproduced with evidence)
- **A39** — gate reported `regressions: ['tests/playwright::e2e_suite']` ("1
  regression") while 5 distinct playwright tests failed. Engineer retry got no
  test names → ran the gate itself to diagnose.
- **A45** — that retry logged **28 rate_limit_events + 600s silence → false
  idle-kill** (rate-limited, not hung).
- **A49** — 1 of the 5 was the recurring **flaky reset-password** E2E.
- The 5 BL-0006 failures: 2 **test-locator bugs** (non-strict `getByRole`/
  `getByText` → strict-mode violations; UI renders fine), 2 **real "search-
  results don't render"** (`getByTestId('search-results')` not found — likely
  **unseeded search data** in the gate DB), 1 flaky.
- Chain: A39 (no actionable names) → self-run-gate → A45 (idle-kill) → wedge.

## Shipped
- **A45 (in-flight half)** `8005dda`: `claude_agent._inflight_readline_timeout()`
  — wall timeout while a tool_use is in flight; tool ids tracked tool_use→result.
- **A51** `8005dda`: `--strict-mcp-config` — agents no longer inherit the
  operator's global MCP fleet (Gmail/Drive/MS365/azure-devops/ghost-Postgres);
  surfaced when the scorer probed azure-devops mid-run.
- **A50** `c06615e`: `merge-branch` syncs the follow-up finding → `merged`.
- **End current Sprint** `b6ea3e9`: `/end-sprint` kill+cleanup (worktrees, docker
  stacks/volumes, run-scoped images, run-state, lock) + AppV2 ⛔ button. The tool
  that cleared this wedged run.
- **AppV2 Review&merge** `b4a1b46`: in-UI anomaly resolution (BranchesPanel,
  unmerged tile, inline merge on not_merged) + run-brief flag toggles.
- Docs `CONTROL_FLOW.md` (gate/check flowchart) + `DOCTRINE.md`.

## ALL THREE SHIPPED + VALIDATED LIVE (2026-06-05 evening, commit `4773e67`)
- **#1 A39** `regression_gate._extract_playwright_failures` — expands the opaque
  `tests/playwright::e2e_suite` into real per-test node-ids + names them in
  `reason`. **Validated live** in the Horizon BL-0001 gate (named
  admin/search/user-settings → auth.setup.ts each retry). 7 tests.
- **#5 A49** `detect_transient_markers` (annotate-only) + explicit `--retries=2`
  in both gate templates. Verdict-flip reclassification deferred (operator
  sign-off). 6 tests.
- **#3 wedge-proof** — root cause was structural: `run_brief`'s outer `try` had
  only a `finally` (can't yield during aclose, PEP 525). Added engineer-flow
  wrap → `engineer_unmerged` + an outer `except` backstop → terminal `aborted`.
  **Validated live**: Horizon BL-0001 exhausted retries → clean `aborted`, NOT a
  wedge. 3 tests.

## A52 — false no_op after a pre-grounding kill (FOUND + FIXED, `ebcf4eb`)
Discovered on the Horizon run ([[arch-horizon-run]]): a pre_grounding-killed
engineer that wrote eng_patterns.md but committed no code was falsely marked
`no_op` (working-tree `.exists()` check), silently skipping a foundation BL.
Fix: R11 no_op now requires the artifact **committed at HEAD**
(`_is_committed_at_head`). UNPUSHED at handoff.

## Lesson (updated)
The crew's grounded worker-loop is solid; the autonomous loop's fragility was
the **harness control plane** — gate signal quality (A39), liveness heuristics
(A45), gate non-determinism (A49), no-clean-terminal (#3 wedge-proof), and
false-no_op skip (A52). As of this session **all are fixed and proven under a
real failure**: the same harness that produced an 8h silent wedge now produces
a clean, named, ~1.5h halt with broken work quarantined. The frontier has moved
DOWNSTREAM — from "the harness wedges" to "the **crew** can't self-repair a hard
regression in budget" (Horizon BL-0001 broke login; engineer chased symptoms).
That is a capability problem (engineer root-cause depth), not a control-plane
one — see [[arch-horizon-run]] + [[arch-acceptance-v02]].
