# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-06-15. Supersedes all prior hand-offs. **Headline: wave
> concurrency (`wave_concurrency>1`, Strategy A) is BUILT, fully LIVE-PROVEN
> (happy-path + conflicting-pair + 3-wide/multi-wave scale), and MERGED to
> `development`/`main`. The reindex-incremental short-circuit (flag-gated) is also
> SHIPPED + live-proven. All five of the prior session's follow-ups are closed; two
> small, non-blocking follow-ups remain.**

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
2. **95% verified confidence before ANY claim.** Verify against a re-openable artifact. Below
   95%: state the confidence + the resolving check. (This session: unit+isolation tests PASSED
   but the first reindex live-proof still FAILED a correctness check — only the live search of
   the real index caught a silent file-drop. Live-prove index/retrieval changes, don't trust
   unit green.)

## VERIFIED CURRENT STATE (checked 2026-06-15)
- **Git (agentic-skills), all synced Mac ≡ remote ≡ origin/GitHub:**
  `development` = `main` = **`3ad9c9c`** (clean). `wave-concurrency` branch retained at
  `4265640` (its work is folded into dev/main).
- **Remote harness**: uvicorn `127.0.0.1:8000`, **pid 3053123** (drifts on restart — re-check
  `lsof -tnP -iTCP:8000 -sTCP:LISTEN`), on `development`. NO active run. **568 tests pass.**
- **Services up**: Milvus (:19530), Ollama (bge-m3, :11434), `ecommerce-pg` (postgres:16 :5433).
- **Target**: `fullstack-ecommerce-app` on `integration` @ **`07ab2cd`**, clean, throwaway test
  branches pruned. SEPARATE git repo (its own remote; NOT on the agentic-skills GitHub).
- **Bridge note**: `.spike-node/bridge.js` is GITIGNORED + regenerated from
  `langgraph_engine/retrieval/semantic.py`'s `BRIDGE_SCRIPT`. The remote copy is current
  (carries the new index_baseline/reindex ops). A fresh remote clone must regenerate it
  (write `semantic.BRIDGE_SCRIPT` to `.spike-node/bridge.js`) before the webapp indexes.

## REMOTE ACCESS
SSH: `ssh -i ~/.ssh/id_ed25519_18012 -o IdentitiesOnly=yes user@192.168.12.180`. Strip banner:
`| grep -v "post-quantum\|store now\|may need to be upgraded\|openssh.com"`. Remote pushes to
GitHub via deploy key. Loop: edit on remote → `pytest tests/` on remote → commit on remote
(`git commit -F <file>`) → `git push origin` → Mac `git fetch && reset --hard origin/<branch>`.
Harness restart (no active run, needed only after PYTHON edits — bridge.js is invoked fresh per
call so JS edits are live immediately): `cd ~/dev/ai-projects/agentic-skills/webapp/backend &&
nohup env PATH="$HOME/.local/bin:$PATH" .venv/bin/python -m uvicorn app.main:app --host
127.0.0.1 --port 8000 >> ~/harness.log 2>&1 & disown`. Controlled skip_po test: commit a
`_brownfield/features/<slug>/BACKLOG.md` (+ brief.md, _codebase_context/, per-BL dirs) on the
target `integration`, then POST `/api/projects/<repo>/run-brief` with `{skip_po:true,
feature_name:"<slug>", wave_execution:true, wave_concurrency:N, reindex_incremental:<bool>,
run_acceptance:false, run_doctrine_meta:false, inject_lessons:false}`. SSE detach: `setsid bash
-c "curl -sN ... > ~/x.log 2>&1" < /dev/null &` (transfer the payload in a SEPARATE ssh call
first — a backgrounded curl sharing the SSH stdin pipe races it → empty body → 422).

## WHAT SHIPPED THIS SESSION (all verified, all on `be37669`)
- **`[x]` Wave concurrency follow-ups #1–#4 (merged @ `4265640`)**: scorer mid-wave trunk-leak
  fix (`6c5f45e`, resolves the BL-0001 noop nuance → kind=merged); conflicting-pair live-proof
  + I-5 `bl_outcomes` reconciliation (`1c7c02f`, → `escalated_assembly_conflict`); 3-wide +
  multi-wave scale (run-…041351Z-fc2e21, 5/5 merged, no resource blowup); FF merge + docs.
- **`[x]` Reindex incremental short-circuit (`be37669`; flag `reindex_incremental` **DEFAULT
  ON** for every crew run, operator 2026-06-15, `3ad9c9c`; set False = full-index rollback)**: bridge op=index_baseline (snapshot-FIRST, then full embed) + op=reindex (incremental
  reindexByChange). Root cause: op=index always re-embedded ALL files; reindexByChange is the
  incremental path the harness never used. LIVE-PROVEN run-20260615T140733Z-df8c69: reindex
  4.4s vs the 900s-capped full embed (~200x), and a real search returns the wave-added
  DiagAlpha/DiagBetaController.cs as INDEXED code paths (no silent drop). First proof
  (e5aa54) caught a silent drop — the post-embed snapshot step was killed by the 900s timeout;
  fixed by snapshot-FIRST ordering. See `.claude/memory/arch_reindex_incremental.md`.

## OPEN FOLLOW-UPS (none block shipped work)
1. **`index_initial` 900s baseline-cap (PRE-EXISTING, surfaced this session).** A full
   `indexCodebase` of `fullstack-ecommerce-app` (~280 files) EXCEEDS the 900s Python indexer
   timeout on CPU bge-m3 and is truncated → the baseline index is PARTIAL (some baseline files
   unembedded) on EVERY run, flag on or off. Orthogonal to the incremental reindex (which
   reliably indexes the WAVE delta). Fix options: raise/stream the index_initial budget, batch
   embeds, or GPU embeddings. Real grounding-quality risk worth addressing.
2. **Lower-priority concurrency hardening** (Grok `Concurrency_Assessment_01.md` §3.3/§3.4):
   dedicated `wave_concurrency=1` byte-identical regression test; disk-preflight scaling by k +
   `wave.concurrency_degraded` event; `in_flight_bls` checkpoint + sidecar lock for mid-wave
   crash resume; A55-class diff-scope acceptance-lint crew fix.

## DECIDED THIS SESSION (do not re-litigate)
- **Assembly-conflict auto-repair loop → DOCUMENTED & DEFERRED** (operator 2026-06-15).
  Surface + no-abort escalation (`escalated_assembly_<kind>`) is the accepted FLOOR and the
  correct TERMINAL behavior for a true semantic conflict; R21's contract gate keeps wave-mates
  file-disjoint so same-wave conflicts are rare. An auto-rebase-retry for spurious (adjacent-
  hunk) conflicts is an enhancement, not a prerequisite. Revisit only if conflicts recur.

## HONEST VERIFICATION LEDGER
`[x]` wave concurrency #1 scorer fix · `[x]` #2 conflict path + I-5 reconcile · `[x]` #3 scale
(3-wide+multi-wave, no blowup) · `[x]` #4 merged dev/main · `[x]` #5 reindex incremental DEFAULT ON
(df8c69: 4.4s vs 900s + wave .cs files indexed, no silent drop) · 568 tests pass remote ·
`[ ]` index_initial 900s baseline-cap (pre-existing, non-blocking) · `[ ]` §3.3/§3.4 hardening.

---PROMPT END---
