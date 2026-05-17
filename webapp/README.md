# Claude Code Agent — Web Runner

A stand-alone FastAPI + React app that invokes the Claude Code CLI against a
git repository, streams every tool call / assistant message to the browser via
Server-Sent Events, and confirms a final commit was produced.

Implements **Option A** from the integration discussion: Python `asyncio`
subprocess driving the `claude` binary with `--print --output-format stream-json`.

## Architecture

```
React (Vite)  ──POST /api/tasks/run-stream──▶  FastAPI
   ▲                                            │
   │ EventSource SSE                            │ asyncio.create_subprocess_exec
   │                                            ▼
   └──── line-delimited JSON ◀───────  claude --print --stream-json
                                                │
                                                ▼
                                          git commit in worktree
```

## Run

```bash
# Backend
cd webapp/backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd webapp/frontend
npm install
npm run dev
```

Open http://localhost:5173.

## Required setup

The backend invokes the `claude` CLI as a subprocess, inheriting your shell
environment. Auth modes — pick whichever matches how you already use Claude
Code from a terminal:

| You sign in to Claude Code with… | What the webapp needs |
|---|---|
| `claude /login` (personal or company OAuth — most common) | Nothing extra. Subprocess inherits `HOME` and reads `~/.claude/` credentials your existing session created. |
| `ANTHROPIC_API_KEY` env var | Export it in the shell that launches `uvicorn`. |
| Corporate Bedrock proxy | `export CLAUDE_CODE_USE_BEDROCK=1` plus the relevant AWS env. |
| Corporate Vertex proxy | `export CLAUDE_CODE_USE_VERTEX=1` plus GCP env. |

In all cases the `claude` binary itself must be on `$PATH`. Confirm with
`which claude` and `claude --version`. If you already run agent tasks from
your terminal, you are good.

## Repo layout

```
webapp/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI entry + CORS
│   │   ├── routers/tasks.py       # /api/tasks/run-stream
│   │   ├── services/claude_agent.py  # async subprocess + SSE generator
│   │   └── services/git_worktree.py  # per-task worktree isolation
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       └── styles.css
└── README.md
```
