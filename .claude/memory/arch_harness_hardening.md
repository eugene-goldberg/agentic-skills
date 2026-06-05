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

## Deferred (next session — see [[arch-active-branch]] + CONTINUATION_PROMPT)
- **#1 A39** `_extract_playwright_failures` + expand suite→node-ids (LOW, HIGH value).
- **#5 A49** playwright `--retries` in gate template (LOW).
- **#3** orchestrator `_engineer_flow` wedge-proof: always emit
  `bl.done(engineer_unmerged)` on exhaustion (HIGHER risk).

## Lesson
The crew's grounded worker-loop is solid (5/6 clean, engineers did real
contextual+graph retrieval per BL). The autonomous loop's fragility is in the
**harness control plane**: gate signal quality (A39), liveness heuristics that
misread rate-limit/long-tool as hung (A45), gate non-determinism (A49), and
no-clean-terminal on exhaustion (#3). These four, together, are the gap between
"BL fails, operator fixes it" and "8h wedge." Fix them before scaling sprint size.
