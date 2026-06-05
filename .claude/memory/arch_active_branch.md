---
name: arch-active-branch
description: "followup-dispatch-ui @ 8005dda (2026-06-05 handoff). Live search_and_discovery sprint exposed A39+A45+A49 compound wedge; A45/A51/A50/End-Sprint/AppV2-review-merge shipped; A39/A49/orchestrator-wedge(#3) deferred. NEXT: finish the 3 deferred harness fixes, then re-run."
metadata: 
  node_type: memory
  type: project
  originSessionId: 7979a248-b0b3-495b-9685-dc8fd4f1d643
---

## State at 2026-06-05

- **agentic-skills branch:** `followup-dispatch-ui` @ `8005dda`, pushed. Stacked
  on architect-prereqs → cumulative_learning → followup-dispatch-ui (branch
  consolidation to trunk still deferred).
- **Target:** `full-stack-fastapi-template` on **`agentic-skills-work-search_and_discovery`**
  @ `46d5bce` — clean fork off master (no billing), **5/6 search BLs merged**;
  BL-0006 (frontend) NOT merged. `.agentic-skills.json` points here.
- **Tests:** 272 passed (`cd webapp/backend && .venv/bin/python -m pytest tests/`).
- **Live stack:** uvicorn PID 15816 (has A50, NOT A45/A51 — restart to load
  8005dda); vite frontend; Docker = milvus only.

## What this session did (see [[arch-harness-hardening]])
Ran a live `search_and_discovery_2` sprint → 5/6 merged, **BL-0006 wedged** by a
3-defect compound (**A39** gate signal collapse + **A45** idle-kill of a
rate-limited agent + **A49** flaky reset-password). Killed + cleaned via the new
End-Sprint flow. Then hardened the harness.

**Shipped:** AppV2 in-UI Review&merge + toggles (`b4a1b46`); A50 merge-branch
ledger sync (`c06615e`); ⛔ End current Sprint button + `/end-sprint`
(`b6ea3e9`); **A45 in-flight idle fix + A51 `--strict-mcp-config`** (`8005dda`).
Docs: `CONTROL_FLOW.md`, `DOCTRINE.md`.

## ⭐ NEXT SESSION GOAL — finish 3 deferred harness fixes, then re-run
1. **#1 A39** (regression_gate.py): `_extract_playwright_failures` + expand
   `tests/playwright::e2e_suite` into real node-ids. LOW risk. HIGH value.
2. **#5 A49** (gate template): playwright `--retries=2`. LOW risk.
3. **#3 wedge-proof** (orchestrator `_engineer_flow`): always emit
   `bl.done(engineer_unmerged)` on exhaustion — no 0-procs wedge. HIGHER risk.
Then restart uvicorn, decide BL-0006 (re-run vs hand-fix 2 locator bugs + the
search-results/seed-data gap), re-run the sprint clean.

Full handoff in `CONTINUATION_PROMPT.md`. Other deferred: ABL-0017 Stage 2,
branch consolidation, flag-flip calibration smokes.
