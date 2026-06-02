"""A48 follow-up (2026-06-02): orchestrator shutdown handler that drains
compose stacks the orchestrator owns when uvicorn receives SIGTERM.

Covers ``app.main._reap_orchestrator_compose_stacks``: scans
``docker ps -a`` for compose-project labels matching the orchestrator's
own prefixes (``agentic-skills-*`` for gates, ``acceptance-*`` for
acceptance) and issues ``docker compose -p <project> down -v
--remove-orphans`` for each.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import main as main_mod  # noqa: E402


class _FakeProc:
    def __init__(self, stdout: bytes = b"", returncode: int = 0):
        self._stdout = stdout
        self.returncode = returncode

    async def communicate(self):
        return self._stdout, b""


def _make_recorder(ps_output: bytes):
    """Captures all subprocess invocations and returns scripted
    output for the first call (the docker ps scan)."""
    calls: list[tuple[str, ...]] = []
    first = [True]

    async def factory(*args, **_kwargs):
        calls.append(args)
        if first[0]:
            first[0] = False
            return _FakeProc(stdout=ps_output)
        return _FakeProc()

    return calls, factory


def test_shutdown_reaps_orchestrator_project_names():
    """`docker ps` lists two orchestrator-owned projects and one foreign
    project. The reaper must `compose -p <project> down -v` for each of
    the two orchestrator projects and skip the foreign one."""
    ps_out = b"""agentic-skills-20260601t120000z-aaa
acceptance-run-20260601t130000z-bbb
some-user-app-stack
""".strip()
    calls, factory = _make_recorder(ps_out)
    with patch.object(asyncio, "create_subprocess_exec", side_effect=factory):
        asyncio.run(main_mod._reap_orchestrator_compose_stacks())
    down_projects = [
        c[3] for c in calls
        if c[:3] == ("docker", "compose", "-p") and len(c) > 3
    ]
    assert "agentic-skills-20260601t120000z-aaa" in down_projects
    assert "acceptance-run-20260601t130000z-bbb" in down_projects
    assert "some-user-app-stack" not in down_projects


def test_shutdown_handles_empty_docker_ps():
    """Empty docker ps output → no down invocations, no error."""
    calls, factory = _make_recorder(b"")
    with patch.object(asyncio, "create_subprocess_exec", side_effect=factory):
        asyncio.run(main_mod._reap_orchestrator_compose_stacks())
    # Only the initial `docker ps` call should have been made.
    assert len(calls) == 1
    assert calls[0][:2] == ("docker", "ps")


def test_shutdown_silent_on_docker_absent():
    """If docker binary is missing entirely, reaper must not raise.
    Uvicorn shutdown is the last thing that should ever blow up."""
    async def boom(*args, **kwargs):
        raise FileNotFoundError("docker not installed")

    with patch.object(asyncio, "create_subprocess_exec", side_effect=boom):
        # Should complete cleanly.
        asyncio.run(main_mod._reap_orchestrator_compose_stacks())


def test_shutdown_deduplicates_repeated_projects():
    """`docker ps -a` may list multiple containers per project (db-1,
    backend-1, etc.). The reaper should down each PROJECT once, not
    per-container."""
    ps_out = b"""agentic-skills-runxyz-pre-aaa
agentic-skills-runxyz-pre-aaa
agentic-skills-runxyz-pre-aaa
""".strip()
    calls, factory = _make_recorder(ps_out)
    with patch.object(asyncio, "create_subprocess_exec", side_effect=factory):
        asyncio.run(main_mod._reap_orchestrator_compose_stacks())
    down_projects = [
        c[3] for c in calls
        if c[:3] == ("docker", "compose", "-p") and len(c) > 3
    ]
    assert down_projects == ["agentic-skills-runxyz-pre-aaa"]
