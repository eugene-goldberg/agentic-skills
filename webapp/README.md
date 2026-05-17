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

## Required env

- `ANTHROPIC_API_KEY` — for the `claude` CLI.
- `claude` must be on `$PATH` (install via `npm i -g @anthropic-ai/claude-code`).

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
