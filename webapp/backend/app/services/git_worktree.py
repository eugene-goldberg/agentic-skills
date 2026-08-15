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
    # A54 (Batch 2-4): the SHA the worktree was created at. The prior
    # `has_new_commits(wt, base_ref="HEAD~1")` idiom counted "HEAD has a
    # parent" (always ≥1), not "the agent committed" — masked by doctrine
    # no-op detection but semantically wrong.
    base_sha: str | None = None


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
    # A54: record the creation-time SHA so "did the agent commit?" is
    # answered against the true base, not HEAD~1.
    sha_code, sha_out, _ = await _run(["git", "rev-parse", "HEAD"], cwd=base)
    base_sha = sha_out.strip() if sha_code == 0 else None
    return Worktree(task_id=task_id, path=base, branch=branch, base_sha=base_sha)


async def _reap_worktree_compose_stacks(wt: Worktree) -> None:
    """A48 follow-up (2026-06-02): reap any docker compose stack the agent
    spawned inside the worktree before we remove the worktree itself.

    Engineers/QA/scorers/acceptance agents have Bash access to their
    worktree and may `docker compose up` to test code interactively
    (verified: BL-0006 financial-management engineer left
    `9b04804af277-db-1` running for 2h after sprint completion).
    Without this hook these stacks orphan: their postgres data volume
    counts against Docker.raw's 60 GB VM disk cap and eventually triggers
    ENOSPC mid-sprint.

    Two passes, defense in depth:

      1. Default-project-name reap: when an agent runs ``docker compose
         up`` without ``-p``, the project name defaults to the basename
         of the cwd — which is the worktree dir, which is the task_id.
         ``docker compose -p <task_id> down -v --remove-orphans`` is
         exact and cheap.

      2. Label-based safety net: if the agent picked an explicit ``-p``,
         step 1 misses it. Sweep for any container whose
         ``com.docker.compose.project.working_dir`` label is inside the
         worktree path and force-remove those.

    Best-effort throughout. Never raises — docker absence, bad container
    IDs, or a hung daemon must not block the git-worktree-remove path.
    """
    # Pass 1: default-project-name (task_id) reap.
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "-p", wt.task_id,
            "down", "-v", "--remove-orphans",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.communicate(), timeout=30.0)
    except Exception:
        pass
    # Pass 2: label-based safety net for explicit-`-p` cases.
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "ps", "-aq",
            "--filter",
            f"label=com.docker.compose.project.working_dir={wt.path}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        container_ids = [c for c in out.decode().split() if c]
        if container_ids:
            proc2 = await asyncio.create_subprocess_exec(
                "docker", "rm", "-fv", *container_ids,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc2.communicate(), timeout=30.0)
    except Exception:
        pass


async def remove_worktree(repo_root: Path, wt: Worktree, *, force: bool = True) -> None:
    """Detach and delete the worktree directory. Branch is left in place
    (caller may want to inspect or merge it).

    Reaps any docker compose stack spawned by the agent inside the
    worktree BEFORE removing the worktree dir, to prevent postgres data
    volumes accumulating into Docker.raw's 60 GB cap across a multi-BL
    sprint. See ``_reap_worktree_compose_stacks`` for the two-pass
    reaper detail.
    """
    await _reap_worktree_compose_stacks(wt)
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


async def find_bl_commits(repo_root: Path, bl_id: str, agent_branch: str,
                          *, base_ref: str | None = None) -> list[dict]:
    """Batch 4-2 (A50): commits on ``agent_branch`` belonging to ``bl_id``,
    oldest first. Subject conventions (verified against the harness):
    engineer commits start with ``BL-NNNN``; QA commits start with
    ``qa(BL-NNNN``. ``base_ref`` bounds the scan (default: whole branch).
    """
    range_spec = f"{base_ref}..{agent_branch}" if base_ref else agent_branch
    code, out, _ = await _run(
        ["git", "log", "--reverse", "--format=%H%x09%s", range_spec],
        cwd=repo_root,
    )
    if code != 0:
        return []
    hits: list[dict] = []
    for line in out.splitlines():
        if "\t" not in line:
            continue
        sha, subj = line.split("\t", 1)
        s = subj.strip()
        if s.startswith(bl_id) or s.startswith(f"qa({bl_id}"):
            hits.append({"sha": sha, "subject": s})
    return hits


async def revert_bl_span(repo_root: Path, bl_id: str, agent_branch: str,
                         *, base_ref: str | None = None) -> dict:
    """Batch 4-2 (A50): the orchestrator-owned backward remedy. Reverts a
    BL's commit span on ``agent_branch`` by adding revert commits (never
    history rewriting — the R13 boundary applies to the orchestrator's
    conscience too: refs move forward only).

    Mechanics: disposable worktree off ``agent_branch`` →
    ``git revert --no-edit`` each of the BL's commits newest-first → on
    any conflict, ``git revert --abort`` and return a structured error
    with ZERO mutation of ``agent_branch``. On success returns the revert
    branch name — the CALLER gates it (regression gate) and FF-merges,
    exactly like any agent branch. This function never touches
    ``agent_branch`` itself.

    Returns ``{ok, kind, branch?, reverted?, error?}`` with kind ∈
    ``reverted | no_commits | conflict | error``.
    """
    commits = await find_bl_commits(repo_root, bl_id, agent_branch, base_ref=base_ref)
    if not commits:
        return {"ok": False, "kind": "no_commits",
                "error": f"no commits for {bl_id} found on {agent_branch}"}
    wt = await create_worktree(repo_root, f"revert-{bl_id.lower()}-{uuid.uuid4().hex[:8]}",
                               base_ref=agent_branch)
    try:
        for c in reversed(commits):  # newest first
            code, _out, err = await _run(
                ["git", "revert", "--no-edit", c["sha"]], cwd=wt.path)
            if code != 0:
                await _run(["git", "revert", "--abort"], cwd=wt.path)
                return {
                    "ok": False, "kind": "conflict",
                    "error": (f"revert of {c['sha'][:8]} ({c['subject'][:80]}) "
                              f"conflicts: {err.strip()[:400]}"),
                    "commits": commits,
                }
        return {"ok": True, "kind": "reverted", "branch": wt.branch,
                "reverted": commits}
    finally:
        # Worktree dir is disposable; the branch (on success) survives for
        # the caller to gate + merge — same convention as agent worktrees.
        await remove_worktree(repo_root, wt)


async def has_new_commits(wt: Worktree, base_ref: str | None = None) -> int:
    """Count commits the agent added beyond the worktree's base.

    A54: defaults to the SHA recorded at worktree creation (`wt.base_sha`),
    which is the true base. An explicit `base_ref` still wins for callers
    with a different comparison point. Falls back to "HEAD~0" (count 0)
    when neither is available — the safe answer is "no new commits".
    """
    base = base_ref or wt.base_sha or "HEAD~0"
    code, out, _ = await _run(
        ["git", "rev-list", "--count", f"{base}..HEAD"], cwd=wt.path
    )
    try:
        return int(out.strip()) if code == 0 else 0
    except ValueError:
        return 0
