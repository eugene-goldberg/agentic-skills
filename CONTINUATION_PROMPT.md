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

## Open items (Verified findings from the labels run — NOT yet fixed/filed)
1. **`_parse_pytest` doesn't parse this target's pytest summary** (py3.14 /
   pytest 9.x). Two symptoms, one cause:
   - per-BL gate logs `green (0 passed)` — **cosmetic only** (`run_bl_tests` is
     exit-code-authoritative, so merges are correct).
   - acceptance `orchestrator.regression_checkpoint` returned **`inconclusive`**
     ("tests did not execute (no pass/fail parsed); verify test_cmd") instead of
     green. Manual re-run of the assembled suite = **111 passed** (so the feature
     is actually clean; the checkpoint just couldn't read it).
   - Proposed fix: make `run_gate` fall back to exit-code-authoritative on
     unparseable output (mirror the A55 `run_bl_tests` fix) and/or repair the
     `_parse_pytest` summary regex. One fix kills both symptoms.
2. **Scorer no longer persists scorecards.** Scorer ran 6/6 (`doctrine_ok=True`)
   but `merged=False` for all — because `orchestrator.py:690` gates the
   gate+merge block to `if role == "qa"`, so the scorer path never merges. On the
   old target, `score(BL-…)` commits landed on integration; under A55 they don't.
   Design call: persist scorecards (merge/copy-back) or accept trace-only +
   document. Currently silently neither.
3. **Ops/Steward role** (`PROPOSAL_OPS_STEWARD_ROLE.md` +
   `skills/brownfield/brownfield-production-incremental-ops/SKILLS.md`) is
   committed as a **proposal + SKILLS only** — NOT wired into the orchestrator
   (no `_ops_flow`, no spawn trigger). Operator open questions in §10 unanswered.

## Suggested next actions (operator to direct — do not start without approval)
- File open items #1 and #2 as ledger entries with the corrected evidence.
- Implement the `run_gate` exit-code fallback (#1) — small, high-value.
- Decide scorecard persistence (#2).
- Decide whether to wire the Ops/Steward role (#3) or leave as proposal.
- Reap the 20 leftover `agent/*` branches in the target if desired.

---PROMPT END---
