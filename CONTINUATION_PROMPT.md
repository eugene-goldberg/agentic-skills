# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-06-15 (evening). Supersedes all prior hand-offs. **Headline: the
> indexing line is COMPLETE — reindex incremental is DEFAULT ON and the index_initial 900s
> baseline-cap is FIXED (marker-gated complete baseline + 3h op-aware timeout), all live-proven.
> (The Product-Q&A validation sprint was killed + cleaned at operator request; harness idle, target pristine.)
> The operator approved the NEXT architectural line: the Contract-First Decomposition + Stub
> Materialization Program (`PROPOSAL_CONTRACT_FIRST_DECOMPOSITION.md`), Phase 0 done, Phase 1
> pending operator go.**

---PROMPT START---

You are the **architect** of agentic-skills. Read `CLAUDE.md` + `THESIS.md` first. Mission: a fully
autonomous AI crew that ships complex features into real brownfield repos with no human — grounded,
self-correcting, honest, cumulative, **and (next line) parallel like a real team**. Honor `.claude/memory/`.

## BINDING WORKFLOW DIRECTIVES (operator 2026-06-14) — still in force
1. **REMOTE-FIRST.** ALL crew/harness code (`webapp/`, `langgraph_engine/`, `skills/`, `rubrics/`,
   tests) is edited AND tested on the remote `192.168.12.180`, then synced **remote → GitHub → Mac**
   (Mac = read-only mirror). Your Edit/Write target the Mac FS, so remote edits go over SSH (read →
   uniqueness-checked python in-place replace → remote `pytest`). See `.claude/memory/feedback_remote_first_dev.md`.
2. **95% verified confidence before ANY claim.** Verify against a re-openable artifact. Unit-green is
   NOT enough for index/retrieval changes — LIVE-prove against a real search (a reindex unit test
   passed but the first live-proof still caught a silent file-drop this session).
3. **SSH gotcha (bit me 3×):** never combine a `base64 -d > file` stdin-transfer with a backgrounded
   job in the SAME ssh call — the bg job races the stdin pipe and truncates the file (→ empty payload
   / 422 / empty script). ALWAYS transfer a payload/script in a SEPARATE ssh call, verify its byte
   count, THEN launch. Detach long work with `setsid bash -c "..." < /dev/null & disown`. `pkill -f X`
   self-matches the ssh shell (its argv contains X) — kill bridge/index procs by PID via
   `ps -eo pid,args | awk '/[b]ridge\\.js/{print $1}'` (the `[b]` trick avoids self-match).

## VERIFIED CURRENT STATE (checked 2026-06-15 ~18:30 UTC)
- **Git (agentic-skills), Mac ≡ remote ≡ origin/GitHub:** `development` = `main` = **`dc22ef2`** (clean).
  `wave-concurrency` retained at `4265640` (fully merged; historical).
- **Remote harness:** uvicorn `127.0.0.1:8000`, **pid 3197156** (DRIFTS on restart — re-check
  `lsof -tnP -iTCP:8000 -sTCP:LISTEN`), running code at `3197a83`. **NO active run — idle.**
- **Services:** Milvus (:19530), Ollama (bge-m3, :11434, 100% CPU — no GPU on host), `ecommerce-pg`
  (postgres:16 :5433). 572 tests pass on the remote venv (as of `17e7090`).
- **Target `fullstack-ecommerce-app`:** branch `integration`, head **`07ab2cd`** (PRISTINE — the Q&A sprint was killed + cleaned). Baseline index
  marker present (`~/.context/baseline_complete/hybrid_code_chunks_92e66084.json`, 409 files/2708
  chunks) so `index_initial` runs incremental/fast.

## Product-Q&A validation sprint — KILLED + CLEANED (operator 2026-06-15)
The full Q&A sprint (`run-20260615T175833Z-083f51`) was launched to validate the new indexing
in a real end-to-end sprint, then **killed at operator request** and fully cleaned up: harness
SIGTERM'd + restarted idle, agent/index/curl procs reaped, target reset to `07ab2cd`, agent
branches + worktrees + `.agent-worktrees` pruned, run state archived. **The new indexing was
already PROVEN live in it** — `index_initial` ran `cc_op=index_baseline` INCREMENTAL (marker
present) and finished in seconds, and the PO grounded fine (8 calls). So the indexing line is
DONE + live-validated. (The sprint also surfaced + we fixed the R21 `;`-split parser bug,
`17e7090`.) Nothing is in flight now.


## WHAT SHIPPED THIS SESSION (all verified, all on `dc22ef2`)
- **`[x]` Wave-concurrency follow-ups #1–4 MERGED** (earlier `4265640`): scorer mid-wave trunk-leak
  fix; conflicting-pair + I-5 `bl_outcomes` reconciliation; 3-wide/multi-wave scale; FF to dev/main.
- **`[x]` Reindex incremental SHIPPED + DEFAULT ON** (`be37669` build, `3ad9c9c` default-flip). Bridge
  `op=reindex` (incremental `reindexByChange`) + `op=index_baseline`; harness barriers embed only
  changed files. Live-proven: reindex 4.4s vs 900s full; wave .cs files indexed (no silent drop).
- **`[x]` index_initial 900s baseline-cap FIXED** (`14a1d1b`). Marker-gated: full embed ONCE per repo
  (snapshot-first + `INDEX_BASELINE_TIMEOUT_S` default 10800s/3h), writes
  `~/.context/baseline_complete/<collection>.json` only on `status:completed`; thereafter incremental.
  Live-proven on ecommerce: full embed completed 2478s/~41min (409 files), 2nd run 2s incremental,
  baseline searchable. See `.claude/memory/arch_reindex_incremental.md`.
- **`[x]` R21 contract-parser brittleness FIX** (`17e7090`). `backlog._contract_tokens` split on
  `;,\\n` even inside `()[]{}`, shattering contracts like `Question{id; text}` → false
  contract_errors → the Q&A sprint ABORTED once. Fix: nesting-aware split + normalize head at `{`/`[`.
  (The retry loop + this fix now clear the PO gate; the parser is still somewhat brittle vs the PO's
  compact markdown — backticks, inline `· **Status:**`, `/`+`+` joins — a NON-blocking hardening
  follow-up worth doing to cut PO retries.)
- **`[x]` Contract-First Decomposition + Stub Materialization Program — PROPOSAL authored**
  (`dc22ef2`, `PROPOSAL_CONTRACT_FIRST_DECOMPOSITION.md`). See next section.

## ★ NEXT ARCHITECTURAL LINE (operator-approved 2026-06-15) — Contract-First Decomposition
`PROPOSAL_CONTRACT_FIRST_DECOMPOSITION.md` (repo root). **Why:** we built + live-proved the parallel
executor (`wave_execution` + `wave_concurrency`) but it's STARVED — the PO decomposes by horizontal
layers → serial DAGs → width-1 waves (the Q&A 4-BL chain is the evidence). A pro team gets parallelism
from **contract-first + mocks**: agree interfaces up front, build vertical slices CONCURRENTLY against
the contract + mocks, integrate once. The unit of dependency becomes the **agreed interface**, not the
upstream's **merged code** — which collapses the serial chain into a parallel fan-out. Our machinery
already FITS: mock-only per-BL gates + ONE real no-mock acceptance integration checkpoint (R17/R20) =
exactly the safety net that makes mocking safe (acceptance catches mock drift). **Missing:** (1) a
contract-materialization step (turn R21 `Exposes`/`Consumes` into compilable stubs committed first),
(2) a contract-first PO decomposition doctrine (vertical mockable slices, not layers). Phased plan in
the doc: **Phase 0 done (the doc); Phase 1 = contract-as-artifact → compilable C# stubs; Phase 2 =
contract-first PO doctrine gated on a DAG-fan-out metric; Phase 3 = mock execution + barrier binding;
Phase 4 = live proof.** Additive + `contract_first` flag default OFF. **Phase 1 PENDING OPERATOR GO.**

## OPEN FOLLOW-UPS (non-blocking)
1. R21 parser hardening vs the PO's compact markdown (backticks / inline `**Field:**` terminators /
   `·`,`/`,`+` joins) — cuts PO doctrine retries. Folds naturally into Contract-First Phase 1 (R21
   becomes the stub source, so it must parse robustly).
2. Concurrency §3.3/§3.4 (Grok `Concurrency_Assessment_01.md`): dedicated `wave_concurrency=1`
   byte-identical regression test; disk-preflight scaling by k + `wave.concurrency_degraded`;
   `in_flight_bls` checkpoint; A55 diff-scope acceptance-lint.
3. Hygiene: prune leftover `agent/*` on the target after the Q&A sprint terminates.

## HONEST LEDGER
`[x]` reindex incremental DEFAULT ON (live-proven) · `[x]` baseline-cap fixed (marker+3h, live-proven
41min-once→2s) · `[x]` R21 `;`-split fix · `[x]` Contract-First PROPOSAL committed (Phase 0) · `[x]` indexing line proven live in the Q&A sprint (then killed + cleaned per operator) · `[ ]` Contract-First Phase 1 (pending
operator go) · `[ ]` R21 markdown hardening (non-blocking).

---PROMPT END---
