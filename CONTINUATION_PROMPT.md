# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-06-06 (evening). Supersedes prior hand-offs.

---PROMPT START---

You are the architect of the agentic-skills project. Read `CLAUDE.md` first —
especially the two **operating principles**: "quality over speed" (95%
verified/tested floor) and "persistence over abort" (the no-abort doctrine).
Only agentic-skills is committed/pushed; brownfield targets and their
`_brownfield/` are never committed here.

## State (all committed AND pushed)
- **Branch `followup-dispatch-ui` @ `4b4be93`**, pushed, working tree clean
  (only untracked `agentic_harness.png`, a stray screenshot — ignore).
- Backend suite: **315 passed** (`cd webapp/backend && .venv/bin/python -m pytest
  tests/ --deselect tests/test_findings_ledger.py::test_concurrent_append_no_torn_lines`).
- uvicorn live PID ~93785 on `4b4be93` (restart only if you change backend code).

## What this session shipped (3 binding doctrine/control-plane changes)
1. **A54 — no-abort persistence doctrine** (operator-BINDING): abort = failure.
   Every agent investigates→fix→re-test until resolved; per-role fix loops deep
   (`MAX_FIX_ATTEMPTS=6`, was 2); on exhaustion → terminal **`escalated`** +
   dossier (Option A), never routine `aborted`. Root-cause mandate in
   `build_gate_fix_prompt`. Codified in CLAUDE.md + `feedback_no_abort_persistence`.
2. **A49 fix #2 + A53** — gate fidelity (same-SHA green memory + single re-sample,
   never blind-flips red→green) + auto-merge atomicity (rollback engineer merge
   on BL-abort/escalate via `git_worktree.reset_target_to`).
3. **A55 — SIMPLE gating model** (operator-BINDING, the big one): **per-BL runs
   ONLY the BL's own unit tests** (`regression_gate.run_bl_tests`, scoped to the
   BL's changed test files, db-only stack — NO full suite, NO Playwright). The
   FULL suite + Playwright E2E run **once at the acceptance phase**
   (`regression_checkpoint` + the acceptance agent; API always, Playwright iff UI
   journeys). Codified in CLAUDE.md ("Gating model — SIMPLE") +
   `feedback_simple_gating_model`. **Do not re-complicate the gate.**

## ⭐ THE KEY FINDING (resolves the "why can't the crew do a trivial BL" puzzle)
The BL-0001 "capability wall" of the prior runs was a **HARNESS artifact, not
crew incapability.** Evidence (item-comments run `…251422`, BL-0001):
- The old per-BL gate was **diff-blind** — it ran the full lint+backend+Playwright
  suite on a *backend-only* BL, and load-induced Playwright flakes produced
  **false reds** on a byte-identical frontend; the no-abort loop then thrashed
  6→157. The crew's commit was correct (zero frontend files touched).
- The engineer is **NOT blind/incompetent**: its trace shows **111 Bash calls** —
  it spun its own Postgres, ran `pytest` iteratively, `ruff`/`mypy`,
  `psql`-debugged auth. A competent local dev loop, like normal Claude Code.
- **With the simple gate (this session), BL-0001 reached GREEN** (19 passed) in
  2 fix attempts on a clean scoped signal. `pytest-randomly` is NOT in the
  target deps, so order is deterministic; the 3→4→green was normal iteration.
- **Lesson:** we over-invested in the control plane and mis-attributed
  harness-induced false-reds as crew-capability limits. The simple gate gives an
  honest signal and the crew converges.

## ⭐ LIVE RUN — monitor it (do NOT kill unless it wedges)
`run-20260606T190150Z-ce9b56` (item-comments, target full-stack-fastapi-template)
is **live and healthy**, validating the simple gating model end-to-end.
- BL-0001 bl_tests went **green (19 passed)** at 20:01 → should merge → QA → BL-0002…
- Tail: `/tmp/item-comments-brief/run.sse.log`; durable log:
  `<target>/_brownfield/features/item-comments-and-activity/events.jsonl`.
- Status check pattern (reuse): read `.orchestrator-state/done/*ce9b56*` for
  terminal; grep events.jsonl for `phase":"bl_tests"` verdicts + `bl.done` /
  `merge_to_target` / `escalated` / `regression_checkpoint` / `acceptance`.
- This is the **first live run of `run_bl_tests`** — the acceptance-phase
  full-suite `regression_checkpoint` + whole-feature E2E have NOT been exercised
  live yet; watch them when the run reaches acceptance.

### First actions next session
1. Check `ce9b56` status. If still live → monitor to terminal (expect clean BL
   merges + acceptance). If `sprint_complete` → **the simple model is fully
   validated end-to-end** (record it). If `escalated` → read the dossier (real
   crew limit) — that's now an HONEST signal, not a false-red.
2. If it wedged/stuck → kill via TaskStop the launcher + `POST /end-sprint
   {purge_images:true}` (python urllib; curl is hook-blocked), then reset trunk
   `git reset --hard e74ac82` + remove orphan containers before any re-run.

## Open / deferred (lower priority now)
- **Test-isolation discipline** for the comment tests (cross-session
  `test_delete_comment` family) — make them order-independent; minor since gate
  order is deterministic (no pytest-randomly).
- **Frontend-BL unit-test wrinkle**: target has no frontend unit harness (only
  Playwright + biome); frontend BLs are lint-gated per-BL + validated at
  acceptance E2E. Add vitest later if per-BL frontend unit coverage is wanted.
- **AUDIT_PROPOSAL_2026-06-06.md** (governance 32→~20 consolidation + I-8 Gate
  Fidelity invariant) — still awaiting operator action.
- A "getting-worse circuit-breaker" (escalate when failure count increases) —
  proposed, not built; lower priority since BL-0001 converged.

## Don'ts
1. Don't commit brownfield targets / `_brownfield/`.
2. Don't re-complicate the per-BL gate (A55 — operator-binding simple model).
3. Don't `docker prune -af` without naming what to keep (Milvus!).
4. Ctrl+C (SIGTERM) uvicorn, not kill -9. curl is hook-blocked → use python urllib.
5. Don't claim a finding without reading the actual source/trace (95% floor) —
   this session twice flipped a wrong hypothesis after reading the evidence
   (engineer "over-reached scope" → false; engineer "flies blind" → false).

## Reading order
1. `CLAUDE.md` (both operating principles + gating model)
2. Memories: `feedback_no_abort_persistence`, `feedback_simple_gating_model`,
   `arch_active_branch`
3. `DESIGN_SHORTCOMINGS.md` A55 / A54 / A53 / A49
4. `AUDIT_PROPOSAL_2026-06-06.md`

---PROMPT END---
