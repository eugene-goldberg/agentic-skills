"""FastAPI entrypoint."""
import asyncio
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def _autoload_env() -> str | None:
    """Best-effort load of retrieval env vars from common .env locations.

    Checks (in order):
      1. WEBAPP_ENV_FILE if set
      2. webapp/.env
      3. agentic-skills/.env.kimi  (chat=kimi, embeddings=Azure)
      4. agentic-skills/.env.gpt54 (chat=Azure gpt-5.4, embeddings=Azure)
    First file found wins. Existing env vars are NOT overwritten.
    """
    explicit = os.environ.get("WEBAPP_ENV_FILE")
    here = Path(__file__).resolve().parents[2]  # webapp/
    candidates = [
        Path(explicit) if explicit else None,
        here / ".env",
        here.parent / ".env.kimi",
        here.parent / ".env.gpt54",
    ]
    for p in candidates:
        if p and p.is_file():
            for line in p.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'").strip('"')
                os.environ.setdefault(k, v)
            return str(p)
    return None


_LOADED_ENV = _autoload_env()

from app.routers import projects, tasks  # noqa: E402  (after env load)

app = FastAPI(title="Claude Code Agent Runner", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router)
app.include_router(projects.router)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "env_file": _LOADED_ENV,
        "embedding_provider": os.environ.get("EMBEDDING_PROVIDER"),
        "milvus": os.environ.get("MILVUS_ADDRESS"),
    }


# A48 follow-up (2026-06-02): force-down any orchestrator-spawned compose
# stacks on uvicorn shutdown so a SIGTERM (operator Ctrl+C, kill, container
# restart) doesn't orphan postgres data volumes into Docker.raw's 60 GB
# VM-disk cap. Catches gate stacks (project=agentic-skills-*), acceptance
# stacks (project=acceptance-*), and engineer-spawned worktree stacks
# (whose worktree-removal hook in git_worktree.py didn't get to run before
# the shutdown).
_ORCHESTRATOR_PROJECT_PATTERNS = ("agentic-skills-", "acceptance-")


@app.on_event("shutdown")
async def _reap_orchestrator_compose_stacks() -> None:
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "ps", "-a",
            "--format", "{{.Label \"com.docker.compose.project\"}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
    except Exception:
        return
    projects = set()
    for line in out.decode().splitlines():
        line = line.strip()
        if line and any(line.startswith(p) for p in _ORCHESTRATOR_PROJECT_PATTERNS):
            projects.add(line)
    for project in projects:
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "compose", "-p", project,
                "down", "-v", "--remove-orphans",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.communicate(), timeout=30.0)
        except Exception:
            continue
