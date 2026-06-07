# Webapp — Project State

**Branch:** `webapp` · **Date:** 2026-05-17 · **Status:** working end-to-end on a single dev machine

A stand-alone FastAPI + React app sitting next to the agentic-skills harness. Its job is to let a human kick off a complete agentic software-engineering workflow — brief decomposition, per-BL implementation, QA, and rubric scoring — by clicking buttons in a browser. Every agent invocation goes through the local `claude` CLI (no API key required), runs in an isolated git worktree, and either commits its result or surfaces a structured failure.

---

## 1. What this gives you

1. **Drop a brief in a textarea** → click **Decompose brief** → a PO-flavored Claude agent writes `.agile-v/BACKLOG.md` in your repo and the right pane parses it into a clickable list.
2. **Radio-select any BL** → click **Execute BL-XXXX** → an Engineer-flavored Claude agent implements just that one item against an isolated worktree branch (`agent/<task_id>`) and commits.
3. **Run QA** against the selected BL → a QA-flavored agent reads recent commits, runs tests, adds acceptance-driven coverage, fixes real bugs (not tests), writes `.agile-v/qa/<BL>.md`, and commits.
4. **Score Current BL** → a strict-but-fair scoring agent reads the workspace rubric, evaluates every dimension (0–5, 50 core + 25 role), writes `.agile-v/scorecards/<BL>.md` in the rubric's exact table format, and commits. Same rubric file (`rubrics/production_grade_scorecard.md`) the harness uses elsewhere, so scores are comparable across the whole system.
5. **Run claude-context index** → indexes the selected repo into Milvus via `@zilliz/claude-context-core` + Azure embeddings. UI badge reports `✓ N files, M chunks`.
6. **Run graphify** → runs `graphify update <repo>` to rebuild `graphify-out/graph.json`. UI badge reports `✓ N nodes, M edges`.
7. **Indeterminate progress bar** between the top section and the main two-pane shows when either indexer is running.
8. **Live SSE log** at the bottom streams every tool call, assistant message, and final result frame from whichever agent is active. Phase tag (`po`, `engineer`, `qa`, `scorer`) shows which role.

All seven agent flows use the **same** Claude Code CLI subprocess pattern (Option A from the original design discussion). Each flow runs in a fresh `git worktree` so concurrent invocations cannot clobber each other.

---

## 2. Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│ React + Vite                                                           │
│   App.jsx ─ repo dropdown │ 4 top buttons │ indeterminate progress    │
│                           │ brief pane    │ backlog list w/ radio     │
│                           │ summary card  │ shared SSE log            │
│   sse.js  ─ streamPost(): POST + parse text/event-stream via fetch    │
└────────────────────────────────────────────────────────────────────────┘
                              │ /api/* (proxied :5173 → :8000 by vite)
                              ▼
┌────────────────────────────────────────────────────────────────────────┐
│ FastAPI (uvicorn)                                                      │
│   app/main.py            auto-loads webapp/.env or ../.env.kimi/.gpt54│
│                          /api/health reports embedding provider, etc. │
│   routers/tasks.py       /api/tasks/repos (list), run-stream (raw)    │
│   routers/projects.py    /api/projects/{repo}/...                     │
│                              backlog        (parsed list)             │
│                              decompose-brief (PO agent, SSE)          │
│                              execute-bl      (Engineer, SSE)          │
│                              qa-bl           (QA, SSE)                │
│                              score-bl        (Scorer, SSE)            │
│                              index/graphify       (sync)              │
│                              index/claude-context (sync)              │
│   services/claude_agent.py  async subprocess → claude --print          │
│                                                 --output-format stream-json
│   services/git_worktree.py  git worktree add -b agent/<id>            │
│   services/backlog.py       parse BACKLOG.md → [{id,title,meta,body}] │
│   services/prompts.py       4 prompt builders (po/eng/qa/scorer)      │
│   services/indexing.py      wraps `graphify` CLI and the shared       │
│                             .spike-node/bridge.js (claude-context)    │
└────────────────────────────────────────────────────────────────────────┘
                              │
                  ┌───────────┼──────────────┐
                  ▼           ▼              ▼
              claude       graphify       Node bridge
            (subprocess)   (subprocess)   (subprocess →
                                             @zilliz/claude-context-core
                                             → Azure OpenAI embeddings
                                             → local Milvus :19530)
```

---

## 3. Endpoint reference

| Method | Path | Body | Returns | Notes |
|---|---|---|---|---|
| GET | `/api/health` | – | `{status, env_file, embedding_provider, milvus}` | Confirms auto-loaded env. |
| GET | `/api/tasks/repos` | – | `{root, repos:[{name, path}]}` | Lists git repos (incl. symlinks) under `backend/repos/`. |
| POST | `/api/tasks/run-stream` | `{task, repo}` | SSE | Generic free-form task runner (kept for parity with the original design doc). |
| GET | `/api/projects/{repo}/backlog` | – | `{path, items:[{id,title,priority,status,story,dependencies,body,…}]}` | Parses `.agile-v/BACKLOG.md`. |
| POST | `/api/projects/{repo}/decompose-brief` | `{brief, project_name?}` | SSE | PO agent → writes `.agile-v/BACKLOG.md`, commits in worktree, then copies the file back to main and commits the import. |
| POST | `/api/projects/{repo}/execute-bl` | `{bl_id, extra_notes?}` | SSE | Engineer agent prompted with one BL section only. |
| POST | `/api/projects/{repo}/qa-bl` | `{bl_id}` | SSE | QA agent — reads commits, runs tests, adds acceptance-driven coverage, writes `.agile-v/qa/<BL>.md`. |
| POST | `/api/projects/{repo}/score-bl` | `{bl_id}` | SSE | Read-mostly scoring agent using `rubrics/production_grade_scorecard.md`. Writes `.agile-v/scorecards/<BL>.md`. |
| POST | `/api/projects/{repo}/index/graphify` | – | `{ok, nodes, edges, graph_path}` | Runs `graphify update <repo> --no-cluster`. |
| POST | `/api/projects/{repo}/index/claude-context` | – | `{ok, indexed_files, total_chunks, status}` | Invokes the shared `.spike-node/bridge.js` (`op=index`). |

All four SSE endpoints emit:
- `{type:"_meta", phase:"worktree_ready"|"exit"|..., task_id, branch, role, bl_id?}` — orchestration crumbs
- `{type:"assistant"|"user"|"tool_use"|"tool_result"|"system"|"result", …}` — passed-through Claude stream-json frames
- `{type:"done", role, bl_id?, branch, commit_sha, new_commits, imported_backlog_path?}` — terminal frame
- `{type:"_error", error}` — surfaced exceptions

---

## 4. UI layout (single page, `App.jsx`)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Claude Code Agent Runner                                                 │
│ PO decomposes a brief → backlog list → click any item to run            │
│ the engineer agent on just that BL.                                     │
├──────────────────────────────────────────────────────────────────────────┤
│ Repo: [notes-app ▾]                                                      │
│   [Run claude-context index] ✓ 26 files, 159 chunks                      │
│   [Run graphify]              ✓ 160 nodes, 317 edges                     │
│ │ [Run QA (BL-0003)]  [Score BL-0003]    ← visible after select          │
├──────────────────────────────────────────────────────────────────────────┤
│ Indexing claude-context…                                                 │
│ ███████════════════════════ (indeterminate sweep when either idx runs)   │
├────────────────────────────────┬─────────────────────────────────────────┤
│ 1 · Brief → PO agent           │ 2 · Backlog (18)                        │
│ (optional project name)        │ ○ BL-0001 Bootstrap         [CRITICAL]  │
│ ┌────────────────────────────┐ │ ● BL-0002 Auth Signup/Login [CRITICAL]  │
│ │ # Project: …               │ │ ○ BL-0003 GET /me           [CRITICAL]  │
│ │ ## Requirements:…          │ │ ○ BL-0004 Workspace Create  [CRITICAL]  │
│ └────────────────────────────┘ │ …                                       │
│ [Decompose brief]              │ (optional extra notes)                  │
│                                │ [Execute BL-0002]                       │
├────────────────────────────────┴─────────────────────────────────────────┤
│ ✓ summary card (branch / commit / new_commits / imported_backlog_path)   │
├──────────────────────────────────────────────────────────────────────────┤
│ Stream (37) [ENGINEER]                                                   │
│ [meta] phase=worktree_ready task=ab12 branch=agent/ab12 role=engineer    │
│ assistant: → bash(git status)                                            │
│ tool_result: M app/main.py                                               │
│ …                                                                        │
│ ✓ done commit 6825722e                                                   │
└──────────────────────────────────────────────────────────────────────────┘
```

Components:
- **Repo dropdown** — populated from `GET /api/tasks/repos`. Symlinks are first-class (the path-escape check uses the un-resolved parent so `..` is still blocked but symlinks-to-anywhere are allowed).
- **4 top buttons** — Run claude-context index, Run graphify, Run QA, Score. The latter two are disabled until a BL is selected.
- **Indeterminate progress bar** — a 40%-wide blue gradient sweeps left→right every 1.4 s while `indexRunning.ctx || indexRunning.graph`. Label switches between *Idle / Indexing claude-context… / Refreshing graphify graph… / both*.
- **Brief pane** — textarea + optional project-name override + "Decompose brief".
- **Backlog pane** — radio-select list with priority pill, story preview, deps. Auto-reloads after every completed stream.
- **Summary card** — appears on `{type:"done", …}`; shows branch / commit / new-commits / (for PO) imported backlog path.
- **Event log** — shared by all four streaming flows. Each frame rendered by `EventLine` based on its `type`.

---

## 5. Auth model

The webapp doesn't store or require an `ANTHROPIC_API_KEY`. The `claude` subprocess inherits `HOME` and reads whatever credentials your terminal `claude /login` session already wrote into `~/.claude/`. That means corporate-provisioned Claude Code (OAuth/SSO, Bedrock proxy, Vertex proxy) all work transparently — if `claude` works in your terminal, it works here.

Documented in `webapp/README.md`. Validated end-to-end on 2026-05-17 with `claude --version` 2.1.143.

---

## 6. Env auto-loading

`app/main.py` loads the first .env file it finds among:
1. `$WEBAPP_ENV_FILE`
2. `webapp/.env`
3. `../.env.kimi`  (chat = kimi-k2.6 via Moonshot, embeddings = Azure)
4. `../.env.gpt54` (chat = Azure gpt-5.4, embeddings = Azure)

Existing process env wins (no clobbering). This means uvicorn can be started with a bare `uvicorn app.main:app --reload` and the retrieval layer still gets Azure / Milvus credentials. `/api/health` returns which file was picked up.

---

## 7. Prompt design

Each role's prompt enforces a non-negotiable completion protocol so the UI can confirm success structurally rather than by parsing prose.

### PO (`build_po_prompt`)
- Writes `.agile-v/BACKLOG.md` in the BL-XXXX format the parser expects.
- Optionally writes `REQUIREMENTS.md` if the brief contains numbered requirements.
- Commits as `po: decompose brief into N backlog items`.
- Final line: `{"status":"complete","backlog_path":".agile-v/BACKLOG.md","item_count":N,"commit_sha":"…"}`.

### Engineer (`build_engineer_prompt`)
- Receives ONE BL section.
- Commits as `<bl_id>: <short>` with a body explaining what changed and why.
- Final line: `{"status":"complete","bl_id":"…","commit_sha":"…","files_changed":N,"summary":"…"}`.

### QA (`build_qa_prompt`)
- Read commits, run existing tests, add acceptance-driven coverage (happy / negative / privacy / cross-tenant), fix real bugs not tests.
- Writes `.agile-v/qa/<BL>.md` summary.
- Final line: `{"status":"complete","bl_id":"…","commit_sha":"…","tests_added":N,"bugs_found":N,"verdict":"PASS|PASS-W/R|FAIL","summary":"…"}`.

### Scorer (`build_score_prompt`)
- Receives the BL section + the entire rubric text inline so it scores against the same dimensions the rest of the system uses.
- Decision rules baked into the prompt: `Fail` on broken/uncovered; `Pass W/R` if ≥2 dims score ≤3; `Pass` otherwise.
- Writes `.agile-v/scorecards/<BL>.md` in the rubric's exact table format.
- Final line: `{"status":"complete","bl_id":"…","commit_sha":"…","total":N,"core":N,"role":N,"verdict":"Pass|Pass W/R|Fail","summary":"…"}`.

---

## 8. Files (3,228 LOC excluding deps)

| Path | LOC | Purpose |
|---|---|---|
| `backend/app/main.py` | ~50 | FastAPI entry + CORS + env auto-load + /api/health |
| `backend/app/routers/tasks.py` | 110 | Generic task runner + repo listing |
| `backend/app/routers/projects.py` | 362 | All per-repo endpoints (backlog, decompose, execute, qa, score, index×2) |
| `backend/app/services/claude_agent.py` | 166 | async subprocess streaming wrapper around `claude --print --output-format stream-json` |
| `backend/app/services/git_worktree.py` | 74 | `git worktree add/remove`, commit-sha + new-commits helpers |
| `backend/app/services/backlog.py` | 72 | Parser for `.agile-v/BACKLOG.md` |
| `backend/app/services/prompts.py` | 189 | 4 prompt builders + 3 completion-protocol blocks |
| `backend/app/services/indexing.py` | 103 | graphify CLI + claude-context bridge wrappers |
| `backend/requirements.txt` | 3 | fastapi, uvicorn[standard], pydantic |
| `frontend/src/App.jsx` | 388 | Whole UI (radio backlog, 4 buttons, progress bar, SSE log) |
| `frontend/src/sse.js` | 37 | streamPost helper (fetch-reader since EventSource is GET-only) |
| `frontend/src/styles.css` | 103 | All styles incl. the indeterminate-bar animation |
| `frontend/{index.html,main.jsx,vite.config.js,package.json}` | 56 | Vite scaffold |

---

## 9. Required tooling on the host

| Tool | Min version | Used by |
|---|---|---|
| `python` | 3.12 | uvicorn |
| `node`   | ≥20  | claude-context bridge (`.spike-node/`) |
| `claude` CLI | 2.x | subprocess invocation by every SSE endpoint |
| `graphify` CLI | any | `index/graphify` endpoint |
| Local Milvus | 2.5.x at `localhost:19530` | claude-context indexing |
| Azure OpenAI deployments | `gpt-5.4` and `text-embedding-3-large` | env-driven; see `.env.gpt54` / `.env.kimi` |

---

## 10. Repos exposed in the dropdown

Currently:
- `lg-graph-test` — symlink to the agentic-skills target repo. Already has a complete 18-item backlog (from the earlier kimi run + my manual treatment); a useful playground for the QA / Score buttons since the engineering work is done.
- `notes-app` — fresh empty git repo with one initial commit. No backlog yet — paste a brief and click Decompose to populate it.

To expose more: drop a git repo (or a symlink to one) under `webapp/backend/repos/` and refresh the page. Anything in `backend/repos/*` is gitignored by `webapp/.gitignore` so the outer repo doesn't pick it up.

---

## 11. Branch + commit history (chronological)

```
9b46077  webapp: stop tracking backend/repos/* contents
76fefd7  webapp: 'Run QA' + 'Score Current BL' buttons + endpoints
d320f68  webapp: indeterminate progress bar between top section and main panes
6825722  webapp: add 'Run claude-context index' + 'Run graphify' buttons
ca86d97  webapp: fix REPOS_ROOT path + allow symlinked repos
de1eebc  webapp: PO decomposition + selectable backlog + per-BL execution
b42e1fc  webapp: document corporate / OAuth auth path (no ANTHROPIC_API_KEY required)
d0c6f97  webapp: FastAPI + React Claude Code agent runner with SSE streaming
```

All on branch `webapp` (descended from `main`, which holds the initial agentic-skills snapshot).

---

## 12. Known constraints / deferred

- **Per-BL execution does not auto-merge to the main checkout.** Each Engineer/QA/Scorer run leaves an `agent/<id>` branch in the repo. The PO flow IS auto-merged to main so the backlog endpoint can see it. If you want Engineer output back on main, currently you must merge manually (`git merge agent/<id>` in the target repo).
- **No persistence of past streams.** When the page refreshes, the event log resets. Backlog auto-reloads from disk after each stream; scorecards / QA reports live in the repo so they survive.
- **No retrieval tools handed to the in-browser agents.** When you click "Execute BL-XXXX" via the webapp, the spawned `claude` does NOT have access to `semantic_search` / `graph_neighbors` etc. Those live in the langgraph_engine harness. To give the webapp agents retrieval, we'd need to register custom tools via Claude Code's plugin/MCP mechanism. Open work.
- **Single concurrent agent per user assumed.** The frontend gates buttons on a single `phase` state; firing two streams in two tabs against the same repo will race. Worktree isolation prevents data corruption but the UI will look confused.
- **Scoring runs the test suite.** The score endpoint executes `pytest -q` (or whatever) as part of grading. For repos with very slow / external-dependent test suites, the 1800 s default timeout may not be enough.
- **The "Score" verdict differs from the manual self-score by up to ~3 points** for the same work — within rubric inter-rater noise (see exchange on BL-0001 67 vs 70). Both numbers tell the same story; absolute comparability requires the same scorer prompt being used both times.

---

## 13. How to run from a fresh clone

```bash
# Once
cd webapp/backend
python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

cd ../frontend
npm install

# Each session
cd webapp/backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000 &
cd webapp/frontend && npm run dev                          # → http://localhost:5173

# Drop a repo to work on
ln -s /abs/path/to/your/repo webapp/backend/repos/myrepo   # or
mkdir webapp/backend/repos/fresh && cd webapp/backend/repos/fresh && git init -b main && git commit --allow-empty -m init
```

That's it. Refresh the browser, the repo appears in the dropdown.

---

## 14. Brownfield mode (branch `brownfield-production` only)

This branch adds an entire alternate doctrine track. The webapp now auto-selects between *greenfield* and *brownfield* prompt families based on `target_status()`. New / changed modules:

| File | Purpose |
|---|---|
| `backend/app/services/prompts_brownfield.py` | Brownfield builders for PO / Engineer / QA / Scorer. **Each loads the SKILLS.md file verbatim** from `skills/brownfield/brownfield-production-incremental-<role>/SKILLS.md` as the binding doctrine block, with a small "WEBAPP CONTRACT" wrapper (artifact paths, completion JSON shape). |
| `backend/app/services/prompts.py` | `select_family(target_status_result)` dispatcher + `build_po / build_engineer / build_qa / build_score` wrappers that route greenfield ↔ brownfield. |
| `backend/app/services/brownfield.py` | `classify_target()`, `pick_artifact_dir()`, `detect_test_command()`, rubric path map. |
| `backend/app/services/repo_config.py` | Loads `.agentic-skills.json` from the target repo root: `agent_branch`, `main_ref`, `test_cmd`, `doctrine` overrides. Default `agent_branch="agentic-skills-work"`, `main_ref="main"`. |
| `backend/app/services/git_worktree.py` | `create_worktree(base_ref=...)` so forks come off the configured agent branch; `fast_forward_target()` (was `fast_forward_main`) merges into the configured target ref and checks out the right ref first. |
| `backend/app/services/regression_gate.py` | Differential pre/post pytest in disposable worktrees; reports `kind=green / regressed / inconclusive / error / skipped`. Auto-detects `test_cmd` or reads override from config. |
| `backend/app/services/doctrine_validator.py` | Hard pre-merge artifact validator + `build_fix_prompt(role, validation)`. Validates: PO → CODEBASE_CONTEXT.md + every BL's `_brownfield/<BL>/codebase_context.md` + SPRINT_PLAN_C1.md; Engineer → `_brownfield/<BL>/eng_patterns.md`; QA → `_brownfield/<BL>/qa_impact.md` + `.agile-v/qa/<BL>.md`. |
| `rubrics/production_grade_scorecard_brownfield.md` | Sidecar rubric — adds Pattern Fidelity, Regression Coverage, Characterization Tests, Invariant Preservation, Blast Radius (5×0–5 = 25). Single brownfield-axis score ≤2 forces Fail. |
| `frontend/src/App.jsx` | Surfaces doctrine, regression-gate verdict, regressions list, and `Review & merge` / `Force merge` buttons in the done card; new `[gate]` line types in the SSE stream renderer. |

### Endpoints added

| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/api/projects/{repo}/merge-branch` | `{branch, skip_gate}` | Manual review path — re-runs the gate then merges, or skips the gate. |
| GET | `/api/projects/{repo}/branches` | – | Lists `agent/*` branches not yet merged into the configured `agent_branch`. |

### Brownfield artifact directory

Agents write into a top-level `_brownfield/` at the target repo root:

```
_brownfield/
  _codebase_context/CODEBASE_CONTEXT.md     # PO whole-system context
  SPRINT_PLAN_C1.md                          # PO sprint plan
  <BL-id>/
    codebase_context.md                      # PO per-BL context
    eng_patterns.md                          # Engineer pattern-match summary
    qa_impact.md                             # QA impact analysis
```

**Important:** do NOT add `_brownfield/` to the brownfield repo's `.gitignore`. The agent branch is the boundary that keeps these out of upstream `master`; gitignoring silently drops artifacts from `git add -A` and breaks the role hand-off chain.

### Per-target config

`.agentic-skills.json` at the target repo root. Example (the current target,
`project-management-app`, which is **Docker-free** and uses `main` as the
pristine ref + `integration` as the agent branch):

```json
{
  "agent_branch": "integration",
  "main_ref": "main",
  "doctrine": "brownfield",
  "test_cmd": ["/abs/path/to/target/.venv/bin/pytest", "backend/tests", "-q"]
}
```

For a Docker-based target the `test_cmd` would instead be something like
`["docker", "compose", "exec", "-T", "backend", "pytest", "-q"]`. With no
`compose.yml`/`compose.gate.yml` present, `run_bl_tests` takes its native
(no-Docker) branch and runs `test_cmd[0]` directly against the BL's test files.

### Doctrine validation + retry

After every agent run's first commit, the validator checks the worktree for required artifacts. If missing/too-small:

1. SSE: `_meta phase=doctrine_check kind=incomplete attempt=N missing=[...]`
2. Same agent re-invoked in same worktree with `build_fix_prompt(role, validation)`.
3. Up to **`MAX_FIX_RETRIES = 2`**.
4. If still incomplete: `kind=give_up`, copy-back (PO) / fast-forward (Engineer/QA) **refused**. UI shows "Review & merge".

### Embedding stack on this branch

Local Ollama (homebrew) serving `bge-m3` at `127.0.0.1:11434`. `webapp/.env` is autoloaded first:

```
EMBEDDING_PROVIDER=Ollama
OLLAMA_HOST=http://127.0.0.1:11434
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIMENSION=1024
```

The chat env files (`.env.kimi`, `.env.gpt54`) are no longer used by the webapp on this branch — `claude` CLI handles all LLM via corporate OAuth.

### Current target

`project-management-app` (at `~/dev/ai-projects/brownfield-targets/project-management-app`, symlinked into `webapp/backend/repos/`). Purpose-built **Docker-free** brownfield: FastAPI + SQLModel + SQLite (no auth, `create_all`, no Alembic) + React/Vite/TS, API-first Projects→Tasks. Pristine `main`, agent branch `integration`. Freshly created 2026-06-06 — baseline suite green (16 backend tests, native pytest), **no sprints run yet**. The prior target `full-stack-fastapi-template` and its crew branches were removed 2026-06-06.

### Findings triage + on-demand fix dispatch (ABL-0014 §I.3 / ABL-0015 / ABL-0021)

After a sprint's acceptance pass, cross-BL findings land in a per-feature
ledger (`_brownfield/features/<slug>/acceptance/findings_log.jsonl`). The
operator reviews and acts on them from the **FindingsTriagePanel** in
`frontend/src/AppV2.jsx` (opens in the detail rail when an acceptance tile
has findings). Endpoints:

- `GET  /api/projects/{repo}/findings?feature_slug=…&status=pending|all` —
  list findings.
- `POST /api/projects/{repo}/verdict` `{feature_slug, finding_id, verdict,
  note}` — record `confirmed | refuted | deferred`.
- `POST /api/projects/{repo}/dispatch-followup` `{feature_slug, finding_id,
  timeout_seconds}` — **ABL-0021** on-demand: spawn a follow-up engineer to
  fix a **confirmed product_bug** (SSE-streamed `acceptance.followup.*` +
  engineer sub-events). Pre-validates eligibility (404 unknown / 409
  not-eligible / 409 already-dispatched, R15). Reuses the ABL-0015 dispatch
  engine — the fix clears the same regression-gate + auto-merge bar as any BL.

**Operator flow (two-step, per-finding):** sprint lands → panel shows
exposed findings → **Confirm** (verdict) → a **"Dispatch fix"** button
appears on confirmed product_bugs → click dispatches that finding and
streams progress; the card then shows `fix: dispatched|merged` + merged sha.
Default-safe: dispatch requires an explicit confirmed verdict + button press.
