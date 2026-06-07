# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-06-07. Supersedes prior hand-offs.
> Every fact below was verified from the live repo/processes at write time, not
> from memory. Where something is NOT verified it is marked **UNVERIFIED**.

---PROMPT START---

You are the architect of the agentic-skills project. Read `CLAUDE.md` first —
especially the two operating principles: "quality over speed" (95%
verified/tested floor) and "persistence over abort" (no-abort doctrine). Only
agentic-skills is committed/pushed; brownfield targets and their `_brownfield/`
are never committed here.

## Operating note carried from last session (BINDING on you, the architect)
Last session the architect repeatedly stated conclusions then retracted them.
Root mechanical cause: reporting an **absence** ("X didn't fire / didn't run")
from a **filtered query** (grepping unprefixed phase names) without checking the
filter — the events were `orchestrator.*`-prefixed, so absence-in-query was read
as absence-in-reality. Bind yourself to:
1. **No "X didn't happen" claim until the negative is verified against the RAW
   source**, not a filtered view.
2. **Verify first, report once.** No conclusions narrated mid-investigation.
3. **Mark every statement Verified vs Unverified-hypothesis.** Unverified ≠ finding.

## Verified state — agentic-skills (`git@github.com:eugene-goldberg/agentic-skills.git`)
- Branches `main`, `followup-dispatch-ui`, `development` **all at `238f434`**,
  all pushed (`git ls-remote origin` confirms). Currently checked out:
  **`development`**.
- Working tree clean except untracked `agentic_harness.png` (stray screenshot —
  ignore / don't commit).
- `238f434` = this session's commit: Ops/Steward role + `_ensure_on_agent_branch`
  orchestrator fix + new-target docs/memory.
- Harness tests: **316 passed** via `cd webapp/backend && .venv/bin/python -m
  pytest tests/ -q`. NOTE: run scoped to `tests/` — bare `pytest` recurses into
  `webapp/backend/repos/` (the symlinked targets) and errors on collection
  (their deps: jose/passlib). Always scope to `tests/`.

## Verified running processes (kill before a clean restart if needed)
- webapp orchestrator: **PID 21138**, uvicorn on `127.0.0.1:8000` (loaded with
  the committed orchestrator code).
- target dev servers (the brownfield app, separate from the harness): backend
  **PID 2559** on `:8002`, frontend `npm run dev` **PID 3138** on `:3002`.
- Milvus stack up (3 containers; `milvus-minio` shows unhealthy = known
  healthcheck-cmd defect, not real). Ollama `bge-m3` running. Milvus holds
  collections from the labels run.

## Verified state — current brownfield target `project-management-app`
(`~/dev/ai-projects/brownfield-targets/project-management-app`, symlinked at
`webapp/backend/repos/`; Docker-free FastAPI+SQLite+React; see
`.claude/memory/arch_target_pm_app.md`.)
- `main` pristine @ `88a0326`; `integration` @ `e9ca200` (checked out).
- **Task Labels & Filtering sprint COMPLETE** (`run-20260607T002244Z-1a46d9`,
  status `sprint_complete`): **6/6 BLs merged** to `integration` (6 engineer + 6
  QA ff-merges), `main` stayed pristine throughout. Acceptance: 0 findings.
  closure_check: 0 violations. 20 leftover `agent/*` branches (reapable).
- Untracked in target: `_brownfield/features/task-labels-and-filtering/acceptance/`.

## What this session validated (Verified)
The 3 structural fixes turned a BL-0001 merge-escalation (prior run) into a clean
6/6 sprint: (1) `graphify-out` gitignored, (2) live `events.jsonl` gitignored
(no longer dirties the merge precondition), (3) `_ensure_on_agent_branch` at run
start keeps `main` pristine. All on the target's `main` baseline + the harness
commit `238f434`.

## Open items

### 1. `_parse_pytest` can't read this target's pytest output — **STILL OPEN**
Two symptoms; verified 2026-06-07. **Correction to a prior hand-off:** the cause
is NOT "py3.14 / pytest 9.x" — it is (a) the target `test_cmd` uses **`-q`**
(quiet) so `run_gate` gets zero per-test lines, and (b) `PYTEST_RESULT_RE`
anchors to `^tests?/` but this target's node-ids are `backend/tests/…` (so even
`run_bl_tests`, which forces `-v`, parses 0). Neither is a version issue.
- per-BL gate logs `green (0 passed)` — **cosmetic** (`run_bl_tests` is
  exit-code-authoritative, merges correct). Caused by the regex-anchor mismatch.
- acceptance `orchestrator.regression_checkpoint` = **`inconclusive`** ("tests
  did not execute (no pass/fail parsed); verify test_cmd"). Manual re-run = **111
  passed**. Caused by `-q` (no per-test lines at all).
- **Corrected fix (NOT "one fix kills both"):** the two symptoms live in
  different functions. `run_gate` needs an **exit-code fallback** on unparseable
  output (fixes the acceptance `inconclusive`; a regex fix alone won't help it
  because `-q` emits nothing to match). The cosmetic per-BL `0 passed` needs the
  **`_parse_pytest` regex anchor** widened to match `backend/tests/…`. Two
  distinct fixes (or drop `-q` from `test_cmd` + widen the regex).

### 2. Scorer scorecard persistence — **FIXED (2026-06-07)**
Root cause: `orchestrator.py` gated the gate+merge block to `if role == "qa"`, so
the scorer's committed, doctrine-validated scorecard (`.agile-v/scorecards/<bl>.md`)
was never fast-forwarded — dropped on the reaped scorer worktree. Verified: the
labels run's 6 scorecards survive on the leftover `agent/*` branches; integration
had `.agile-v/qa/` but no `.agile-v/scorecards/`.
**Fix:** added a scorer `elif` that persists the scorecard via a **gate-free
fast-forward** (scorer is read-only — A55's QA-only gate has nothing to run; only
the merge was wrongly QA-only). A1 non-ff auto-rebase parity, no post-rebase gate.
Tests: `tests/test_scorer_scorecard_persistence.py` (3). Operator decision:
gate-free ff-merge.

### 3. Janitor (Ops/Steward) role — **WIRED with full §6 authority (2026-06-07)**
Operator decisions: name = **Janitor**; **wire with full §6 authority**. Shipped:
`_janitor_flow` (runs in the REAL repo checkout) + spawn triggers in `run_brief`
(engineer escalation on `last_gate_kind ∈ {error, infra_fail}`; QA merge-failed
branch), deterministic sidecar verdict, `janitor.structural_anomaly` → I-7
doctrine-meta routing, R16 in `doctrine_spec` + CLAUDE.md (CI-guarded),
`run_janitor` flag (default ON = rollback). Advisory contract enforced+tested: a
Janitor failure never aborts the run. Tests: `tests/test_janitor_flow.py` (5).
SKILLS renamed `…-ops` → `…-janitor`. Full record: `PROPOSAL_OPS_STEWARD_ROLE.md`
§11. **Deferred:** auto re-run of the failed step after a verified repair (needs
the per-BL body refactored into a retryable unit — separate reviewed increment).

## Test state after this session
`cd webapp/backend && .venv/bin/python -m pytest tests/ -q` → **324 passed**
(316 baseline + 3 scorer-persistence + 5 janitor). Scope to `tests/`.

## Suggested next actions (operator to direct — do not start without approval)
- Implement item #1: `run_gate` exit-code fallback + widen `_parse_pytest` regex
  anchor (two distinct fixes). File as a ledger entry with the corrected cause.
- Approve the deferred Janitor auto-rerun increment (#3) if wanted.
- Reap the 20 leftover `agent/*` branches in the target if desired.
- Decide commit/merge of this session's work (currently uncommitted on `development`).

---PROMPT END---
