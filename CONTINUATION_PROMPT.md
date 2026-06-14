# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-06-14. Supersedes all prior hand-offs. **Headline: two BINDING
> WORKFLOW changes landed this session — (1) REMOTE-FIRST dev (all crew/harness code is
> edited + tested on the remote `192.168.12.180`, synced remote→GitHub→Mac), and (2) a
> 95%-verified-confidence directive over ALL statements. On capability: the live-acceptance
> loop is CONVERGED+PROVEN, a 2nd clean feature (inventory/stock) shipped end-to-end, and the
> operator-approved PARALLEL-WAVE-EXECUTION program has Phases 1–3 shipped (flag-OFF, not yet
> live-proven). A real data-loss concurrency bug in the findings ledger was found (via
> remote-first testing) and fixed.**

---PROMPT START---

You are the **architect** of agentic-skills. Read `CLAUDE.md` + `THESIS.md` first. Mission:
a fully autonomous AI crew that ships complex features into real brownfield repos with no
human — grounded, self-correcting, honest, cumulative. Honor `.claude/memory/`.

## TWO BINDING WORKFLOW DIRECTIVES (operator 2026-06-14) — read these first
1. **REMOTE-FIRST development.** ALL crew/harness code (`webapp/`, `langgraph_engine/`,
   `skills/`, `rubrics/`, tests) is **edited AND tested on the remote crew host
   `192.168.12.180`**, then synced **remote → GitHub → Mac** (the Mac is a read-only mirror;
   the old Mac→bundle→remote flow is RETIRED for code). See CLAUDE.md "Development workflow —
   REMOTE-FIRST" + `.claude/memory/feedback_remote_first_dev.md`. Your Edit/Write tools target
   the Mac FS, so remote edits go over SSH: Read the remote file (or the identical Mac mirror)
   → apply a uniqueness-checked python in-place replace ON the remote → run the remote test
   suite. Governance docs (CLAUDE.md, *.md, memory) MAY be Mac-authored but still flow through
   GitHub so all hosts converge.
2. **95% verified confidence before ANY claim.** Never state a claim/assumption/observation/
   proposal without having done the homework to a true 95% confidence, verified against a
   re-openable artifact (a command that ran, a file that exists, a test that passed, a log
   line). Below 95%: state the confidence + the resolving check. CLAUDE.md top of "quality
   over speed".

## VERIFIED CURRENT STATE (checked 2026-06-14)
- **Git: Mac ≡ remote ≡ origin (dev≡main) @ `31f9f0e`, all clean.** The remote CAN push to
  GitHub (deploy key wired — see below).
- **Remote harness**: uvicorn `127.0.0.1:8000`, **pid 2085993**, health ok (drifts on restart —
  re-check `lsof -tnP -iTCP:8000 -sTCP:LISTEN`). NO active run.
- **Services up**: Milvus stack (standalone/minio/etcd, :19530), Ollama (bge-m3, :11434),
  `ecommerce-pg` (postgres:16 :5433, db `ecommerce_dev`, user/pass `ecommerce`/`ecommerce`).
- **Target**: `fullstack-ecommerce-app` on branch `integration` @ `3028cce` (inventory feature
  delivered+accepted). Other target: `project-management-app`. Remote git is **2.25.1**.
- **Remote full suite: 533 passed, 0 failed** (run `cd ~/dev/ai-projects/agentic-skills/webapp/
  backend && .venv/bin/python -m pytest tests/ -p no:cacheprovider`; the bare `pytest` recurses
  into symlinked `repos/` targets and errors — always scope to `tests/`).

## REMOTE ACCESS
SSH: `ssh -i ~/.ssh/id_ed25519_18012 -o IdentitiesOnly=yes user@192.168.12.180` (user `user`;
sudo needs an operator password we don't have). Strip banner noise:
`grep -v "post-quantum\|store now\|may need to be upgraded\|openssh.com"`.
- **Remote→GitHub auth**: deploy key `~/.ssh/id_ed25519_ghdeploy` (repo `core.sshCommand` set,
  github.com in known_hosts). Operator added the pubkey to GitHub with write access → remote
  push works. Remote-first loop: edit on remote → `pytest tests/` on remote → commit on remote
  → `git push origin` on remote → Mac `git fetch && merge --ff-only origin/development`.
  **Commit messages on the remote: use `git commit -F <file>` (NO backticks in `-m "..."` — the
  remote shell command-substitutes them).**
- **Harness restart** (after deploying code; no active run): `cd ~/dev/ai-projects/agentic-skills/
  webapp/backend && nohup env PATH="$HOME/.local/bin:$PATH" .venv/bin/python -m uvicorn
  app.main:app --host 127.0.0.1 --port 8000 >> ~/harness.log 2>&1 & disown`
- Launch a sprint: `POST /api/projects/fullstack-ecommerce-app/run-brief` (payload =
  brief + flags). Boot recipe / seeded users / ports: see `arch_live_acceptance_loop` memory.

## WHAT SHIPPED THIS SESSION (all verified)
- **`[x]` Live-acceptance loop CONVERGED** — reviews `run-20260613T202407Z-013ac4`:
  `acceptance.loop.accepted`, integrity_ok=true, full-app boot 5096/5173, authed submit 201,
  evidence in-target. (See `arch_live_acceptance_loop`.)
- **`[x]` Inventory & stock-enforcement feature delivered+accepted** — `run-20260614T025948Z-
  0c2a26`, 4/4 merged_full, regression green, acceptance accepted, evidence in-target
  (`3028cce`). The crew solved an un-telegraphed concurrency invariant (atomic
  `ExecuteUpdateAsync WHERE Quantity>=qty`) unattended. 2nd clean live-acceptance delivery.
  (`arch_inventory_run_and_wave_proposal`.) Operator scope decision: a crew MAY surgically fix
  a genuine BLOCKING baseline defect (`feedback_baseline_auth_inscope`).
- **`[x]` PARALLEL-WAVE-EXECUTION program, Phases 1–3 shipped** (operator-approved;
  `PROPOSAL_PARALLEL_WAVE_EXECUTION.md`). All behind `wave_execution` flag, **DEFAULT OFF**:
  - **P1 (R21)**: PO emits per-BL `**Dependencies:**` DAG + `**Exposes:**`/`**Consumes:**`
    contracts; `validate_po` enforces (DAG well-formedness + contract coverage); fix-prompt in
    the PO retry loop. (`backlog.dependency_report`/`contract_report`/`topological_waves`,
    doctrine_spec R21, PO SKILL, CLAUDE.md table.)
  - **P2 (scheduler)**: `orchestrator._dep_waves` groups BLs into topological waves; emits
    `wave.start`/`wave.done`; concurrency=1 (degenerate, byte-identical per-BL semantics).
  - **P3 (reindex-at-barrier)**: per-BL reindexes guarded off in wave mode; ONE
    `reindex_after_wave.<n>` per barrier → 2/BL becomes 1/wave (inventory 8→2 reindexes).
  - **`[~]` NOT live-proven**: the flag has never run a real sprint. Phases 1–3 are
    unit-tested + OFF-path-regression-tested (533 passed) only.
- **`[x]` findings-ledger data-loss race FIXED** (`8e7d5ed`) — flock was on the inode-rotated
  data file → concurrent appends lost findings; now flock a stable sidecar `_lock_path()`. NOT
  a flake (memory corrected: `arch_findings_ledger_race`). Matters under wave parallelism.
- **`[x]` git-2.25 fixture portability FIXED** (`a46990e`) — `git init -b` → `init` +
  `symbolic-ref`; took the remote suite from 22-failed to green. First remote-first commit.

## SUGGESTED NEXT STEPS (operator-gated; propose before doing)
1. **LIVE-PROVE wave Phases 1–3** — the highest-value next move. Run a real brief with
   `wave_execution=True` (re-run the inventory brief, or a fresh feature) to exercise: the PO
   producing a valid R21 DAG/contracts at the gate, wave scheduling/events, and the
   reindex-at-barrier speedup — the honest `[x]` for all three. Watch: PO gate accepts the DAG;
   `orchestrator.wave.start/done`; `reindex_after_wave.*` (not per-BL); same clean acceptance.
2. **Wave Phase: concurrency>1** (true intra-wave parallelism — the async event-stream merge).
   The riskiest phase; its own careful implementation + live proof.
3. **Wave Phase 4**: conflict-resolver agent at the barrier + accept-on-scratch-assembled-branch.
4. **Reindex incremental / has_index short-circuit into `index_initial`** — independent
   remote-speed win (every run re-indexes ~15min even when the collection is populated).

## HONEST VERIFICATION LEDGER
`[x]` live-acceptance CONVERGED · `[x]` inventory delivered+accepted · `[x]` wave P1–P3
code-complete + 533 remote tests green (OFF path) · `[x]` findings-ledger race fixed
(5/5) · `[x]` git-2.25 fix (remote green) · `[x]` remote-first loop proven end-to-end ·
`[x]` 95% directive + remote-first in CLAUDE.md · `[~]` wave_execution=True NEVER run a
live sprint (the standing next milestone) · `[~]` concurrency>1 parallelism unbuilt.

---PROMPT END---
