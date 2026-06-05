# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-06-05.

---PROMPT START---

You are picking up the agentic-skills project. **You are the architect.** Read
`CLAUDE.md` first (esp. "Operating principle: quality over speed" — Rules 1–6,
the **95% verified/tested floor**, Rule 3 narrative momentum). Only
agentic-skills is committed/pushed; brownfield targets and their `_brownfield/`
are never committed here.

## ⭐ THIS SESSION'S GOAL — finish the harness hardening, then re-run the sprint

Last session ran a **live brownfield sprint** (`search_and_discovery_2`,
"Advanced Search & Knowledge Discovery", on `full-stack-fastapi-template`) and
it exposed three harness defects that compounded into a wedged run. We fixed two
live and **deferred three** to this session. Do those, then re-run the sprint
clean.

### What happened last run (the evidence)
- **5/6 BLs `merged_full`** on the clean branch; **BL-0006 (frontend) wedged.**
- Root cause was a **3-defect compound**, all now reproduced with evidence:
  - **A39** — the gate reported `regressions: ['tests/playwright::e2e_suite']`
    ("1 regression") while there were **5 distinct playwright failures**. The
    engineer retry got no actionable test names → ran the gate itself → spiral.
  - **A45** — the retry then hit **28 rate_limit events + a 600s silence →
    false idle-timeout kill** (it was rate-limited/working, not hung).
  - **A49** — one of the 5 failures was the unrelated **flaky reset-password**
    E2E (recurring; also seen in the invoice run).
  - The 5 BL-0006 failures were: 2 **test-locator bugs** (engineer's own
    `search.spec.ts` non-strict `getByRole`/`getByText` → strict-mode
    violations; UI actually renders), 2 **real "search-results don't render"**
    (`getByTestId('search-results')` not found — likely **unseeded search data**
    in the gate DB), 1 **flaky** (reset-password).

### Already shipped last session (on `followup-dispatch-ui`)
- `b4a1b46` AppV2 in-UI **Review & merge** (BranchesPanel + unmerged tile +
  inline on `not_merged` findings) + run-brief toggles (run_acceptance_followup,
  inject_lessons).
- `c06615e` **A50** — `merge-branch` syncs the follow-up finding to `merged`.
- `b6ea3e9` **⛔ End current Sprint** button + `POST /end-sprint` (reaps
  worktrees, docker stacks/volumes, run-scoped images, run-state, lock).
- `8005dda` **A45 + A51** agent guards: `_inflight_readline_timeout()` (don't
  idle-kill while a tool is in flight / rate-limited) + **`--strict-mcp-config`**
  (agents no longer inherit the operator's global MCP fleet — Gmail/Drive/MS365/
  azure-devops/ghost-Postgres). Suite **272 passed**.
- Docs: `CONTROL_FLOW.md` (Mermaid + ASCII control-flow), `DOCTRINE.md`.

### ⭐ DO THIS SESSION — the 3 deferred harness fixes (precise specs)
1. **#1 A39 (regression_gate.py, LOW risk, do first):** add
   `_extract_playwright_failures(raw_tail)` —
   regex `\[chromium\]\s*›\s*(tests/\S+:\d+:\d+)\s*›\s*(.+?)\s*(?:─|$)`. In
   `run_gate`, when `tests/playwright::e2e_suite` is in `regressions`, **expand
   it to the real node-ids** into `regressions` (+ a `failing_tests` field), and
   name a few in `reason`. Unit-test the extractor on a sample tail. *This is the
   fix that gives the engineer something to fix.*
2. **#5 A49 (gate template, LOW risk):** add `--retries=2` to the playwright
   invocation in `webapp/backend/app/templates/regression_gate.sh` AND the
   active branch's `scripts/regression_gate.sh`, so flaky-final-pass = PASS
   (kills the reset-password false regression). Optional `_TRANSIENT_RE`
   annotation in `regression_gate.py`. Test: template contains `--retries`.
3. **#3 wedge-proof (orchestrator.py `_engineer_flow`, HIGHER risk — own care):**
   on retry-exhaustion/idle, **always emit `bl.done(engineer_unmerged)`** and
   continue/abort deterministically — never leave 0-procs-no-terminal (a wedged
   run that only the End-Sprint button can clear). Read the retry loop carefully
   first; don't break the R10/R10.1/R10.2 paths.

Also: **file A51 in the ledger** (implemented but not yet filed) and bump
A39/A45/A49 with this run's evidence (A45 partial fix is already noted).

### Then: re-run + BL-0006 decision
- Restart uvicorn to load `8005dda` (live PID 15816 predates A45/A51).
- BL-0006 (frontend search UI) is **not merged**. Decide: with A39+A49+seed-data
  fixed, re-run just BL-0006 (skip_po resume) OR hand-fix the 2 locator bugs +
  the search-results/seed gap, then merge. The 5 merged BLs (search foundation +
  registry, API, filtering, ranking, saved searches) are safe on
  `agentic-skills-work-search_and_discovery`.
- Consider whether the gate needs **seeded search data** for search/list
  features (the `search-results` E2E can't pass against an empty DB).

## State at hand-off
- **agentic-skills branch:** `followup-dispatch-ui` @ `8005dda` (pushed). Several
  branches stacked (architect-prereqs→cumulative_learning→followup-dispatch-ui);
  branch consolidation to a trunk is still deferred.
- **Target:** `full-stack-fastapi-template` on **`agentic-skills-work-search_and_discovery`** @ `46d5bce` — clean fork off master (no billing), 5/6 search BLs merged. `.agentic-skills.json` agent_branch points here.
- **Test posture:** `cd webapp/backend && .venv/bin/python -m pytest tests/` → **272 passed**.
- **Live stack:** uvicorn PID 15816 (has A50, NOT A45/A51 — restart to load `8005dda`); vite frontend; Docker = milvus only; worktrees/run-images cleaned.

## UI now (AppV2 — operator can run everything from the UI)
submit → stream (rich event log: click any line → full event JSON; tool calls/
text/results shown) → acceptance → triage (confirm/refute/defer) → 🛠 Dispatch
fix (R15) → ⚠ Unmerged-branches tile + Review & merge → ⛔ End current Sprint.

## Reading order
1. `CLAUDE.md` (architect role + operating principle)
2. This ⭐ section + `CONTROL_FLOW.md` (how the gates/checks work) + `DOCTRINE.md`
3. `DESIGN_SHORTCOMINGS.md` A39 / A45 / A49 / A50 / A51
4. `PREFLIGHT.md` before any re-run

## Don'ts (carried)
1. Don't commit brownfield targets / `_brownfield/`.
2. Don't `docker … prune -af` without naming what to keep (Milvus!).
3. Ctrl+C (SIGTERM) uvicorn, not kill -9 (A48 reaper) — but note a live SSE run
   blocks graceful shutdown; use the **⛔ End current Sprint** button to kill a
   live run cleanly, or kill -9 + manual reap if truly stuck.
4. Don't rush #3 (orchestrator surgery) — it's the one that can break the
   gate-retry loop.

---PROMPT END---
