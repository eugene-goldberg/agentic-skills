# HANDOFF — agentic-skills (machine migration)

> Written 2026-06-17 for moving the architect's working machine. Read this top-to-bottom
> before doing anything. It is self-contained: mission, architecture, how the crew runs,
> exactly where we are, what is in flight, and what to do next. After reading this, also
> read `CLAUDE.md`, `THESIS.md`, and `ARCHITECTURE_INVARIANTS.md` (the standing
> governance), and `.claude/memory/MEMORY.md` (cross-session memory index).

---

## 0. TL;DR — what you are inheriting

**agentic-skills** is a fully-autonomous AI software-development *crew*: point it at a real
brownfield git repo, hand it a product requirement, walk away, come back to clean,
regression-tested, grounded commits that ship the feature — plus an honest report of what
was deferred or is risky. Mission detail: `THESIS.md` + `CLAUDE.md` "Mission".

You are the **architect** of this project (see `CLAUDE.md` "Your role"). You own delivery,
the structural lens (`ARCHITECTURE_INVARIANTS.md`), the governance docs, and calibrated,
operator-gated proposals (risk + named test + rollback).

**The crew does NOT run on this laptop.** It runs on a **remote Linux host
(`192.168.12.180`)**. Your laptop is a thin client: you SSH in to edit/test crew code and
to launch/monitor runs, and you keep a read-only git mirror locally. **The single most
important migration step is making the new machine able to SSH to that remote** (Section 2).

---

## 1. The two-machine (actually three-place) model

| Place | What it is | Role |
|---|---|---|
| **Your laptop** (was a Mac; now the new machine) | The architect's client + read-only git mirror | You run Claude Code here; it SSHes to the remote. Local repo is `git reset --hard origin/<branch>` — a mirror, never the source of truth for crew code. |
| **Remote host `192.168.12.180`** (`user@`, hostname `B460MDS3HACY1`, Ubuntu 22.04, x86_64, git 2.x) | **The crew host** — runs the FastAPI harness, the agent subprocesses, Ollama, Milvus, Postgres, Docker | **Ground truth for all crew/harness code.** All edits + tests + runs happen here. |
| **GitHub** `git@github.com:eugene-goldberg/agentic-skills.git` | Shared history | Sync hub. Flow is **remote → GitHub → laptop** (never laptop → remote for crew code). |

**BINDING workflow rule (operator directive 2026-06-14, still in force):** all crew/harness
code (`webapp/`, `langgraph_engine/`, `skills/`, `rubrics/`, tests) is **edited AND tested
on the remote**, then `git push` from the remote to GitHub, then the laptop
`git fetch && git reset --hard origin/development`. The laptop never pushes crew code.
Governance docs (`*.md`, `.claude/memory/`) MAY be drafted on the laptop but flow through
the same remote→GitHub→laptop sync. See `.claude/memory/feedback_remote_first_dev.md`.

---

## 2. ⭐ MIGRATION CHECKLIST (do this first on the new machine)

These are the things that do **not** come from `git clone` and that the **operator must set
up manually** — secrets and host access cannot be committed.

1. **Clone the repo from GitHub:**
   `git clone git@github.com:eugene-goldberg/agentic-skills.git` (needs your GitHub SSH auth).
   Default working branch is `development`. Check out `development`.

2. **Copy the SSH private key that reaches the remote crew host.** On the old machine it is
   `~/.ssh/id_ed25519_18012`. **Securely copy it to the new machine's `~/.ssh/` (chmod 600).**
   Verify: `ssh -i ~/.ssh/id_ed25519_18012 user@192.168.12.180 hostname` → should print
   `B460MDS3HACY1`. The new machine must be on a network that can route to `192.168.12.180`
   (it is a LAN/VPN host — if the new machine is remote, you need the same VPN/LAN).
   - Convenience: add to `~/.ssh/config`:
     ```
     Host crew
       HostName 192.168.12.180
       User user
       IdentityFile ~/.ssh/id_ed25519_18012
     ```
     then `ssh crew` works. (The benign post-quantum-KEX warning on connect is harmless;
     filter it out of command output with `grep -v post-quantum`.)

3. **You do NOT need to set up Ollama/Milvus/Postgres/dotnet/node locally** — they all run
   on the remote. The laptop only needs: `git`, an SSH client, and Claude Code.

4. **Re-point the memory symlink if you use Claude Code auto-memory locally:** run
   `scripts/setup_memory_symlink.sh` (idempotent) so `.claude/memory/` is found at the
   canonical path. (Memory files are committed in the repo at `.claude/memory/`.)

5. **The remote is already fully provisioned** — you should not need to reinstall anything
   there. If the remote ever reboots, see Section 6 "Bringing the remote back up".

6. **GitHub deploy key for remote pushes is already installed on the remote**
   (`~/.ssh/id_ed25519_ghdeploy`, repo-local `core.sshCommand` points at it; its public half
   is in the GitHub repo Deploy Keys with WRITE). So the remote can `git push origin`
   directly — nothing to do here unless that key is rotated.

---

## 3. Repository layout & governance docs

Two top-level subprojects:
- **`webapp/`** — the live system. FastAPI backend (`webapp/backend/`) that invokes the local
  `claude` CLI as agent subprocesses, + a React UI. **This is where the crew/orchestrator
  lives.** Read `webapp/PROJECT_STATE.md` for the deep reference. The orchestrator is
  `webapp/backend/app/services/orchestrator.py` (large; the heart of the crew). Tests:
  `webapp/backend/tests/` (run with the remote venv — Section 5).
- **`langgraph_engine/`** — the original LangGraph A/B harness (historical/reference).

**Read these in order on any non-trivial session** (full list in `CLAUDE.md` "Governance documents"):
1. `CLAUDE.md` — mission + your role + the map (READ FIRST, every session).
2. `THESIS.md` — the north star + definition of done.
3. `ARCHITECTURE_INVARIANTS.md` — the 7 structural rules (I-1..I-7); the audit lens.
4. `DESIGN_SHORTCOMINGS.md` — the audit ledger (anomalies A1..A6x, classified).
5. `WORKFLOW.md`, `CONTROL_FLOW.md`, `PIPELINE.md` — gates/guards/retries/events.
6. `DOCTRINE.md` + the R-rules table in `CLAUDE.md` — the doctrine the crew enforces
   (R5..R22), mirrored in code by `doctrine_spec.py` (a CI test fails on drift).
7. `.claude/memory/MEMORY.md` — the cross-session memory index; each `arch_*.md` /
   `feedback_*.md` is one durable fact. **Skim these — they encode hard-won lessons.**
8. `CONTINUATION_PROMPT.md` — the previous session-to-session handoff (now superseded by
   the "current state" below for the migration, but still useful background).

---

## 4. Operating principles (binding — these govern how you work)

- **Quality over speed / 95% rule:** make NO claim, fix, or "it works" below 95% verified
  confidence, backed by a re-openable artifact (a command that ran, a file that exists, a
  test that passed, a log line). Below 95%, say so and run the check. (`CLAUDE.md` top.)
- **No-abort / persistence:** aborting a sprint is a FAILURE. Every agent investigates →
  fixes → re-tests to resolution; the only non-success is an honest `escalated` with a
  dossier, never a silent give-up. (`feedback_no_abort_persistence.md`.)
- **Improve the crew, don't accommodate one target:** every move is "what does the crew
  gain?" Don't patch one target's symptom. (`feedback_improve_crew_not_accommodate.md`.)
- **Honesty / no scope-overclaim:** `[x]` = live-proven on a traced path; `[~]` =
  unit-tested only; a mocked test is not live behavior. (`feedback_no_scope_overclaim.md`.)
- **Operator-gated authority:** you propose; the operator approves. Never commit/push,
  force-push, or change doctrine without the operator's word. (Commits this session were all
  explicitly authorized.)

### SSH gotchas (each one bit me this session — internalize them)
- **Heredocs/payloads with apostrophes, braces, or unicode break a single-quoted
  `ssh '...'`.** Reliable pattern: write the file LOCALLY, `base64 | ssh 'base64 -d > f'`,
  verify byte count, then run/apply it. (Used for every remote code edit + commit message.)
- **Editing remote crew code:** your Edit/Write tools target the LOCAL fs. To edit on the
  remote, write a small Python patch script locally that does
  `assert s.count(OLD)==1; s.replace(OLD,NEW)` (mirrors the Edit tool's uniqueness safety),
  base64 it over, run it with the remote python. AST-check + run tests after.
- **Restart the harness with a LOGIN shell** so `claude`/`dotnet`/`node` resolve on PATH:
  `setsid bash -lc ".venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > ~/harness.log 2>&1" < /dev/null & disown`.
  A non-login `bash -c` drops `~/.local/bin` → `claude` FileNotFoundError → run aborts.
  **uvicorn has NO hot-reload — after editing crew code you MUST restart the harness** to
  load it. Verify the new code is live by `grep`-ing the source, not by sha.
- **Long SSH loops get auto-backgrounded** by the tool; launch monitors with
  `run_in_background` and read the output file. Commit/launch one-liners that background:
  read the task output file to get the result.
- **Commit messages:** write to a local file, base64 to remote, `git commit -F ~/msg.txt`
  (NOT inline `-m` with special chars).

---

## 5. CURRENT STATE (verified 2026-06-17 ~12:10 UTC)

### Git
- **GitHub origin:** `git@github.com:eugene-goldberg/agentic-skills.git`
- **`development` = `main` = `origin` = laptop = `164817a`** (clean; `main` FF'd to
  `development` at the end of this session).
- Live branches are ONLY `development` (working tip) and `main` (stable). Everything else is
  historical. Work lands on `development`, FF into `main` once verified.

### Remote crew host `192.168.12.180`
- Harness (FastAPI/uvicorn) on `127.0.0.1:8000` — `openapi.json` returns 200. **PID drifts on
  every restart — re-check with `lsof -tnP -iTCP:8000 -sTCP:LISTEN`.** Code at `164817a`.
- Services (all UP): **Ollama** `:11434` (bge-m3 embeddings), **Milvus** `:19530` (vector
  store), **ecommerce-pg** `:5433` (the target's Postgres). Docker containers:
  `milvus-standalone`, `milvus-minio`, `milvus-etcd`, `ecommerce-pg` (plus unrelated `sofi_*`).
  Note: host `lsof` won't show docker-proxy ports as LISTEN; use `/dev/tcp` probes or `docker ps`.
- Embeddings: **local Ollama `bge-m3` (1024-dim)**, configured in `webapp/.env`
  (`EMBEDDING_PROVIDER=Ollama`, `OLLAMA_HOST=http://127.0.0.1:11434`). NOT Azure.

### The brownfield target under test: `fullstack-ecommerce-app`
- Real repo at `~/dev/ai-projects/brownfield-targets/fullstack-ecommerce-app` on the remote,
  symlinked into the webapp at `webapp/backend/repos/fullstack-ecommerce-app`.
- **C#/.NET 8 backend** (`backend/Ecommerce.sln`, EF Core, Postgres) + **React+Vite+TS
  frontend** (`frontend/`, vitest). MIT. The first non-Python target; substrate for the
  cross-language work.
- `.agentic-skills.json`: `agent_branch=integration`, `main_ref=main`,
  `test_cmd=["dotnet","test","backend/Ecommerce.sln","--nologo"]`,
  **`frontend_test_cmd=["npm","run","test","--"]`** (added this session — Fix A),
  `app_boot` v2 (backend `:5096` + frontend `:5173`).
- **Target branch state:** `integration` was just given an **onboarding commit
  (`d51e5c9`)** that commits the frontend **vitest test infrastructure**
  (`frontend/vitest.config.ts`, `frontend/tests/setup.ts`, `package.json` test script +
  testing-library/vitest/happy-dom devDeps) + `frontend_test_cmd` to the baseline. `main` of
  the target is the pristine baseline; `integration` forks from it and is the agent
  fork-point + auto-merge sink.

---

## 6. How to operate the crew (the actual mechanics)

### Launch a sprint (brief → merged feature), via the remote harness
`POST http://127.0.0.1:8000/api/projects/<repo>/run-brief` with a JSON body (SSE-streamed).
Reliable launch (detached, logs to a file you then tail/grep):
```
# payload at ~/diag_payload.json on the remote (write it via base64 from a local file)
setsid bash -c "curl -sN -X POST -H 'Content-Type: application/json' \
  --data @/home/user/diag_payload.json \
  http://127.0.0.1:8000/api/projects/fullstack-ecommerce-app/run-brief \
  > /home/user/diag_runN.log 2>&1" < /dev/null & disown
```
Key payload fields (see `RunBriefRequest` in `webapp/backend/app/routers/projects.py`):
`brief` (required), `max_bls`, `wave_execution` (bool), `wave_concurrency` (int ≥1),
`contract_first` (bool, DEFAULT ON but forced OFF on non-.NET targets),
`run_acceptance` (bool), `run_doctrine_meta` (bool), `timeout_per_role`.
**The frontend-concurrency diagnostic payload** used all session (3 independent frontend
BLs, `wave_execution=true`, `wave_concurrency=3`, `contract_first=false`,
`run_acceptance=false`) is on the remote at `~/diag_payload.json`.

### Monitor a run
Events are SSE `data: {…}` lines in the log. The orchestrator milestones look like
`"phase": "orchestrator.<name>"` (e.g. `backlog_parsed`, `wave.start`, `bl.assembled`,
`bl.done`, `coverage_check`, `sprint_complete`, `closure_check.done`). Terminal =
`closure_check.done` (or `escalated`/`aborted`). Pattern used all session: a
`run_in_background` SSH loop that `sleep 30; grep -q` for the terminal marker, then prints a
distilled summary (waves, `bl.assembled`, final `bl_outcomes`, `merged_total`). Parse JSON
robustly (events are SSE-framed; nested braces break naive regex — grep specific fields or
use a small python `json.JSONDecoder().raw_decode` scan from each `data: {`).

### Reset the target to pristine between runs
```
cd ~/dev/ai-projects/brownfield-targets/fullstack-ecommerce-app
git worktree prune; (remove stray worktrees under ../.agent-worktrees, ../.gate-worktrees)
git checkout integration; git reset --hard <baseline>   # baseline = d51e5c9 (onboarded) NOT main
git branch -D <all agent/* and work/* branches>; git clean -fdq
```
**IMPORTANT:** reset to the **onboarded baseline `d51e5c9`**, NOT `main` — resetting to `main`
+ `git clean -fd` would wipe the committed vitest infra and re-trigger the infra-conflict
class. (This exact mistake cost a run this session.) Also: `.agentic-skills.json` is TRACKED,
so any harness-side edit to it must be COMMITTED (an uncommitted tracked change makes the
target checkout dirty → the assembly merge-guard refuses to merge → spurious
`escalated_assembly` errors).

### Bringing the remote back up (if it rebooted)
- Start Docker stacks (Milvus + the target Postgres): they are docker containers
  (`milvus-standalone`, `milvus-etcd`, `milvus-minio`, `ecommerce-pg`) — `docker start` them
  or use their compose. Ollama: `systemctl --user`/`ollama serve` (bge-m3 model pulled).
- Restart the harness with the LOGIN-shell incantation in Section 4.
- Sanity: `curl -s 127.0.0.1:8000/openapi.json` = 200; `curl 127.0.0.1:11434/api/tags`;
  `/dev/tcp` probes for 19530 + 5433. Run the test suite (below) to confirm the venv is intact.

### Run the test suite (remote)
```
cd ~/dev/ai-projects/agentic-skills/webapp/backend
.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
As of `164817a`: **635 passed.**

---

## 7. WHAT THIS SESSION DID — the frontend-concurrency line (READ THIS)

**Goal the operator set:** for a set of FRONTEND/React BLs in one sprint, run them
CONCURRENTLY (wave-level parallelism across whole BLs — NOT splitting one BL). This is
distinct from the (already-complete) Contract-First program, which is C#-backend-DI-specific.

A diagnostic sprint (3 independent frontend BLs, `wave_concurrency=3`, `contract_first=false`)
exposed a chain of issues. Fixes, in order, all **remote-first + live-proven**:

### Fix B — honest assembly eligibility — `e4f9e06` (committed, pushed, PROVEN)
**Bug (critical, was a silent false-success):** in concurrent wave mode a BL was only
assembly-eligible if `qa_merged` (QA added a reinforcement commit). A frontend BL's QA adds
nothing (engineer already wrote the tests → `new_commits==0` → `merged=false`), so the
engineer-green work was stranded on its work_branch yet recorded `merged_no_qa` and counted
in `merged_total` — `sprint_complete` on an **empty trunk**. Serial mode keeps such code on
the trunk; concurrent stranded it.
**Fix:** `orchestrator._concurrent_assembly_decision()` (pure, unit-tested). Eligibility =
engineer-green + QA-doctrine-OK (NOT `qa_merged`), matching serial. Honesty invariant: a
`merged_*` label is recorded IFF the BL assembles; a non-assembling BL escalates
(`qa_escalated`) and is excluded from `merged_total`. **Live-proven** run
`run-20260617T013450Z-6371bc` (2 BLs assembled to trunk, 1 honestly escalated on a real
conflict, `merged_total=2` truthful).

### G2 — concurrent-wave PO file-disjoint doctrine — part of `164817a` (PROVEN)
**Bug:** the "keep slices file-disjoint / no shared composition root" PO doctrine was gated
to `contract_first` only. A non-contract_first frontend wave got none of it, so the PO put
two BLs both into `Home.tsx` → assembly conflict.
**Fix:** `prompts_brownfield.po_wave_disjoint_instruction()` — appended to the PO prompt when
`wave_concurrency>1` and NOT contract_first: keep same-wave BLs file-disjoint; if two BLs
must edit the same file, declare a `Dependency` so they serialize into separate waves (the
non-C# analog of contract_first's rule — there is no binder, so serialization is the clean
escape). Threaded `build_po → build_po_prompt_brownfield`; `_po_flow` passes
`wave_concurrent`. **Live-proven** run `run-20260617T023137Z-68235b` — the PO declared
`BL-0003 deps BL-0002`, waves `[[BL-0001,BL-0002],[BL-0003]]`. (NOTE: doctrine is
PROBABILISTIC — a later run did NOT serialize. See residual below.)

### Fix A — frontend-aware per-BL gate — part of `164817a` (PROVEN)
**Bug (false green):** the per-BL gate ran the configured backend `dotnet test` even for a
frontend BL whose own tests are React/vitest — so the frontend tests never ran but the gate
went green on the irrelevant backend suite. Worse, engineers were even WRITING C# tests for
frontend BLs.
**Fix:** (A1) `regression_gate.run_bl_tests` — when the BL's changed test files are frontend
(`*.test.tsx/.ts(x)/.js(x)`) and the target sets `frontend_test_cmd`, run THAT runner (vitest)
in the frontend dir (`app_boot.frontend.dir`), symlinking the target's `node_modules` into
the detached gate worktree. Gated on the new `repo_config.frontend_test_cmd` field → existing
targets byte-identical. (A2) engineer doctrine ("Test at the RIGHT layer for THIS BL"): a
frontend BL writes FRONTEND tests (vitest under `frontend/tests/`, grounded in the frontend
test config), not backend tests. (A3) layer-aware `no_tests` fix message.
**Live-proven** run `run-20260617T031851Z-b9bd46` — engineers wrote `frontend/tests/*.test.tsx`
and the gate ran real vitest (happy-dom, React component tests passing).

### Onboarding (target prep, not framework) — target commit `d51e5c9`
Run 4 surfaced that the target's **vitest infra was not committed to its baseline**, so every
frontend engineer recreated `vitest.config.ts`/`tests/setup.ts`/`package.json` test deps
concurrently → they collided. Fix = commit the vitest infra to the target `integration`
baseline ONCE (Onboarder-class target prep). Done as `d51e5c9`.

### Run 5 — CLEAN 3/3 concurrent frontend delivery (the capstone, PROVEN)
Re-run on the onboarded baseline (`run-20260617T120649Z-436f92`): all 3 frontend BLs ran
CONCURRENTLY in one wave, the gate ran real **vitest** (happy-dom, React component tests
passing), and **all 3 assembled `merged_full` onto the trunk with ZERO conflicts**
(`merged_total=3`, `ui_bls=[all 3]`, `sprint_complete`, `violation_count=0`). Verified on the
target trunk: `BackToTop.tsx`, `Newsletter.tsx`, `RecentlyViewed.tsx` + their
`frontend/tests/*.test.tsx` all present on `integration`. This is the end-to-end proof that
the framework fixes (B, G2, Fix A) + onboarding produce clean N-of-N concurrent frontend
delivery — the operator's original goal for this line.

### Commits summary
- agentic-skills: `e4f9e06` (Fix B), `164817a` (G2 + Fix A) on `development`/`origin`. 635 tests green.
- target ecommerce repo: `d51e5c9` on `integration` (vitest onboarding; the reset baseline).

---

## 8. IN FLIGHT — status

1. **Run 5 — confirmation run `run-20260617T120649Z-436f92`** — ✅ **DONE, CLEAN 3/3**
   (see Section 7 "Run 5"). Nothing pending; the target trunk `integration` now carries all
   three demo components + their vitest tests. (If you want a pristine target for the next
   experiment, reset to the onboarded baseline `d51e5c9` per Section 6 — NOT `main`.)
2. **FF `main` to `164817a`** — ✅ **DONE** (operator-approved; executed at the end of this
   session). `main == development == 164817a` on the remote, GitHub, and laptop.
3. **This handoff doc** committed to the repo so the new machine gets it via clone.

---

## 9. OPEN WORK / ROADMAP (after the in-flight items)

- **Deterministic clean N/N concurrent frontend delivery (the residual).** G2 doctrine
  reduces but does not eliminate same-file collisions because (a) the PO serializes only
  *probabilistically*, and (b) two BLs mounting into the same page (`Home.tsx`) still need
  serialization or composition. Fix B keeps this HONEST (ship what assembles, escalate the
  rest, never false-success), but guaranteed N/N needs one of:
  - **a deterministic React "binder"** — the frontend analog of the C# `contract_bind`:
    regenerate shared wiring (a page's mount list / a barrel `index.ts`) from disjoint
    per-BL artifacts so concurrent BLs never co-edit the shared parent. This is the heavier,
    "generalize the binder to React" build the operator originally asked about. The C#
    version (`contract_bind.py` + `orchestrator._contract_bind` + the materializer/engineer
    `@contract-module`/`@contract-aggregator` conventions) is the template.
  - or stronger PO/engineer ENFORCEMENT (a gate that rejects a same-wave shared-file edit and
    forces a Dependency), rather than advisory doctrine.
- **Generalize the contract materializer/binder beyond C#/dotnet** (the broader cross-language
  item from the prior Contract-First program; today contract_first is .NET-gated via
  `orchestrator._is_dotnet_target`).
- **2nd-target / harder-feature calibration** of all of the above.
- Lower priority: `wave_concurrency=1` byte-identical regression test; R21 PO-markdown parser
  hardening.

---

## 10. Quick reference — key files

| Path | What |
|---|---|
| `webapp/backend/app/services/orchestrator.py` | The crew engine: run_brief, `_po_flow`, `_one_bl(_concurrent)`, `_run_wave_concurrent`, `_concurrent_assembly_decision` (Fix B), `_contract_*`, gates, closure. |
| `webapp/backend/app/services/prompts_brownfield.py` | PO/engineer/QA prompt builders + doctrine blocks (`po_contract_instruction`, `po_wave_disjoint_instruction` (G2), `_engineer_contract_block`, "Test at the RIGHT layer" (Fix A2)). |
| `webapp/backend/app/services/regression_gate.py` | Per-BL gate `run_bl_tests` (Fix A1: `_is_frontend_test`, `_frontend_dir`, vitest branch), R19 coverage. |
| `webapp/backend/app/services/repo_config.py` | `.agentic-skills.json` loader (`frontend_test_cmd` field). |
| `webapp/backend/app/services/contract_bind.py` | The C# binder (template for a future React binder). |
| `webapp/backend/app/routers/projects.py` | `RunBriefRequest` schema + `/run-brief` endpoint. |
| `webapp/backend/tests/test_concurrent_assembly_decision.py`, `test_frontend_concurrency_fixes.py` | This session's tests. |
| `.claude/memory/` | Cross-session memory (start at `MEMORY.md`). |
| `CONTINUATION_PROMPT.md` | Prior session handoff (pre-this-session). |

---

## 11. First moves on the new machine (checklist)

1. Clone repo; checkout `development`; confirm HEAD (should be `164817a` or later once main
   is FF'd / run 5 lands follow-ups).
2. Copy `~/.ssh/id_ed25519_18012`; `ssh crew hostname` → `B460MDS3HACY1`.
3. `ssh crew`, check harness (`curl 127.0.0.1:8000/openapi.json` → 200) + services + that
   `cd ~/dev/ai-projects/agentic-skills && git status` is clean at the expected commit.
4. Read `CLAUDE.md`, `THESIS.md`, `ARCHITECTURE_INVARIANTS.md`, `.claude/memory/MEMORY.md`.
5. Finish the IN-FLIGHT items (Section 8): check run 5, FF main.
6. Then pick up the roadmap (Section 9). Surface findings to the operator before starting
   significant work (operator-gated).

— End of handoff. Keep this file updated as the migration completes.
