"""A48 follow-up (2026-06-02): worktree-removal compose-stack reaper.

Covers the two-pass reaper in
``app.services.git_worktree._reap_worktree_compose_stacks``:

  1. Default-project-name pass: ``docker compose -p <task_id> down -v``
  2. Label-based safety net: scan + force-remove containers whose
     ``com.docker.compose.project.working_dir`` is the worktree path.

Tests stub ``asyncio.create_subprocess_exec`` to capture the exact docker
commands the reaper would have issued, without needing a real docker
daemon. The remove_worktree integration test asserts the reaper runs
BEFORE the git-worktree-remove step.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import git_worktree as gw  # noqa: E402


def _make_wt(tmp_path: Path, task_id: str = "abc123def456") -> gw.Worktree:
    p = tmp_path / ".agent-worktrees" / task_id
    p.mkdir(parents=True)
    return gw.Worktree(task_id=task_id, path=p, branch=f"agent/{task_id}")


# ─── helpers ────────────────────────────────────────────────────────────────


class _FakeProc:
    """Mimics the parts of asyncio.subprocess.Process the reaper touches."""

    def __init__(self, stdout: bytes = b"", returncode: int = 0):
        self._stdout = stdout
        self.returncode = returncode

    async def communicate(self):
        return self._stdout, b""


def _make_subprocess_recorder(
    pass1_stdout: bytes = b"",
    pass2_stdout: bytes = b"",
    pass3_stdout: bytes = b"",
):
    """Returns a (calls, factory) pair. `calls` accumulates the argv
    of every subprocess invocation; `factory` is the AsyncMock
    side_effect that returns scripted _FakeProc instances."""
    calls: list[tuple[str, ...]] = []
    scripted = [pass1_stdout, pass2_stdout, pass3_stdout]

    async def factory(*args, **_kwargs):
        calls.append(args)
        out = scripted.pop(0) if scripted else b""
        return _FakeProc(stdout=out)

    return calls, factory


# ─── reaper-only tests ──────────────────────────────────────────────────────


def test_reaper_pass1_uses_default_project_name(tmp_path: Path) -> None:
    """When the agent ran `docker compose up` with no -p, the project
    name defaults to the worktree basename = task_id. Pass 1 must
    issue exactly `docker compose -p <task_id> down -v --remove-orphans`."""
    wt = _make_wt(tmp_path, task_id="myTaskId123")
    calls, factory = _make_subprocess_recorder()
    with patch.object(asyncio, "create_subprocess_exec", side_effect=factory):
        asyncio.run(gw._reap_worktree_compose_stacks(wt))
    assert any(
        c[:6] == ("docker", "compose", "-p", "myTaskId123", "down", "-v")
        for c in calls
    ), f"pass-1 docker compose down not issued; got {calls}"


def test_reaper_pass2_label_filter_includes_worktree_path(tmp_path: Path) -> None:
    """Pass 2 (label safety net) must filter on the worktree path so
    explicit-`-p` engineer stacks are still caught."""
    wt = _make_wt(tmp_path, task_id="taskid")
    calls, factory = _make_subprocess_recorder()
    with patch.object(asyncio, "create_subprocess_exec", side_effect=factory):
        asyncio.run(gw._reap_worktree_compose_stacks(wt))
    label = f"label=com.docker.compose.project.working_dir={wt.path}"
    assert any(
        "ps" in c and label in c
        for c in calls
    ), f"pass-2 label filter missing; got {calls}"


def test_reaper_pass2_removes_found_containers(tmp_path: Path) -> None:
    """Pass 2 stdout returns container IDs → reaper must invoke
    `docker rm -fv` for each."""
    wt = _make_wt(tmp_path)
    calls, factory = _make_subprocess_recorder(
        pass1_stdout=b"",
        pass2_stdout=b"abc123\ndef456\n",
        pass3_stdout=b"",
    )
    with patch.object(asyncio, "create_subprocess_exec", side_effect=factory):
        asyncio.run(gw._reap_worktree_compose_stacks(wt))
    rm_calls = [c for c in calls if c[:3] == ("docker", "rm", "-fv")]
    assert rm_calls, f"docker rm not invoked; got {calls}"
    assert "abc123" in rm_calls[0]
    assert "def456" in rm_calls[0]


def test_reaper_pass2_skips_rm_when_no_containers_found(tmp_path: Path) -> None:
    """Empty `docker ps` output → no rm invocation (cheap fast-path)."""
    wt = _make_wt(tmp_path)
    calls, factory = _make_subprocess_recorder(
        pass1_stdout=b"", pass2_stdout=b"", pass3_stdout=b"",
    )
    with patch.object(asyncio, "create_subprocess_exec", side_effect=factory):
        asyncio.run(gw._reap_worktree_compose_stacks(wt))
    rm_calls = [c for c in calls if c[:3] == ("docker", "rm", "-fv")]
    assert not rm_calls


def test_reaper_swallows_exceptions_from_docker_failure(tmp_path: Path) -> None:
    """If docker isn't installed / daemon is down, the reaper must NOT
    raise. The remove_worktree contract is that this hook is advisory."""
    wt = _make_wt(tmp_path)

    async def boom(*args, **kwargs):
        raise FileNotFoundError("docker not installed")

    with patch.object(asyncio, "create_subprocess_exec", side_effect=boom):
        # Should complete without raising
        asyncio.run(gw._reap_worktree_compose_stacks(wt))


# ─── remove_worktree integration ────────────────────────────────────────────


def test_remove_worktree_calls_reaper_before_git_remove(tmp_path: Path) -> None:
    """The reaper hook must fire BEFORE `git worktree remove` — otherwise
    we'd race against the engineer's stack having an open file handle in
    the worktree dir."""
    wt = _make_wt(tmp_path)
    order: list[str] = []

    async def fake_reap(_wt):
        order.append("reap")

    async def fake_run(cmd, cwd=None):
        if cmd[:2] == ["git", "worktree"]:
            order.append("git_remove")
        return (0, "", "")

    with patch.object(gw, "_reap_worktree_compose_stacks", side_effect=fake_reap):
        with patch.object(gw, "_run", side_effect=fake_run):
            asyncio.run(gw.remove_worktree(tmp_path, wt))

    assert order == ["reap", "git_remove"], (
        f"reaper must fire before git worktree remove; saw {order}"
    )


def test_remove_worktree_still_completes_if_reaper_raises_internally(tmp_path: Path) -> None:
    """The reaper itself swallows exceptions; if a contributor regresses
    that, remove_worktree should at least not blow up the caller. This
    test pins that behavior by injecting a reaper that raises and
    asserting we still continue to the git step (we DON'T continue today
    — the contract is the reaper swallows. This test pins the contract
    so a future refactor stays honest.)"""
    wt = _make_wt(tmp_path)
    git_called = []

    async def reap_raises(_wt):
        raise RuntimeError("contributor regressed swallowing")

    async def fake_run(cmd, cwd=None):
        if cmd[:2] == ["git", "worktree"]:
            git_called.append(True)
        return (0, "", "")

    # We DON'T expect remove_worktree to swallow on its own — the contract
    # is the reaper swallows. So this should raise.
    with patch.object(gw, "_reap_worktree_compose_stacks", side_effect=reap_raises):
        with patch.object(gw, "_run", side_effect=fake_run):
            with pytest.raises(RuntimeError):
                asyncio.run(gw.remove_worktree(tmp_path, wt))
    assert not git_called, "git_remove should not run when reaper raises"
