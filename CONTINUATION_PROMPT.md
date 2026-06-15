# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-06-15. Supersedes all prior hand-offs. **Headline: wave
> concurrency (`wave_concurrency>1`, intra-wave Strategy A) is now BUILT, fully
> LIVE-PROVEN across happy-path + conflicting-pair + 3-wide/multi-wave scale, and
> MERGED into `development` and `main` (FF, `4265640`). The three follow-ups that
> gated the merge are all closed. Only lower-priority hardening + one scope
> decision remain.**

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
   `/tmp` and run it — heredocs over SSH single-quotes mangle quotes/apostrophes/`$`), run the
   remote suite. See `.claude/memory/feedback_remote_first_dev.md`.
2. **95% verified confidence before ANY claim.** Verify against a re-openable artifact (a
   command that ran, a file that exists, a test that passed, a log line). Below 95%: state the
   confidence + the resolving check.

## VERIFIED CURRENT STATE (checked 2026-06-15)
- **Git (agentic-skills), all synced Mac ≡ remote ≡ origin/GitHub:**
  - `development` = `main` = `wave-concurrency` = **`4265640`** (clean). The whole wave-
    concurrency line is now folded into the live branches; `wave-concurrency` is retained but
    no longer ahead.
- **Remote harness**: uvicorn `127.0.0.1:8000`, **pid 2727315** (drifts on restart — re-check
  `lsof -tnP -iTCP:8000 -sTCP:LISTEN`), on `development` @ `4265640`. NO active run.
  **563 tests pass** on the remote venv.
- **Services up**: Milvus (:19530), Ollama (bge-m3, :11434), `ecommerce-pg` (postgres:16 :5433).
- **Target**: `fullstack-ecommerce-app` on branch `integration` @ **`07ab2cd`** (order-
  fulfillment + the 2 concurrency-liveproof diag endpoints), checkout clean, all throwaway
  test branches pruned. SEPARATE git repo (its own remote; NOT on the agentic-skills GitHub).

## REMOTE ACCESS
SSH: `ssh -i ~/.ssh/id_ed25519_18012 -o IdentitiesOnly=yes user@192.168.12.180`. Strip banner:
`| grep -v "post-quantum\|store now\|may need to be upgraded\|openssh.com"`. Remote pushes to
GitHub via deploy key (repo `core.sshCommand` set). Loop: edit on remote → `pytest tests/` on
remote → commit on remote (`git commit -F <file>`; NO backticks/heredoc-hostile chars in `-m`)
→ `git push origin` → Mac `git fetch && reset --hard origin/<branch>`. Harness restart (no
active run): `cd ~/dev/ai-projects/agentic-skills/webapp/backend && nohup env
PATH="$HOME/.local/bin:$PATH" .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port
8000 >> ~/harness.log 2>&1 & disown` — uvicorn has NO hot-reload; restart after deploying code
edits, verify via source grep not sha. Run a sprint: `POST /api/projects/<repo>/run-brief`
(payload = brief + flags). To launch a CONTROLLED skip_po test: hand-author + commit a
`_brownfield/features/<slug>/BACKLOG.md` (+ brief.md, _codebase_context/CODEBASE_CONTEXT.md,
per-BL codebase_context.md dirs) on the target's `integration`, then POST with
`{skip_po:true, feature_name:"<slug>", wave_execution:true, wave_concurrency:N,
run_acceptance:false, run_doctrine_meta:false, inject_lessons:false}`. SSE log: detach with
`setsid bash -c "curl -sN ... > ~/x.log 2>&1" < /dev/null &` (a backgrounded curl in the SAME
SSH shell as a stdin pipe races the pipe → empty body → 422; transfer payload in a SEPARATE
ssh call first).

## WHAT SHIPPED THIS SESSION (all verified, all on `4265640`)
- **`[x]` Follow-up #1 — scorer mid-wave trunk-leak FIXED** (`6c5f45e`). Root cause of the
  BL-0001 noop nuance: the scorer in `_one_bl_concurrent` was called WITHOUT
  `merge_target_override`, so `_qa_or_scorer_flow` defaulted `_merge_target` to the trunk and
  its scorecard FF-merge landed BL work on the trunk mid-wave. Fix: pass
  `merge_target_override=work_branch` (symmetric with QA). AST regression guard
  (`test_concurrent_scorer_defer.py`). LIVE-PROVEN: BL-0001 now assembles as `kind:merged`
  via the barrier, not `noop`.
- **`[x]` Follow-up #2 — conflicting-pair live test + I-5 honesty FIX** (`1c7c02f`). Run
  `run-20260615T024030Z-bcef22` (then re-proof `…033033Z-1dc152` on a clean baseline): two
  same-wave BLs both create `ConflictProbe.cs` → BL-0001 assembled `merged`, BL-0002 → real
  git add/add `kind:conflict` → `bl.escalated(role=assembly)` no-abort, trunk = alpha only
  (deterministic), BL-0002 work preserved on its branch, `sprint_complete` (not aborted). The
  run exposed an I-5 bug — `bl_outcomes` mislabeled the conflicted BL as `merged_full`; fixed
  via extracted+unit-tested `_reconcile_unassembled_outcome` (→ `escalated_assembly_conflict`),
  live-confirmed in the re-proof.
- **`[x]` Follow-up #3 — scale test** (run `run-20260615T041351Z-fc2e21`). 5 disjoint diag-
  endpoint BLs, `wave_concurrency=3`: wave 0 = [BL-0001,2,3] ran 3-WIDE concurrent, wave 1 =
  [BL-0004,5] ran 2-WIDE concurrent after the wave-0 barrier reindex. All 5 assembled
  `kind:merged` in BL-id order, 0 escalations, all `merged_full`, trunk carried all 5
  endpoints+tests. NO resource blowup (52GB free, load ~6/12 cores at peak). cap
  `min(wave,flag,cpu//2)` honored (cpu//2=6 on this 12-core host).
- **`[x]` Follow-up #4 — MERGED + docs** (`4265640`). FF `wave-concurrency`→`development`→
  `main`. Fixed the stale `projects.py` "inert until fan-in lands" comment; extended the
  CLAUDE.md R21 row to document Phase 5 (`wave_concurrency>1`). Harness restarted on the merged
  code. Bonus hygiene: pruned ~120 leaked `agent/*` branches on the target across the session.

## OPEN FOLLOW-UPS (none block anything that's shipped)
1. **SCOPE DECISION (operator) — assembly-conflict auto-repair loop.** Today a same-wave file
   conflict is surfaced + escalated (`escalated_assembly_<kind>`), which is the CORRECT
   *terminal* behavior for a TRUE semantic conflict (can't auto-reconcile contradictory intent)
   and is the floor. The Grok assessment (`Concurrency_Assessment_01.md`) notes
   `PROPOSAL_WAVE_CONCURRENCY.md` §4/§7 may envision an auto-rebase-retry loop for SPURIOUS
   (adjacent-hunk) conflicts. R21's contract gate is meant to keep wave-mates file-disjoint, so
   same-wave conflicts should be rare. Decide: build auto-rebase-retry (enhancement) or document
   surface-and-escalate as the accepted behavior. VERIFY proposal §4/§7 text before treating as
   required.
2. **Reindex latency** — `index_initial` + each `reindex_after_wave.<n>` runs a FULL CPU
   `op=index` (~6–8 min each on bge-m3); the scale run spent ~20 min just indexing. The
   has_index short-circuit guards only the SEARCH path, not index_initial/reindex. An
   incremental/has_index short-circuit for the reindex barriers would cut wall-clock materially.
3. **Hygiene** — one stale `vite` proc (pid was 1295214) + its leaked worktree
   `~/dev/ai-projects/brownfield-targets/.agent-worktrees/accept-run-20260613T124519Z-05b6e9`
   still need reaping. Sweep `.agent-worktrees/` for orphans.
4. **Lower-priority hardening** (Grok assessment §3.3/§3.4, none blocking): dedicated
   `wave_concurrency=1` byte-identical regression test; disk-preflight scaling by k +
   `wave.concurrency_degraded` event; `in_flight_bls` checkpoint + sidecar lock for mid-wave
   crash resume; A55-class diff-scope acceptance-lint crew fix.

## HONEST VERIFICATION LEDGER
`[x]` #1 scorer fix (6c5f45e, AST-tested, live-proven kind=merged) · `[x]` #2 conflict path +
I-5 reconcile (1c7c02f, 4 unit tests + 2 live runs, bl_outcomes honest) · `[x]` #3 scale
(fc2e21: 3-wide + 2-wide multi-wave, 5/5 merged, no blowup) · `[x]` #4 merged to dev/main
(4265640) + docs + harness restarted · 563 tests pass remote · `[ ]` auto-repair-loop scope
decision (open, non-blocking) · `[~]` reindex latency + worktree/vite hygiene (open, non-blocking).

---PROMPT END---
