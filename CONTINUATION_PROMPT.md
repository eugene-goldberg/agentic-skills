# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-08-15. This session: (1) full-code-audit that
> identified mission-blocking flaws C1–C5/M1–M4 (ledger A49–A57);
> (2) `AUTONOMY_HARDENING_PLAN.md` authorized (decisions D1–D6);
> (3) **Batches 0–7 executed and committed** on the new branch
> `autonomy-hardening` (off `architect-prereqs` @ `8745331`).
> Backend suite: **291/291** (was 208; Batches 5–7 landed 2026-08-16).
>
> ⚠️ **Machine migration:** this checkout now lives under
> `/Users/egoldberg` (was `/Users/eugenegoldberg`). venv + memory
> symlink restored; **brownfield targets, Milvus, Ollama are still
> missing** (tracker 0-3/0-4 — operator-blocked).

---PROMPT START---

You are picking up the agentic-skills project. **You are the architect.**
Read `CLAUDE.md` first — especially "Operating principle: quality over
speed" (the 95% verified/tested certainty floor and narrative-momentum
rule).

## 1. Identity

**agentic-skills** — autonomous synthetic AI crew for brownfield feature
delivery. Operator: Eugene Goldberg. Active branch: **`autonomy-hardening`**
(NOT architect-prereqs; that is its parent).

## 2. State at hand-off — autonomy-hardening Batches 0–7 shipped

Read `AUTONOMY_HARDENING_PLAN.md` (the why + decisions D1–D6) and
`AUTONOMY_HARDENING_TRACKER.md` (live status). Commits:

| Commit | Batch | What |
|---|---|---|
| `5b3b31f` | 0 | plan authorized; ledger A49–A57 filed; env partially restored |
| `f333e20` | 1 (C1/A34) | detached runs: run_registry, `POST /run-brief {detached:true}` → 202, resumable `GET /api/runs/{id}/events`, explicit `/abort`; disconnect never kills a run |
| `1868229` | 2 (C4) | gate `build_fail` kind + `gate_failure_class` + regressed⇒non-empty invariant (A39); api_error = infra-retry, no budget burn (A44); idle clock suspended while a tool is in flight (A45); A54–A57 |
| `9728f0a` | 3 (C2) | dependency DAG now GATES (`deferred_dep`, A49); triage agent v1 (RETRY_REWRITE×1 / DEFER / ESCALATE, enum-constrained, DEFER fallback) + **R16**; `run_triage` flag-OFF |
| `f2ab112` | 4 (C3/A50) | Fail verdict → `merged_score_failed` + `score_failed` + scorer-context triage; `revert_bl_span` + operator-gated `POST /revert-bl {confirm:true}` |
| `f5ab92c` | 5 (C5) | A29 PRE-baseline gate cache (SHA-keyed, ~50% gate time); cost aggregation (`bl.done cost_usd`, `sprint_complete total_cost_usd`/`cost_by_role`); `max_sprint_usd` cap → `deferred_budget` |
| `9e33cfc` | 6 (M1) | `LESSONS.jsonl`: resolved retries append failure signatures; last 10 injected into engineer/QA prompts; exported to trace archive for doctrine-meta |
| `855f62b` | 7 (M2–M4) | A51 checkout preflight + verified PO commit; A53 indexer health + mid-sprint Milvus restart + loud `indexing_degraded`; A52 agent env allowlist + HARNESS.md §11 trust model |

**How to run the suite:** `cd webapp/backend && .venv/bin/python -m
pytest tests/ -q -p no:cacheprovider` → 291/291. venv is uv-managed
Python 3.12 (`~/.local/bin/uv`).

## 3. Open work (in priority order)

1. **AUTONOMY_HARDENING_PLAN.md is fully executed** (Batches 0–7;
   commits `f5ab92c` Batch 5, `9e33cfc` Batch 6, Batch 7 in the
   tracker-final commit; suite **291/291**). Only 5-1 (target-side
   playwright workers) remains, blocked on the environment.
2. **Environment restore (tracker 0-3/0-4, operator-blocked):**
   brownfield target (old-machine backup or fresh clone +
   `RUNBOOK_clean_brownfield_reset.md`), Milvus stack, Ollama+bge-m3.
   Blocks all live smokes, Batch E of ABL-0015, and calibration sprints.
3. **Calibration sprints (operator-gated):** one clean `run_triage=true`
   sprint → propose D1 default flip; ABL-0015 Batch E (Journey 03) —
   note its findings-ledger state lived on the lost target checkout.
4. **ARCHITECT_PLAN.md Batches C/D/E/G** — still proposed/unstarted
   (framework-reviewer, observer, doctrine-spec, governance hygiene).
   Note G-1 grew: ARCHITECTURE_INVARIANTS.md I-2 table now also lacks
   R14/R15/R16 rows; the empty-cells matrix predates Batches 1–4.

## 4. New flags (all default-preserving)

| Flag | Default | Flip condition |
|---|---|---|
| `detached` (run-brief) | False | none — opt-in per call |
| `run_triage` | False | 1 clean triage-ON calibration sprint (D1) |
| `run_acceptance_followup` | False | ABL-0015 Batch E live smoke |

## 5. Don'ts (carried + new)

1. Don't `docker system prune` without naming what to keep.
2. Don't skip `PREFLIGHT.md` before any live sprint.
3. Don't force-kill uvicorn (SIGTERM only — reapers).
4. Don't trust `.venv/bin/python` from an unexpected cwd — the Bash
   session persists its working directory.
5. The A45 test file (`test_a45_idle_busy.py`) is timing-sensitive:
   fake-CLI spawn costs ~2.1s on this Mac (argv assessment). If it
   flakes, widen margins — do not weaken the assertions.

---PROMPT END---
