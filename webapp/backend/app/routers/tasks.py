"""Task endpoints.

POST /api/tasks/run-stream  — long-lived SSE stream that fires off an agent
task against an isolated git worktree and emits each tool call / message in
real time. Final SSE frame carries `{type:"done", commit_sha, ...}`.

GET  /api/tasks/repos       — list configured target repos.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.claude_agent import stream_agent_task
from app.services.git_worktree import (
    Worktree,
    create_worktree,
    get_commit_sha,
    has_new_commits,
    remove_worktree,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


REPOS_ROOT = Path(os.environ.get("AGENT_REPOS_ROOT", Path(__file__).resolve().parents[3] / "repos")).resolve()


class TaskRequest(BaseModel):
    task: str = Field(..., min_length=1, description="Single complex task for the agent.")
    repo: str = Field(..., description="Name of a repo under AGENT_REPOS_ROOT.")
    timeout_seconds: int = Field(1800, ge=60, le=7200)
    keep_worktree: bool = Field(False, description="If true, leave the worktree on disk after the run.")


@router.get("/repos")
def list_repos() -> dict:
    if not REPOS_ROOT.exists():
        return {"root": str(REPOS_ROOT), "repos": []}
    repos = []
    for p in sorted(REPOS_ROOT.iterdir()):
        if (p / ".git").exists():
            repos.append({"name": p.name, "path": str(p)})
    return {"root": str(REPOS_ROOT), "repos": repos}


def _sse(event: dict) -> bytes:
    """Format an event as one SSE frame."""
    return f"data: {json.dumps(event, default=str)}\n\n".encode()


@router.post("/run-stream")
async def run_task_stream(req: TaskRequest):
    repo_path = (REPOS_ROOT / req.repo).resolve()
    if not repo_path.is_dir() or not (repo_path / ".git").exists():
        raise HTTPException(status_code=404, detail=f"repo {req.repo!r} not found under {REPOS_ROOT}")

    async def gen():
        wt: Worktree | None = None
        try:
            wt = await create_worktree(repo_path)
            yield _sse({
                "type": "_meta",
                "phase": "worktree_ready",
                "task_id": wt.task_id,
                "branch": wt.branch,
                "path": str(wt.path),
            })
            async for event in stream_agent_task(
                req.task,
                wt.path,
                timeout_seconds=req.timeout_seconds,
            ):
                yield _sse(event)

            commit_sha = await get_commit_sha(wt)
            new_commits = await has_new_commits(wt, base_ref="HEAD~1")
            yield _sse({
                "type": "done",
                "task_id": wt.task_id,
                "branch": wt.branch,
                "commit_sha": commit_sha,
                "new_commits": new_commits,
            })
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "_error", "error": f"{type(exc).__name__}: {exc}"})
        finally:
            if wt is not None and not req.keep_worktree:
                # Leave the branch in place; only detach the worktree.
                try:
                    await remove_worktree(repo_path, wt)
                    yield _sse({"type": "_meta", "phase": "worktree_removed"})
                except Exception as exc:  # noqa: BLE001
                    yield _sse({"type": "_error", "error": f"worktree cleanup: {exc}"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
