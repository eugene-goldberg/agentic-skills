# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-06-07 (evening). Supersedes prior hand-offs.
> Every fact below was verified from the live repo/processes at write time.
> Where something is NOT verified it is marked **UNVERIFIED**.

---PROMPT START---

You are the architect of the agentic-skills project. Read `CLAUDE.md` first —
especially the operating principles: "quality over speed" (95% verified floor),
"persistence over abort" (no-abort doctrine). Only agentic-skills is
committed/pushed; brownfield targets and their `_brownfield/` are never committed
here.

## Operating note carried forward (BINDING on you, the architect)
Verification discipline — earned the hard way this session (I made two confident
wrong inferences about retrieval wiring before `meta.json` falsified them):
1. **No "X didn't happen / X is broken" claim until verified against the RAW
   source** (the authoritative artifact — `meta.json` cmd, `retrieval.jsonl`,
   raw stream), not a filtered grep. Watch the `orchestrator.`-prefix trap on
   `phase` fields.
2. **Verify first, report once.** No conclusions narrated mid-investigation.
3. **Mark every statement Verified vs Unverified-hypothesis.**

## Branch model (BINDING)
Work on **`development`**, fast-forward into **`main`** when verified. These two
are the ONLY live branches (all others are historical). `followup-dispatch-ui`
was merged + deleted 2026-06-07. **Both at `eee9ab0`, in sync, pushed.** Tree
clean except untracked `agentic_harness.png` (stray — ignore). Currently on
`development`. Scope harness tests to `tests/`:
`cd webapp/backend && .venv/bin/python -m pytest tests/ -q` → **335 passed**
(+1 KNOWN pre-existing flake `test_findings_ledger::test_concurrent_append_no_torn_lines`
— passes on re-run; not yours).

## Verified running processes (refreshed after the post-Exp-1b restart)
- **Harness orchestrator: PID 69546**, uvicorn `127.0.0.1:8000`. **Restarted
  2026-06-07 with current code — A56 is now LIVE** (verified: `run_brief` has the
  `warm_retrieval` param). It has all of this session's fixes (scorer-persistence,
  Janitor, item#1 gate, A56 warm-up). The NEXT sprint will run `retrieval_warmup`
  before the PO; confirm the PO grounds (≥1 `retrieval.jsonl` entry, no
  `po.grounding_unavailable`).
- Target dev servers (separate from harness): backend **PID 67691** `:8002` (on
  `integration`, the dependency feature live), frontend **PID 69699** `:3002`
  (dependency board UI). Use `localhost:3002`, NOT 127.0.0.1 (vite is IPv6-only).
  (PIDs drift across restarts — re-verify with `lsof -nP -iTCP:8000/:8002/:3002`.)
- Milvus stack up (3 containers; `milvus-minio` "unhealthy" = known healthcheck
  defect, not real). Ollama `bge-m3` up. **All retrieval is LOCAL** — Milvus
  `localhost:19530`, Ollama `127.0.0.1:11434`, graphify on-disk cache. There is
  NO external retrieval dependency (operator was emphatic about this).

## Experiment 1b — DONE (the dependencies sprint COMPLETED + probes run)
`run-20260607T135926Z-908991` finished `sprint_complete`: **6/6 merged_full**,
0 escalations, scores 94–97 Pass W/R, regression_checkpoint green, acceptance 0
findings. **The crew PASSED the no-telegraph discovery test** — all live probes
confirmed: transitive cycle A→B→C→A → 409; done-guard 409 on BOTH `PATCH
/tasks/{id}` AND `/move`; unblock-on-completion → 200. Full write-up in
`EXPERIMENT_dependencies_stress.md` §7. Caveat: this run's PO grounded BLIND (0
retrieval — A56 wasn't live), so the 6/6 happened *despite* PO grounding on
direct reads; A56 (below) closes that for future runs.

**The harness can now be safely restarted** (the run is terminal). The target
backend was already restarted onto `integration` for the probes (the dep feature
is live at `localhost:3002`/`:8002`).

## What this session shipped (all on `main` @ `eee9ab0`)
1. **Scorer scorecard persistence** (`15872ad`) — read-only scorer now gate-free
   ff-merges its `.agile-v/scorecards/<bl>.md`. Confirmed live (scorer
   merged=true, 97/100 on dependencies BL-0001).
2. **Janitor / Ops-Steward role, full §6 authority** (`15872ad`, **R16**) —
   `_janitor_flow` runs in the REAL repo to repair non-code failures
   (engineer infra_fail/error + QA-merge-failed); structural anomalies → I-7
   doctrine-meta; advisory (never aborts); R13 streaming-kill backstop. SKILLS
   renamed `…-ops`→`…-janitor`. **Deferred:** auto-rerun-after-repair (needs the
   per-BL body refactored into a retryable unit). See `PROPOSAL_OPS_STEWARD_ROLE.md` §11.
3. **Item #1 gate fix** (`dfc00df`) — `PYTEST_RESULT_RE` accepts `backend/tests/…`
   prefixes + `run_gate` exit-code fallback on unparseable (`-q`) output. Proven
   live: acceptance regression_checkpoint now `green` (was `inconclusive`).
   Corrected the prior hand-off's misattribution (cause = `-q` + regex anchor,
   NOT pytest 9.x).
4. **A56 retrieval readiness gate + PO grounding check** (`eee9ab0`, behind
   `warm_retrieval=True`) — warms the LOCAL backend before the PO so the first
   agent isn't grounding-blind; surfaces `po.grounding_unavailable` if a PO
   grounds 0. **External-free by construction** (forwards only Ollama/Milvus env,
   never Azure/OpenAI — tested). Verified live: `warm_retrieval` warms the local
   stack in 9.2s, ok=True. **Now LIVE on the harness (restarted 2026-06-07).**
5. **Crew stress-test program** — see below.

## Crew stress-test program (the strategic thread)
Operator pushed back that the toy target + additive features were weak evidence
for the mission. Established a 2-experiment program (`EXPERIMENT_*.md`):
- **Exp 1 — Kanban board + DnD + ordering** (`run-…T040112Z-ae3e0d`): landmine
  *telegraphed*. **Crew PASSED** 6/6 — handled the `create_all`-no-ALTER
  migration (`_migrate_task_rank`), wrote an optimistic-rollback Playwright
  journey, acceptance ✅ ACCEPT. `EXPERIMENT_kanban_stress.md` §9.
- **Exp 1b — Task Dependencies** (running now): landmine *NOT telegraphed* —
  tests discovery (transitive cycles, every-path done-guard). The fair "would a
  competent engineer get it right from a normal ticket?" test.
- **Exp 2 (future)** — a REAL third-party brownfield repo (substrate realism).
  `EXPERIMENT_dependencies_stress.md` §6.

## Open items (ledger)
- **A56** (filed `3afcb42`; fix shipped `eee9ab0`) — **fix is now LIVE** (harness
  restarted 2026-06-07). Mark RESOLVED after the FIRST new sprint shows a grounded
  PO (≥1 `retrieval.jsonl` entry, `retrieval_warmup.done`, no
  `po.grounding_unavailable`). Sub-items still open: (a) make retrieval an
  *eager* (non-deferred) tool; (b) **verify A51** `--strict-mcp-config` actually
  contains the deferred-tool/claude.ai layer (the PO saw Microsoft 365/Excalidraw
  despite it — do NOT assume A51 is intact).
- **Gate differential-detection on quiet output** — the regression checkpoint is
  green-by-exit-code on `-q` targets, not green-by-diff (Exp 1 caveat #3). Filing
  candidate.
- Janitor **auto-rerun-after-repair** (deferred increment, PROPOSAL §11).
- 20+ leftover `agent/*` branches on the target (reapable).

## Suggested next actions (operator to direct — do not start without approval)
1. **Confirm A56 live:** launch any new sprint and verify the PO grounds — the
   stream should show `orchestrator.retrieval_warmup.done`, the PO's
   `retrieval.jsonl` ≥1 grounded entry, and NO `po.grounding_unavailable`. If
   clean, mark A56 RESOLVED in the ledger.
2. Decide the frontier: **Exp 2 (real third-party brownfield repo** — substrate
   realism, the last untested mission dimension) vs. the A56 follow-ups (eager
   retrieval / A51 containment verification) vs. the gate-diff-on-quiet hardening.
3. Both crew stress experiments PASSED (Kanban telegraphed; dependencies
   discovery) — the worker-loop is well-evidenced. The unbuilt part of the
   mission remains the *cumulative* property + real-brownfield substrate.

---PROMPT END---
