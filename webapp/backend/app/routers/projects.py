"""Project-scoped endpoints: brief decomposition + per-BL execution.

Layered on top of the existing /api/tasks stream service:

  POST /api/projects/{repo}/decompose-brief   →  PO agent  (SSE)
  GET  /api/projects/{repo}/backlog            →  parsed backlog items
  POST /api/projects/{repo}/execute-bl         →  Engineer agent for one BL (SSE)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services import backlog as backlog_svc
from app.services.claude_agent import stream_agent_task
from app.services.git_worktree import (
    Worktree,
    create_worktree,
    get_commit_sha,
    has_new_commits,
    remove_worktree,
)
from app.services.prompts import build_engineer_prompt, build_po_prompt

router = APIRouter(prefix="/api/projects", tags=["projects"])

REPOS_ROOT = Path(
    os.environ.get(
        "AGENT_REPOS_ROOT",
        Path(__file__).resolve().parents[2] / "repos",
    )
).resolve()


def _repo_dir(repo: str) -> Path:
    # Reject '..' or absolute-path tricks by requiring `repo` to be a direct
    # child entry of REPOS_ROOT. Symlinks are intentionally allowed so users
    # can expose existing repos without copying them.
    entry = REPOS_ROOT / repo
    if entry.parent.resolve() != REPOS_ROOT:
        raise HTTPException(status_code=400, detail="repo name not allowed")
    p = entry.resolve()
    if not p.is_dir() or not (p / ".git").exists():
        raise HTTPException(status_code=404, detail=f"repo {repo!r} not found")
    return p


def _sse(event: dict) -> bytes:
    return f"data: {json.dumps(event, default=str)}\n\n".encode()


class DecomposeRequest(BaseModel):
    brief: str = Field(..., min_length=20)
    project_name: str | None = None
    timeout_seconds: int = Field(2400, ge=60, le=7200)


class ExecuteBLRequest(BaseModel):
    bl_id: str = Field(..., pattern=r"^BL-\d{4}$")
    extra_notes: str | None = None
    timeout_seconds: int = Field(2400, ge=60, le=7200)
    keep_worktree: bool = False


# ----------------------- listing -----------------------------------------

@router.get("/{repo}/backlog")
def get_backlog(repo: str) -> dict:
    repo_dir = _repo_dir(repo)
    bf = backlog_svc.find_backlog(repo_dir)
    if bf is None:
        return {"path": None, "items": []}
    items = backlog_svc.parse_file(bf)
    return {
        "path": str(bf.relative_to(repo_dir)),
        "items": [
            {
                "id": it.id,
                "title": it.title,
                "type": it.meta.get("type"),
                "priority": it.meta.get("priority"),
                "status": it.meta.get("status"),
                "effort": it.meta.get("effort"),
                "dependencies": it.meta.get("dependencies"),
                "story": next(
                    (
                        ln.split(":", 1)[1].strip()
                        for ln in it.body.splitlines()
                        if ln.lower().startswith("**story:**")
                    ),
                    None,
                ),
                "body": it.body,
            }
            for it in items
        ],
    }


# ----------------------- decompose ---------------------------------------

@router.post("/{repo}/decompose-brief")
async def decompose_brief(repo: str, req: DecomposeRequest):
    repo_dir = _repo_dir(repo)
    prompt = build_po_prompt(req.brief, req.project_name or repo)

    async def gen():
        wt: Worktree | None = None
        try:
            wt = await create_worktree(repo_dir)
            yield _sse({
                "type": "_meta",
                "phase": "worktree_ready",
                "task_id": wt.task_id,
                "branch": wt.branch,
                "role": "po",
            })
            async for event in stream_agent_task(
                prompt,
                wt.path,
                timeout_seconds=req.timeout_seconds,
            ):
                yield _sse(event)
            commit_sha = await get_commit_sha(wt)
            new_commits = await has_new_commits(wt, base_ref="HEAD~1")

            # Merge the PO branch back into the repo's main so subsequent BL
            # executions can see the BACKLOG.md. We do a fast-forward / squash
            # by simply copying the produced BACKLOG.md into the main repo.
            merged_bl_path: str | None = None
            from shutil import copy2
            src_bl = wt.path / ".agile-v" / "BACKLOG.md"
            if src_bl.exists():
                dst_bl = repo_dir / ".agile-v" / "BACKLOG.md"
                dst_bl.parent.mkdir(parents=True, exist_ok=True)
                copy2(src_bl, dst_bl)
                merged_bl_path = str(dst_bl.relative_to(repo_dir))
                # Commit the import on main
                import subprocess
                subprocess.run(["git", "add", ".agile-v/"], cwd=repo_dir, check=False)
                subprocess.run(
                    ["git", "commit", "-m", f"po: import backlog from {wt.branch}",
                     "--author", "Claude PO Agent <po@webapp.local>"],
                    cwd=repo_dir,
                    check=False,
                )

            yield _sse({
                "type": "done",
                "role": "po",
                "task_id": wt.task_id,
                "branch": wt.branch,
                "commit_sha": commit_sha,
                "new_commits": new_commits,
                "imported_backlog_path": merged_bl_path,
            })
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "_error", "error": f"{type(exc).__name__}: {exc}"})
        finally:
            if wt is not None:
                try:
                    await remove_worktree(repo_dir, wt)
                    yield _sse({"type": "_meta", "phase": "worktree_removed"})
                except Exception as exc:  # noqa: BLE001
                    yield _sse({"type": "_error", "error": f"cleanup: {exc}"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ----------------------- execute BL --------------------------------------

@router.post("/{repo}/execute-bl")
async def execute_bl(repo: str, req: ExecuteBLRequest):
    repo_dir = _repo_dir(repo)
    bf = backlog_svc.find_backlog(repo_dir)
    if bf is None:
        raise HTTPException(status_code=400, detail="no BACKLOG.md found — decompose a brief first")
    text = bf.read_text(encoding="utf-8")
    section = backlog_svc.extract_section(text, req.bl_id)
    if section is None:
        raise HTTPException(status_code=404, detail=f"{req.bl_id} not found in backlog")

    full_prompt = build_engineer_prompt(req.bl_id, section)
    if req.extra_notes:
        full_prompt += f"\n\n## Extra user notes\n{req.extra_notes}\n"

    async def gen():
        wt: Worktree | None = None
        try:
            wt = await create_worktree(repo_dir)
            yield _sse({
                "type": "_meta",
                "phase": "worktree_ready",
                "task_id": wt.task_id,
                "branch": wt.branch,
                "bl_id": req.bl_id,
                "role": "engineer",
            })
            async for event in stream_agent_task(
                full_prompt,
                wt.path,
                timeout_seconds=req.timeout_seconds,
            ):
                yield _sse(event)
            commit_sha = await get_commit_sha(wt)
            new_commits = await has_new_commits(wt, base_ref="HEAD~1")
            yield _sse({
                "type": "done",
                "role": "engineer",
                "bl_id": req.bl_id,
                "task_id": wt.task_id,
                "branch": wt.branch,
                "commit_sha": commit_sha,
                "new_commits": new_commits,
            })
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "_error", "error": f"{type(exc).__name__}: {exc}"})
        finally:
            if wt is not None and not req.keep_worktree:
                try:
                    await remove_worktree(repo_dir, wt)
                    yield _sse({"type": "_meta", "phase": "worktree_removed"})
                except Exception as exc:  # noqa: BLE001
                    yield _sse({"type": "_error", "error": f"cleanup: {exc}"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
