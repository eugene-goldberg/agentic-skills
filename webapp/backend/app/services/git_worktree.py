"""Per-task git worktree isolation.

Each agent task gets its own worktree + branch so concurrent runs don't
clobber each other and so a failed run is trivially abandoned.
"""
from __future__ import annotations

import asyncio
import shlex
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Worktree:
    task_id: str
    path: Path
    branch: str


async def _run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return proc.returncode or 0, out.decode(), err.decode()


async def create_worktree(repo_root: Path, task_id: str | None = None) -> Worktree:
    """Create a fresh worktree off the repo's current HEAD.

    Returns a Worktree handle. Caller is responsible for `remove_worktree`
    once done (success or failure)."""
    task_id = task_id or uuid.uuid4().hex[:12]
    branch = f"agent/{task_id}"
    base = repo_root.parent / ".agent-worktrees" / task_id
    base.parent.mkdir(parents=True, exist_ok=True)
    code, _, err = await _run(
        ["git", "worktree", "add", "-b", branch, str(base)],
        cwd=repo_root,
    )
    if code != 0:
        raise RuntimeError(f"git worktree add failed: {err}")
    return Worktree(task_id=task_id, path=base, branch=branch)


async def remove_worktree(repo_root: Path, wt: Worktree, *, force: bool = True) -> None:
    """Detach and delete the worktree directory. Branch is left in place
    (caller may want to inspect or merge it)."""
    args = ["git", "worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(wt.path))
    await _run(args, cwd=repo_root)


async def get_commit_sha(wt: Worktree) -> str | None:
    code, out, _ = await _run(["git", "rev-parse", "HEAD"], cwd=wt.path)
    return out.strip() if code == 0 else None


async def has_new_commits(wt: Worktree, base_ref: str = "HEAD~0") -> int:
    """Count commits the agent added beyond the worktree's base."""
    code, out, _ = await _run(
        ["git", "rev-list", "--count", f"{base_ref}..HEAD"], cwd=wt.path
    )
    try:
        return int(out.strip()) if code == 0 else 0
    except ValueError:
        return 0
