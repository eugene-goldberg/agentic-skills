"""Real-git tests for the wave-concurrency barrier-assembly primitive.

PROPOSAL_WAVE_CONCURRENCY.md Strategy A, step 3. `merge_branch_into_target` does a
real 3-way merge so a wave's per-BL branches (all forked from the SAME wave-base SHA)
can be assembled onto the trunk in fixed order. Exercises real `git merge`:
  - disjoint per-BL branches assemble cleanly (the R21-contract common case),
  - overlapping edits report `conflict` and ABORT (trunk left clean -> no-abort route).
Uses `asyncio.run` + the git-2.25-safe init (no `init -b`).
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.git_worktree import merge_branch_into_target  # noqa: E402


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _porcelain(repo: Path) -> str:
    return subprocess.run(["git", "status", "--porcelain"], cwd=repo,
                          capture_output=True, text=True).stdout.strip()


def _init_repo(tmp_path: Path, base_files: dict) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    for rel, body in base_files.items():
        (repo / rel).write_text(body)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def _branch_commit(repo: Path, branch: str, base: str, files: dict) -> None:
    # fork `branch` off `base`, commit `files`, return to `base` (the trunk)
    _git(repo, "checkout", "-q", base)
    _git(repo, "checkout", "-q", "-b", branch)
    for rel, body in files.items():
        (repo / rel).write_text(body)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"{branch} work")
    _git(repo, "checkout", "-q", base)


def test_disjoint_branches_assemble_cleanly(tmp_path):
    repo = _init_repo(tmp_path, {"README.md": "base\n"})
    # two BLs forked from the SAME base, touching disjoint files
    _branch_commit(repo, "agentwork/bl1", "main", {"a.txt": "A\n"})
    _branch_commit(repo, "agentwork/bl2", "main", {"b.txt": "B\n"})

    async def _run():
        r1 = await merge_branch_into_target(repo, "agentwork/bl1", "main")
        r2 = await merge_branch_into_target(repo, "agentwork/bl2", "main")
        return r1, r2

    r1, r2 = asyncio.run(_run())
    assert r1["ok"] and r1["kind"] == "merged", r1
    # bl2 forked from base (not from bl1's tip) -> genuinely non-FF -> 3-way merge
    assert r2["ok"] and r2["kind"] == "merged", r2
    assert (repo / "a.txt").exists() and (repo / "b.txt").exists()
    assert _porcelain(repo) == ""


def test_conflicting_branches_report_conflict_and_abort(tmp_path):
    repo = _init_repo(tmp_path, {"README.md": "base\n", "shared.txt": "base\n"})
    # two BLs editing the SAME line of the same file -> overlapping
    _branch_commit(repo, "agentwork/c1", "main", {"shared.txt": "v1\n"})
    _branch_commit(repo, "agentwork/c2", "main", {"shared.txt": "v2\n"})

    async def _run():
        r1 = await merge_branch_into_target(repo, "agentwork/c1", "main")
        r2 = await merge_branch_into_target(repo, "agentwork/c2", "main")
        return r1, r2

    r1, r2 = asyncio.run(_run())
    assert r1["ok"] and r1["kind"] == "merged", r1
    # c2 overlaps c1 -> conflict, merge aborted, trunk left clean
    assert (not r2["ok"]) and r2["kind"] == "conflict", r2
    assert "shared.txt" in r2["conflict_files"], r2
    assert (repo / "shared.txt").read_text().strip() == "v1"  # c1's value survives
    assert _porcelain(repo) == ""  # merge --abort left the trunk clean


def test_noop_when_already_merged(tmp_path):
    repo = _init_repo(tmp_path, {"README.md": "base\n"})
    _branch_commit(repo, "agentwork/x", "main", {"x.txt": "X\n"})

    async def _run():
        first = await merge_branch_into_target(repo, "agentwork/x", "main")
        again = await merge_branch_into_target(repo, "agentwork/x", "main")
        return first, again

    first, again = asyncio.run(_run())
    assert first["ok"] and first["kind"] == "merged"
    assert again["ok"] and again["kind"] == "noop", again
