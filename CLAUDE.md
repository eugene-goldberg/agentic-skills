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
- `webapp` — everything in `webapp/`; current working branch for that subproject

## Conventions worth honoring

- Never commit `.env*` files (gitignored).
- `webapp/backend/repos/*` is gitignored — those are user-managed git repos exposed to the UI, not part of this repo.
- The scoring rubric is **one file**: `rubrics/production_grade_scorecard.md`. Both the harness and the webapp's `score-bl` endpoint feed it to the scorer prompt verbatim. Don't fork it.
- Agent subprocess invocations always run in an isolated `git worktree add -b agent/<task_id>` so concurrent runs can't clobber each other. See `webapp/backend/app/services/git_worktree.py`.
