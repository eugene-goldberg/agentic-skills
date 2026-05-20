# agentic-skills — orientation for Claude

This repo has two top-level moving parts. Read the right one before editing.

## 1. `langgraph_engine/` — the original harness

LangGraph orchestrator that runs role-LLMs (PO / Engineer / QA) through `python -m langgraph_engine run …`. Used for the published A/B comparison runs against gpt-5.4, kimi-k2.6, qwen, Claude. State machine in `graph.py`, role nodes in `nodes/`, retrieval layer (graph + claude-context-core bridge) in `retrieval/`. CLI in `__main__.py`.

When working here, the historical signal lives in `runs/`, `ab_runs/`, and `Project_Brief.md`. Reference repo for retrieval is `reference-repos/fastapi-good-patterns/`. Target repo is `target-repos/lg-graph-test/`.

## 2. `webapp/` — FastAPI + React Claude Code agent runner

A stand-alone browser UI that invokes the local `claude` CLI as a subprocess (no `ANTHROPIC_API_KEY` needed — inherits corporate OAuth from `~/.claude/`). Exposes PO decomposition, per-BL execution, QA, rubric scoring, and two indexers (graphify + claude-context) through SSE-streamed endpoints.

**For any work on the webapp — read [`webapp/PROJECT_STATE.md`](webapp/PROJECT_STATE.md) first.** It is the authoritative current-state document covering:

- The 10 backend endpoints and what each does
- The four agent prompt builders (`po`, `engineer`, `qa`, `scorer`) and their completion protocols
- The React UI layout, top-section buttons, indeterminate progress bar, SSE log
- Env auto-loading (`webapp/.env` → `.env.kimi` → `.env.gpt54`)
- Repo dropdown and the symlink-vs-path-escape security model
- The full commit history on branch `webapp` (8 commits, 3,228 LOC)
- 6 known constraints / deferred items
- Step-by-step run instructions

The shorter `webapp/README.md` is a quick-start; `PROJECT_STATE.md` is the deep reference.

## Branches

- `main` — initial harness snapshot
- `skills_with_graphs` — Phase 0–4 retrieval-layer plan and implementation, A/B harness
- `webapp` — FastAPI+React webapp Claude Code runner (greenfield doctrine)
- `brownfield-production` — current working branch; adds brownfield doctrine on top of `webapp` (auto-doctrine selection by target_status, sidecar rubric, per-repo `.agentic-skills.json`, regression-gated auto-merge)

## Brownfield boundary (this branch only)

Hard distinction between two kinds of repository:

1. **Core project** — `agentic-skills/` (this checkout). Holds prompts, rubrics, langgraph engine, webapp source. Its git history is internal.
2. **Brownfield targets** — real-world independent repos with their own remotes. Subjects of work by the agents, never part of agentic-skills, never committed to this repo's index.

Brownfield targets are cloned **outside** agentic-skills, by convention under `~/dev/ai-projects/brownfield-targets/<repo>/`, and exposed to the webapp via a symlink at `webapp/backend/repos/<repo>`. Agentic-skills' `.gitignore` already ignores `webapp/backend/repos/*`.

Each brownfield target carries an `.agentic-skills.json` at its root with:

- `agent_branch` — branch off which agent worktrees fork AND into which successful runs auto-merge. Default: `agentic-skills-work`.
- `main_ref` — pristine upstream branch (`main` or `master`).
- `test_cmd` — optional override for the regression-gate test command (auto-detected otherwise).
- `doctrine` — optional explicit family override (`brownfield` / `greenfield`).

Currently configured target: **`full-stack-fastapi-template`** symlinked from `~/dev/ai-projects/brownfield-targets/full-stack-fastapi-template/`. Upstream uses `master` as default branch.

## Brownfield artifact directory

Agents write pre-work artifacts into a top-level `_brownfield/` directory at the root of the target repo:

```
_brownfield/
  _codebase_context/CODEBASE_CONTEXT.md   # PO: whole-system context
  SPRINT_PLAN_C1.md                       # PO: sprint plan
  <BL-id>/
    codebase_context.md                   # PO: per-BL context
    eng_patterns.md                       # Engineer: pattern matching
    qa_impact.md                          # QA: impact & coverage
```

Falls back to `_agentic_artifacts/` only if `_brownfield/` is taken upstream.

## Brownfield rubric

Brownfield runs are scored against `rubrics/production_grade_scorecard_brownfield.md`, which adds five dimensions (Pattern Fidelity, Regression Coverage, Characterization Tests, Invariant Preservation, Blast Radius) to the standard core+role scoring. A single brownfield-axis score ≤ 2 forces a Fail verdict regardless of total.

## Auto-merge gating (brownfield)

Engineer and QA runs no longer fast-forward into the agent branch on a simple commit-success:

1. Agent commits to its `agent/<task_id>` worktree branch.
2. **Doctrine validator** (`app/services/doctrine_validator.py`) checks that the role's required artifacts exist on disk and are ≥120 bytes. If anything is missing, the agent is **re-invoked in the same worktree** with a delta prompt (`build_fix_prompt`) listing exact missing paths, up to 2 retries. UI sees `_meta phase=doctrine_check kind=incomplete|complete|give_up`.
3. **Regression gate** (`app/services/regression_gate.py`) creates two disposable worktrees off `target_ref`, dry-runs the agent branch into the second, runs `test_cmd` in both, and computes the regressed-test set. Result kinds: `green` (post exit=0, no regressions), `regressed`, `inconclusive` (post exit≠0 but no parseable test output — e.g. test runner couldn't actually run), `skipped` (greenfield, gate intentionally off), `error`.
4. Auto-merge proceeds **only** if both `doctrine_ok` AND `gate.kind=="green"`. Otherwise the agent branch stays in place and the UI surfaces a "Review & merge" button.

Endpoints:
- `GET /api/projects/<repo>/branches` — agent branches not yet merged into the configured `agent_branch`.
- `POST /api/projects/<repo>/merge-branch` `{branch, skip_gate}` — re-runs the gate then merges, or skips the gate on operator override. UI exposes both "Review & merge (re-run gate)" and "Force merge (skip gate)" buttons on Engineer/QA done cards.

## Embedding stack (this branch only)

Embeddings come from **local Ollama on this Mac**, not Azure:

- Model: `bge-m3` (1024-dim), via `brew services start ollama`
- Config: `webapp/.env` (autoloads first):
  ```
  EMBEDDING_PROVIDER=Ollama
  OLLAMA_HOST=http://127.0.0.1:11434
  EMBEDDING_MODEL=bge-m3
  EMBEDDING_DIMENSION=1024
  ```
- Bridge: `.spike-node/bridge.js` (auto-regenerated from `langgraph_engine/retrieval/semantic.py`'s `BRIDGE_SCRIPT` constant) carries an `OllamaEmbedding` class alongside `AzureEmbedding`.
- Azure path still exists for the older harness in `langgraph_engine/`; both providers selected via `EMBEDDING_PROVIDER`.

## Current brownfield state

Target: **`full-stack-fastapi-template`** symlinked at `webapp/backend/repos/full-stack-fastapi-template`, working branch `agentic-skills-work`.

Completed cycles (all on `agentic-skills-work`, `master` pristine):

- **BL-0001** (Workspace SQLModel + Alembic) — PO 13 BLs / Engineer `6abe64e` / QA PASS `011baeb` / Scorer **92/100 Pass** `45464e1`. 25 files / +1118 / -0 vs `master`.

Known infrastructure gap: the regression gate cannot run in-container `pytest` on this Mac because `compose.override.yml` uses Docker Compose v2.22+ `develop:` key that the local Engine 24.0.6 rejects. Until upgraded or worked around, each Engineer/QA commit is force-merged via `merge-branch?skip_gate=true`.

## Auto-memory

Memory files live in this repo at `.claude/memory/`, symlinked from `~/.claude/projects/<encoded-path>/memory` so Claude Code's auto-memory system finds them at the canonical location. After a fresh clone (or if the symlink ever breaks), run:

```bash
scripts/setup_memory_symlink.sh
```

The script is idempotent and refuses to clobber a real directory at the target.

## Conventions worth honoring

- Never commit `.env*` files (gitignored).
- `webapp/backend/repos/*` is gitignored — those are user-managed git repos exposed to the UI, not part of this repo.
- The scoring rubric is **one file**: `rubrics/production_grade_scorecard.md`. Both the harness and the webapp's `score-bl` endpoint feed it to the scorer prompt verbatim. Don't fork it.
- Agent subprocess invocations always run in an isolated `git worktree add -b agent/<task_id>` so concurrent runs can't clobber each other. See `webapp/backend/app/services/git_worktree.py`.
