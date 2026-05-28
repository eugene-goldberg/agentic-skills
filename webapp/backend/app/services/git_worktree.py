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


async def create_worktree(repo_root: Path, task_id: str | None = None, *, base_ref: str | None = None) -> Worktree:
    """Create a fresh worktree off `base_ref` (default: current HEAD).

    For brownfield targets, callers pass `base_ref=<agent_branch>` from
    repo_config so all agent work forks off the dedicated branch instead of
    mutating `main` directly. If `base_ref` is None we preserve the original
    behavior (fork off whatever's currently checked out)."""
    task_id = task_id or uuid.uuid4().hex[:12]
    branch = f"agent/{task_id}"
    base = repo_root.parent / ".agent-worktrees" / task_id
    base.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["git", "worktree", "add", "-b", branch, str(base)]
    if base_ref:
        cmd.append(base_ref)
    code, _, err = await _run(cmd, cwd=repo_root)
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


async def fast_forward_target(repo_root: Path, branch: str, target_ref: str = "main") -> dict:
    """Fast-forward `target_ref` in the main checkout to include `branch`.

    Returns {ok, merged_sha?, error?, kind} where kind is one of
    "ff" (clean fast-forward), "noop" (already up to date),
    "non_ff" (branch diverged — manual merge required),
    "error" (git failed).
    """
    # Sanity: branch must exist
    code, out, _ = await _run(["git", "rev-parse", "--verify", branch], cwd=repo_root)
    if code != 0:
        return {"ok": False, "kind": "error", "error": f"branch {branch} not found"}
    branch_sha = out.strip()

    code, out, _ = await _run(["git", "rev-parse", "--verify", target_ref], cwd=repo_root)
    if code != 0:
        return {"ok": False, "kind": "error", "error": f"{target_ref} not found"}
    main_sha = out.strip()

    if branch_sha == main_sha:
        return {"ok": True, "kind": "noop", "merged_sha": main_sha}

    # Check is_ancestor(main, branch) → if not, this would be a non-FF merge
    code, _, _ = await _run(
        ["git", "merge-base", "--is-ancestor", main_sha, branch_sha], cwd=repo_root,
    )
    if code != 0:
        return {
            "ok": False,
            "kind": "non_ff",
            "error": f"{target_ref} ({main_sha[:8]}) is not an ancestor of {branch} ({branch_sha[:8]}); manual merge required",
            "branch_sha": branch_sha,
            "main_sha": main_sha,
        }

    # Refuse to fast-forward only if there are TRACKED modifications that
    # could collide with the merge. Untracked artifacts (graphify-out/, build
    # caches, etc.) are *mostly* harmless for a fast-forward, but git WILL
    # refuse to overwrite an untracked working-tree file with a tracked one
    # from the incoming branch — see A35 fix #2 below for the cleanup that
    # makes the "mostly" actually true.
    code, out, _ = await _run(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=repo_root,
    )
    if code == 0 and out.strip():
        return {
            "ok": False,
            "kind": "error",
            "error": "main checkout has modified tracked files; not merging",
            "status": out.strip()[:400],
        }

    # Make sure the main checkout has `target_ref` checked out — otherwise
    # `git merge --ff-only branch` would merge into whatever IS checked out
    # (often `main`), not into the configured target.
    code_cur, cur_out, _ = await _run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], cwd=repo_root)
    current_branch = cur_out.strip() if code_cur == 0 else None
    if current_branch != target_ref:
        code, _, err = await _run(["git", "checkout", target_ref], cwd=repo_root)
        if code != 0:
            return {"ok": False, "kind": "error", "error": f"could not checkout {target_ref}: {err.strip()}"}

    # A35 fix #2: pre-merge cleanup of known-disposable indexer artifacts.
    # The graphify indexer creates a symlink at `<repo>/graphify-out` pointing
    # at the per-repo cache under ~/.cache/agentic-skills/graphify/. The symlink
    # is regenerated on every indexer run and contains no commit-worthy data —
    # but if an agent branch's reindex created the symlink before its commit,
    # `git add -A` swept it in, and the resulting tracked entry collides with
    # the main checkout's untracked symlink on FF merge with:
    #   "error: The following untracked working tree files would be overwritten
    #    by merge: graphify-out"
    # This silently degraded documents_2 BL-0002 + BL-0007 (A37 forensic).
    # Remove the untracked symlink in the main checkout before merging; if the
    # next indexer run needs it, it'll regenerate. We only remove symlinks, not
    # regular files, to avoid touching anything genuinely committed.
    graphify_out = repo_root / "graphify-out"
    if graphify_out.is_symlink():
        try:
            graphify_out.unlink()
        except OSError:
            # If we can't remove it, fall through and let the merge surface
            # the original error — better diagnostic than swallowing here.
            pass

    code, _, err = await _run(["git", "merge", "--ff-only", branch], cwd=repo_root)
    if code != 0:
        return {"ok": False, "kind": "error", "error": f"git merge --ff-only failed: {err.strip()}"}
    return {"ok": True, "kind": "ff", "merged_sha": branch_sha, "target_ref": target_ref}


async def has_new_commits(wt: Worktree, base_ref: str = "HEAD~0") -> int:
    """Count commits the agent added beyond the worktree's base."""
    code, out, _ = await _run(
        ["git", "rev-list", "--count", f"{base_ref}..HEAD"], cwd=wt.path
    )
    try:
        return int(out.strip()) if code == 0 else 0
    except ValueError:
        return 0
