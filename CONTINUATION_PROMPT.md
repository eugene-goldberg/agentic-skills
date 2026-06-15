# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-06-15. Supersedes all prior hand-offs. **Headline: this session
> (1) delivered the ORDER FULFILLMENT feature 100% live-accepted, (2) live-proved the wave
> program P1–P3, (3) fixed a real acceptance-reround harness bug, and (4) BUILT and
> LIVE-PROVED wave concurrency>1 (true intra-wave parallelism) end-to-end. Concurrency lives
> on branch `wave-concurrency` (NOT yet merged to dev/main) — two follow-ups gate the merge.**

---PROMPT START---

You are the **architect** of agentic-skills. Read `CLAUDE.md` + `THESIS.md` first. Mission:
a fully autonomous AI crew that ships complex features into real brownfield repos with no
human — grounded, self-correcting, honest, cumulative. Honor `.claude/memory/`.

## TWO BINDING WORKFLOW DIRECTIVES (operator 2026-06-14) — still in force
1. **REMOTE-FIRST development.** ALL crew/harness code (`webapp/`, `langgraph_engine/`,
   `skills/`, `rubrics/`, tests) is **edited AND tested on the remote `192.168.12.180`**,
   then synced **remote → GitHub → Mac** (Mac = read-only mirror). Your Edit/Write target the
   Mac FS, so remote edits go over SSH: read the file, apply a uniqueness-checked python
   in-place replace ON the remote (for large/delicate edits, base64-transfer an edit script to
   `/tmp` and run it — heredocs over SSH single-quotes mangle `'''`/apostrophes/`$`), run the
   remote suite. See `.claude/memory/feedback_remote_first_dev.md`.
2. **95% verified confidence before ANY claim.** Verify against a re-openable artifact (a
   command that ran, a file that exists, a test that passed, a log line). Below 95%: state the
   confidence + the resolving check. The operator caught real over-claims this session — hold to
   "is it called yet (grep)?" / "what's the committed SHA + test count?" / "did a live run prove
   it?" not prose.

## VERIFIED CURRENT STATE (checked 2026-06-15)
- **Git (agentic-skills), all synced Mac ≡ remote ≡ origin/GitHub:**
  - `development` = `main` = **`50f86d5`** (acceptance reround worktree-collision FIX `c8ccc76`
    + real-git integration test).
  - **`wave-concurrency` = `f7419e9`** (the whole concurrency build, AHEAD of main; NOT merged).
    Remote working tree + harness are on this branch. `557` tests pass (serial path byte-identical).
- **Remote harness**: uvicorn `127.0.0.1:8000`, **pid 2495664** (drifts on restart — re-check
  `lsof -tnP -iTCP:8000 -sTCP:LISTEN`), on `wave-concurrency` code (`3e7efd5`'s code; the later
  `f7419e9` was docs/memory only). NO active run.
- **Services up**: Milvus (:19530), Ollama (bge-m3, :11434), `ecommerce-pg` (postgres:16 :5433).
- **Target**: `fullstack-ecommerce-app` on branch `integration` @ **`07ab2cd`** (carries the
  order-fulfillment feature + the 2 diag endpoints from the concurrency live-proof), checkout
  clean. The target is a SEPARATE git repo (its own remote; NOT on the agentic-skills GitHub).

## REMOTE ACCESS
SSH: `ssh -i ~/.ssh/id_ed25519_18012 -o IdentitiesOnly=yes user@192.168.12.180`. Strip banner:
`| grep -v "post-quantum\|store now\|may need to be upgraded\|openssh.com"`. Remote pushes to
GitHub via deploy key (repo `core.sshCommand` set). Loop: edit on remote → `pytest tests/` on
remote → commit on remote (`git commit -F <file>`; NO backticks in `-m`) → `git push origin` →
Mac `git fetch && reset --hard origin/<branch>` (Mac-local governance edits get clobbered by
reset — commit them on the remote first, as done this session). Harness restart (no active run):
`cd ~/dev/ai-projects/agentic-skills/webapp/backend && nohup env PATH="$HOME/.local/bin:$PATH"
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >> ~/harness.log 2>&1 &
disown` — uvicorn has NO hot-reload; restart after deploying code edits, verify via source grep
not sha. Run a sprint: `POST /api/projects/<repo>/run-brief` (payload = brief + flags); standalone
acceptance: `POST /api/projects/<repo>/run-acceptance` (single-shot, needs a FRESH run_id).

## WHAT SHIPPED THIS SESSION (all verified)
- **`[x]` ORDER FULFILLMENT feature 100% LIVE-ACCEPTED** — run-20260614T143621Z-0b7c91 (5 BLs,
  state machine + RBAC + customer tracker UI + admin console UI). Acceptance found 2 real UI bugs,
  auto-fixed them, then a harness reround bug forced an escalation → FIXED (`c8ccc76`) → re-run
  `reacc2` integrity_ok=true, 11/11 journeys. A55-class baseline-lint false-red hand-fixed (target
  `cf20499`). integration @ delivered. See `.claude/memory/arch_order_fulfillment_wave_proof.md`.
- **`[x]` Wave program P1+P2+P3 LIVE-PROVEN** — the order-fulfillment run ran with
  `wave_execution=True`: R21 DAG gate, 4 waves, 4 barrier reindexes (1/wave, 0 per-BL), regression
  green.
- **`[x]` Acceptance-reround worktree-collision bug FIXED** (`c8ccc76`, on dev/main) —
  `_accept_worktree_task_id` (round-unique branch) + real-git integration test. End-to-end reround
  `[~]` (mechanism proven; a natural reround not yet observed clean).
- **`[x]` WAVE CONCURRENCY>1 BUILT + LIVE-PROVEN** (branch `wave-concurrency` @ `f7419e9`, Strategy
  A). Primitives: `_merge_streams` (async fan-in), `merge_branch_into_target` (real 3-way barrier
  merge, `git_worktree.py:264`), `_run_wave_concurrent` (orchestration), `_one_bl_concurrent` +
  the `_concurrent_wave_mode` dispatch in `run_brief` (`orchestrator.py`; `_run_wave_concurrent`
  CALLED at ~`:4461`). Flag `wave_concurrency:int=1` (>1 opt-in; serial byte-identical). LIVE PROOF
  run-20260615T010822Z-36f623 (`wave_concurrency=2`, 2 independent diag endpoints → 1 wave
  [BL-0001,BL-0002]): both engineers spawned the SAME second, overlapping, 2 concurrent agents,
  both `work_ready` (defer-merge); assembled both ok in BL-id order (0 conflicts); both
  merged_full; delivered to integration; `sprint_complete`; checkout clean back on `integration`.
  **Only BL-0001+BL-0002 verified concurrent — happy-path, disjoint, 2-wide, single wave, one run.**

## OPEN FOLLOW-UPS (gate the `wave-concurrency` → dev/main merge)
1. **BL-0001 noop/early-merge NUANCE (investigate first).** In the proof, BL-0001 assembled as
   `kind:noop` (already in integration) and its commits sit DIRECTLY on integration while BL-0002
   came via a merge commit — suggests BL-0001 may not have FULLY deferred its trunk merge (likely
   the engineer non_ff rebase path or QA `merge_target_override` lineage landing it early). Harmless
   on disjoint BLs, but under a real file conflict it could matter. Root-cause in `_one_bl_concurrent`
   + `_engineer_flow(defer_merge)` rebase path + `_qa_or_scorer_flow(merge_target_override)`.
2. **Conflicting-pair live test** — run a `wave_concurrency=2` sprint with two BLs that edit the
   SAME file/line, prove `merge_branch_into_target` reports `conflict` + the BL routes to no-abort +
   siblings still assemble + trunk stays deterministic. This is the untested half of Strategy A.
3. **Scale** — a 3+ BL wave and/or multi-wave concurrent run (concurrency cap = `min(wave,flag,
   cpu//2)`); confirm no resource blowup.
4. **THEN merge `wave-concurrency` → development → main** (FF), restart harness, update CLAUDE.md
   R-table/doc-index for `wave_concurrency`.
5. Lower priority: reindex incremental/has_index short-circuit; leaked `agent/accept-*` branches +
   stale vite procs hygiene; the A55-class diff-scope-acceptance-lint crew fix.

## HONEST VERIFICATION LEDGER
`[x]` order-fulfillment 100% accepted · `[x]` wave P1–P3 proven · `[x]` reround worktree fix
(c8ccc76, real-git tested) · `[x]` concurrency>1 BUILT + LIVE-PROVEN happy-path (run-…36f623, 2
disjoint BLs) · `[~]` concurrency conflict-path NOT tested · `[~]` concurrency scale (3+ / multi-
wave) NOT tested · `[~]` BL-0001 full-defer nuance OPEN · `[ ]` concurrency NOT merged to dev/main.

---PROMPT END---
