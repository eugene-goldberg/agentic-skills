"""Live/integration proof for the acceptance-reround worktree-branch fix.

run-20260614T143621Z-0b7c91 (order-fulfillment, wave_execution=True): the
live-acceptance loop found 2 UI product_bugs, dispatched+merged fixes, then the
round-2 re-verify died at ``git worktree add -b agent/accept-<run_id>`` because
round 1 already created that branch -> acceptance.skipped(worktree_failed) ->
acceptance.loop.escalated with integrity_ok=false (the 2 fixes merged but were
never live-confirmed).

Unlike the pure-naming unit tests in test_acceptance_loop.py, these exercise the
REAL ``create_worktree`` (an actual ``git worktree add -b`` against a temp repo)
to (a) reproduce the original branch collision and (b) prove the round-unique
task id from ``_accept_worktree_task_id`` lets a reround create its worktree
without colliding with the prior round's still-existing branch.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import git_worktree as gw  # noqa: E402
from app.services.orchestrator import _accept_worktree_task_id as wtid  # noqa: E402


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _init_repo(tmp_path: Path) -> Path:
    # git-2.25-safe init (no `init -b`; symbolic-ref instead) — matches the
    # remote crew host's git and the a46990e fixture-portability fix.
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "README.md").write_text("baseline\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "baseline")
    return repo


def test_reround_worktree_no_collision_real_git(tmp_path):
    """Real `git worktree add`: round-1 reuse collides; round-2 unique name does not."""
    repo = _init_repo(tmp_path)
    rid = "run-20260614T143621Z-0b7c91"

    async def _run():
        created = []
        try:
            # Round 1 — the historical name; succeeds and creates the branch.
            wt1 = await gw.create_worktree(repo, task_id=wtid(rid, 1), base_ref="main")
            created.append(wt1)
            assert wt1.branch == f"agent/accept-{rid}"

            # Reproduce the ORIGINAL BUG: re-creating the round-1 name collides
            # exactly as the reround did (real `git worktree add -b` failure).
            raised = False
            try:
                await gw.create_worktree(repo, task_id=wtid(rid, 1), base_ref="main")
            except RuntimeError as exc:
                raised = True
                assert "already exists" in str(exc) or "worktree add failed" in str(exc)
            assert raised, "round-1 branch name must collide on reuse (the bug)"

            # THE FIX: round 2 uses a round-unique task id -> no collision.
            wt2 = await gw.create_worktree(repo, task_id=wtid(rid, 2), base_ref="main")
            created.append(wt2)
            assert wt2.branch == f"agent/accept-{rid}-r2"
            assert wt2.branch != wt1.branch
            assert wt1.path.exists() and wt2.path.exists()
        finally:
            for wt in created:
                try:
                    await gw.remove_worktree(repo, wt, force=True)
                except Exception:
                    pass

    asyncio.run(_run())
