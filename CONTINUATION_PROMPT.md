# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-06-12 (EOD). Supersedes all prior hand-offs. Every fact below was
> verified against the live repo + the remote host at write time. **The headline of this
> session: the autonomous crew now RUNS ON A REMOTE LINUX HOST (192.168.12.180), the full
> C# ecommerce app + all retrieval infra were migrated there, and two real retrieval bugs
> were root-caused and fixed.**

---PROMPT START---

You are the **architect** of the agentic-skills project. Read `CLAUDE.md` and `THESIS.md`
first. Mission: a **fully autonomous AI crew** that adds complex features to real brownfield
repos with no human in the loop — grounded, self-correcting, honest, cumulative. **The thing
being built is the crew.** Operating doctrine unchanged (quality-over-speed, no-abort,
improve-the-crew-not-accommodate, 95%-rigor-before-act, no-scope-overclaim `[x]` live-proven
vs `[~]` unit-only). Honor the memory files in `.claude/memory/`.

## TL;DR of where things are

1. **The crew runs on a REMOTE host.** A full workstation migration moved the harness + all
   retrieval infra + the C# ecommerce brownfield target onto **`user@192.168.12.180`** (Ubuntu
   20.04, x86_64, 12-core, 62 GB RAM, CPU-ONLY no GPU). A complete crew sprint was delivered
   there end-to-end (PO→engineer→R19 gate→merge→sprint_complete). The Mac is now just the
   control terminal.
2. **Two retrieval bugs root-caused + fixed this session** (commits `95d0f81`, `a712162`):
   the Ollama string-input `/api/embed` hang, and the per-agent worktree re-index. The first
   is fully verified; the second is deployed + a verify run is mid-flight (see §Verify).
3. **The zero-defect-escape chain (R18→R19→R20+R17)** shipped earlier this session and is on
   `dev≡main`. See `arch_zero_escape_chain` memory + `PROPOSAL_ACCEPTANCE_REAL_TEST_MANDATE.md`.

## Git / branch state
- **`development` ≡ `main` @ `a712162`** (the only live branches; work on development → FF main).
  Recent: `a712162` worktree-reindex fix · `95d0f81` Ollama string-embed fix · `6e2c096`+`e7991ec`+`cb41c08` the R18/R19/R20 chain.
- **VERIFY ON RESUME:** `git -C ~/dev/ai-projects/agentic-skills status` clean? and
  `git rev-parse origin/main origin/development` — **push `a712162` to origin if behind**
  (last confirmed push was `6e2c096`; the two retrieval fixes may be local-only).

## THE REMOTE CREW HOST — full operating details (192.168.12.180)

**SSH (passwordless, key created this session):**
```
ssh -i ~/.ssh/id_ed25519_18012 -o IdentitiesOnly=yes user@192.168.12.180
```
(remote user is literally `user`; sudo requires a password we do NOT have — operator-only.)
Add a `~/.ssh/config` alias `host180` if convenient (HostName 192.168.12.180, User user,
IdentityFile ~/.ssh/id_ed25519_18012, IdentitiesOnly yes).

**What's installed/running on the remote (verified):**
- **Harness**: uvicorn on `127.0.0.1:8000`, **HEALTHY, pid 422039** (PID drifts on restart —
  re-check `lsof -tnP -iTCP:8000 -sTCP:LISTEN`). Launch cmd (must set PATH for claude + uv-py):
  ```
  cd ~/dev/ai-projects/agentic-skills/webapp/backend
  nohup env PATH="$HOME/.local/bin:$PATH" .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >> ~/harness.log 2>&1 & disown
  ```
- **Docker stack** (`docker ps`): `milvus-standalone` + `milvus-minio` + `milvus-etcd` (the
  vector store, compose at `~/agentic-infra/`, data bind-mounts at `~/agentic-infra/volumes/`),
  + `ecommerce-pg` (postgres:16, `:5433`, db `ecommerce_dev`, user/pass `ecommerce`/`ecommerce`).
- **Ollama**: systemd service (`/usr/local/bin/ollama serve`, owned by `ollama` user → restart
  needs sudo = operator), model **`bge-m3`** loaded. ⚠ Ollama version **0.24.0** (see bug §A).
- **graphify CLI: NOT installed** → `graph_*` retrieval tools cannot build/query (open item).
- **claude CLI**: `/home/user/.local/bin/claude` v2.1.175, **authenticated** (`~/.claude/.credentials.json`).
- **Python 3.12** via uv (`~/.local/bin`), **.venv rebuilt** (x86_64, 65 deps). **Node 18** present;
  spike-node bridge deps (`@zilliz/claude-context-core`) installed in `.spike-node/node_modules`.
- **.NET 8.0.301** (`/usr/bin/dotnet`) — system-installed; the ecommerce repo **builds 0-errors**.

**Repo + target paths on the remote:**
- Harness repo: `~/dev/ai-projects/agentic-skills` (rsync'd from the Mac, at `a712162`-ish — verify
  `git -C ~/dev/ai-projects/agentic-skills log --oneline -3` and re-rsync any newer local commits).
- Brownfield targets: `~/dev/ai-projects/brownfield-targets/{fullstack-ecommerce-app, beaverhabits}`,
  symlinked into `webapp/backend/repos/`. ecommerce on branch `integration`.
- `webapp/.env` on remote uses `localhost` for Ollama (:11434) + Milvus (:19530) — correct (both
  are local to the remote). `.env` is gitignored; it's already in place.

**To launch a brief on the remote** (curl the local harness, detached):
```
ssh ... user@192.168.12.180 'cat > ~/p.json <<JSON ... JSON; setsid nohup bash -c "curl -sN -X POST http://127.0.0.1:8000/api/projects/fullstack-ecommerce-app/run-brief -H Content-Type:application/json --data @$HOME/p.json > ~/run.log 2>&1" </dev/null & disown'
```
Monitor via `~/run.log` phase events. Migration plan doc: `MIGRATION_PLAN_infra_to_180.md`.

## RETRIEVAL — two bugs fixed this session (the big debugging arc)

### Bug A — Ollama string-input `/api/embed` hang  →  FIXED + VERIFIED (`95d0f81`)
- Ollama **0.24.0** `/api/embed` **HANGS forever on a bare-STRING `input`** (40s→http=000) but
  works with an **array** (`["..."]`, ~3.8s). The spike-node bridge's `_embedOne` (query embed
  for SEARCH) sent a string → every `semantic_search` hung → crew grounded blind. `embedBatch`
  (INDEX) sent an array → indexing worked. Each stuck string req pins an Ollama slot at 100% CPU
  and eventually wedges the whole instance (needs `sudo systemctl restart ollama`).
- **Fix**: `langgraph_engine/retrieval/semantic.py` `BRIDGE_SCRIPT` `_embedOne` now sends
  `input: [text]` + `AbortSignal.timeout` on both embed paths. **VERIFIED**: bridge `search`
  returns relevant C# hits in **~1.2s** (was infinite hang). Memory: `arch_ollama_embed_string_hang`.
- GOTCHA: `.spike-node/bridge.js` is materialized from `BRIDGE_SCRIPT` by `SemanticRegistry`
  (semantic.py) **only when a `semantic_search` runs** (not during indexing). If you edit the
  template, force-regen: `python -c "import importlib.util,pathlib; ...exec semantic.py...;
  bridge.write_text(m.BRIDGE_SCRIPT)"` (done on remote this session). retrieval_server.py loads
  `REPO_ROOT/langgraph_engine/retrieval/semantic.py` — that IS the source of truth for the webapp.

### Bug B — per-agent worktree re-index  →  FIXED + DEPLOYED, verify run mid-flight (`a712162`)
- Each agent runs in a fresh git worktree (`.agent-worktrees/<hash>`). `_retrieval_kwargs`
  (`webapp/backend/app/routers/projects.py`) passed `target_repo=wt.path` → the retrieval server
  keyed the code collection by the WORKTREE path → fresh EMPTY collection → claude-context-core
  RE-INDEXED the whole repo before that agent's first search (minutes on CPU-only → blew the 25s
  warmup + search timeouts → crew grounded blind even after Bug A was fixed).
- **Fix**: `target_repo = lessons_repo or wt.path` — point retrieval at the STABLE main checkout
  (already indexed at index_initial; `lessons_repo` is already passed as `repo_dir`). Worktree is
  byte-identical to main at spawn, so the main collection grounds correctly; the agent reads its
  own new files directly. Mirrors the ABL-0016 lessons stable-key fix. **Deployed to remote +
  harness restarted.**

### Verify run — IN FLIGHT (check first thing on resume)
- A brief (`ecommerce-retrieval-verify`, GET /api/v1/Categories/count) was launched on the remote
  to prove Bug B's fix. Log: `~/verify.log`. At write time it was **still in `index_initial`**
  (the one-time MAIN re-index, slow on CPU ~15-20 min) — NOT yet at the PO where the fix is tested.
- **THE PROOF to capture**: once past index_initial → check the newest
  `traces/fullstack-ecommerce-app/*-po-*/retrieval.jsonl` tool breakdown. **FIX WORKS if** it
  shows MULTIPLE `semantic_search` calls (with n_hits) — vs only `target_status` before — AND
  `retrieval_warmup.done` fired (not `.timeout`) AND no `bridge.js op=index` runs against a
  `.agent-worktrees/` path. If still indexing main, just wait (don't relaunch).

### SEPARATE inefficiency surfaced (follow-up, NOT today's fix)
- `index_initial` re-indexes the FULL main repo **every run** even when the collection already
  exists (`hybrid_code_chunks_<md5(repo)>`). On CPU-only that's ~15-20 min of dead time per run.
  Clean fix: skip/short-circuit index_initial when the collection is already populated (the
  bridge `has_index` op already exists for exactly this). High-leverage for remote usability.

## THE ZERO-DEFECT-ESCAPE CHAIN (shipped this session, on dev≡main)
Operator directive 2026-06-12 (BINDING): PO writes comprehensive acceptance criteria → engineer
covers every criterion with tests → acceptance live-verifies each → every failure dispatches a
fixer → 0% *detected* escape. Built as 4 gates on the **acceptance criterion** (`AC-<BL>-<n>`):
- **R18** (`doctrine_validator.validate_po` + `backlog.thin_criteria_report`): BL with <2 substantive
  criteria fails the PO gate → retry. **R19** (`regression_gate.run_bl_tests`): per-BL gate scans
  tests for every AC id → `coverage_gap` if any uncovered. **R20** (`_acceptance_flow._unverified_criteria`
  + `ac_coverage`): acceptance live-verifies each AC; unverified → non-clean + blocks `integrity_ok`.
  **R17 + always-dispatch**: observed-failure auto-dispatch independent of the calibration flag;
  `FOLLOWUP_COST_CAP` 1→25. All in `doctrine_spec.py` (I-2) + CLAUDE.md R-rule table.
- Honesty boundary: guarantees zero *detected* escape; residual = a behavior no criterion describes.
  Memory: `arch_zero_escape_chain`. Doc: `PROPOSAL_ACCEPTANCE_REAL_TEST_MANDATE.md`.
- **`[~]` not yet live-proven on a full real sprint** (the reviews 401 it was built for hasn't been
  re-run end-to-end with the chain catching+fixing it). That's a standing live-proof TODO.

## Path-keying note (migration)
Milvus collections + graphify caches are keyed by `hash(absolute_repo_path)`. The migrated
Mac-path collections are ORPHANED on the remote (different paths) → the remote re-indexes under
new-path hashes (e.g. `hybrid_code_chunks_92e66084` for the ecommerce remote path). The migrated
data + cumulative-learning stores (`lessons_*`, `patterns_*`, `lessons_global`) are present but
unused at the new paths. If reusing the migrated crew memory matters, re-key collections/caches to
the remote-path hashes (or mount targets at identical paths). Otherwise the remote rebuilds fresh.

## OPEN ITEMS / suggested next actions (priority order)
1. **Confirm the verify run** (Bug B fix) — capture the PO `retrieval.jsonl` `semantic_search`
   evidence. If it works → grounded retrieval is fully live on the remote.
2. **Push `a712162` to origin** if not already.
3. **Make `index_initial` skip when the collection is populated** (the big remote-speed win).
4. **Install `graphify` CLI** on the remote → enables `graph_*` retrieval.
5. **Live-prove the zero-escape chain** on a real sprint (re-run the reviews feature; the 401 is
   the canonical defect it must catch + auto-fix).
6. **Operator chores**: rotate the Docker Hub password that was exposed in the remote's
   `~/.docker/config.json` (cleared this session); optionally `sudo systemctl restart ollama` if
   embeds wedge again (Ollama 0.24.0 fragility).

## Honest verification ledger
- `[x]` remote migration (repo+build 0-err, Postgres, .NET8, Milvus 161 collections, graphify,
  Ollama) — verified. `[x]` full crew sprint delivered on remote (run-20260612T190835Z-22efad,
  BL-0001 merged_full). `[x]` Bug A retrieval hang fixed (bridge search 1.2s). `[~]` Bug B
  worktree-reindex fix deployed, verify run mid-flight (PO evidence pending). `[~]` zero-escape
  chain unit-proven (478 tests) not full-sprint live-proven. `[ ]` graphify graph_* on remote.

---PROMPT END---
