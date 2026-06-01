"""Tests for A48 fix #2: volume_reaper.

Subprocess is mocked at asyncio.create_subprocess_exec so the tests
don't require docker on the runner. Behavior validated:
- Empty/None project name → no-op success
- Invalid project name → fail with reason
- Valid project + docker OK → parse volumes_removed + bytes_reclaimed
- Non-zero exit / FileNotFoundError / timeout → fail with reason
- reap_many runs sequentially and returns one result per project
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import volume_reaper as vr  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def _fake_proc(returncode: int, stdout: bytes = b"", stderr: bytes = b""):
    """Build an awaitable subprocess-like stub for the mocked path."""
    proc = SimpleNamespace(returncode=returncode)
    async def _communicate():
        return stdout, stderr
    proc.communicate = _communicate
    return proc


# ─── no-op + validation ───────────────────────────────────────────────────


def test_none_project_is_noop_success() -> None:
    r = _run(vr.reap(None))
    assert r.ok is True
    assert r.volumes_removed == 0
    assert r.bytes_reclaimed == 0
    assert "no compose_project" in r.reason


def test_empty_project_is_noop_success() -> None:
    r = _run(vr.reap(""))
    assert r.ok is True
    assert "no compose_project" in r.reason


def test_invalid_project_name_rejected() -> None:
    """Uppercase, semicolons, dashes-at-start — none are valid compose
    project names. Reaper must refuse without invoking docker."""
    for bad in (
        "UPPER",                # uppercase forbidden
        "with space",
        "with;semicolon",
        "-leading-dash",        # must start with alnum
        "with.dot",
    ):
        with patch("asyncio.create_subprocess_exec", side_effect=AssertionError(
                "must not be called"
        )):
            r = _run(vr.reap(bad))
        assert r.ok is False, bad
        assert "invalid project name" in r.reason, bad


# ─── docker subprocess path ───────────────────────────────────────────────


def test_successful_reap_parses_output() -> None:
    stdout = (
        b"Deleted Volumes:\n"
        b"abc123\n"
        b"def456\n"
        b"\n"
        b"Total reclaimed space: 1.5GB\n"
    )
    with patch(
        "asyncio.create_subprocess_exec",
        AsyncMock(return_value=_fake_proc(0, stdout=stdout)),
    ):
        r = _run(vr.reap("acceptance-run-foo"))
    assert r.ok is True
    assert r.project == "acceptance-run-foo"
    assert r.volumes_removed == 2
    assert r.bytes_reclaimed == int(1.5 * (1024 ** 3))
    assert r.reason == ""


def test_successful_reap_zero_volumes() -> None:
    stdout = b"Total reclaimed space: 0B\n"
    with patch(
        "asyncio.create_subprocess_exec",
        AsyncMock(return_value=_fake_proc(0, stdout=stdout)),
    ):
        r = _run(vr.reap("acceptance-run-foo"))
    assert r.ok is True
    assert r.volumes_removed == 0
    assert r.bytes_reclaimed == 0


def test_kb_mb_suffixes_parsed() -> None:
    cases = {
        b"Total reclaimed space: 500MB": 500 * (1024 ** 2),
        b"Total reclaimed space: 12kB": 12 * 1024,
        b"Total reclaimed space: 2TB": 2 * (1024 ** 4),
    }
    for stdout, expected in cases.items():
        with patch(
            "asyncio.create_subprocess_exec",
            AsyncMock(return_value=_fake_proc(0, stdout=stdout)),
        ):
            r = _run(vr.reap("p"))
        assert r.bytes_reclaimed == expected, stdout


def test_nonzero_exit_fails_with_reason() -> None:
    with patch(
        "asyncio.create_subprocess_exec",
        AsyncMock(return_value=_fake_proc(1, stderr=b"daemon offline")),
    ):
        r = _run(vr.reap("p"))
    assert r.ok is False
    assert "exit 1" in r.reason
    assert "daemon offline" in r.reason


def test_docker_not_on_path_fails() -> None:
    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=FileNotFoundError("no docker"),
    ):
        r = _run(vr.reap("p"))
    assert r.ok is False
    assert "not on PATH" in r.reason


def test_oserror_fails_with_reason() -> None:
    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=OSError("EPERM"),
    ):
        r = _run(vr.reap("p"))
    assert r.ok is False
    assert "OSError" in r.reason


def test_timeout_fails_with_reason() -> None:
    async def _hang():
        await asyncio.sleep(10)
    proc = SimpleNamespace(returncode=0, communicate=_hang)
    with patch(
        "asyncio.create_subprocess_exec",
        AsyncMock(return_value=proc),
    ):
        r = _run(vr.reap("p", timeout_s=0.05))
    assert r.ok is False
    assert "timed out" in r.reason


# ─── to_event ─────────────────────────────────────────────────────────────


def test_to_event_shape() -> None:
    stdout = b"Total reclaimed space: 250MB\n"
    with patch(
        "asyncio.create_subprocess_exec",
        AsyncMock(return_value=_fake_proc(0, stdout=stdout)),
    ):
        r = _run(vr.reap("p"))
    evt = r.to_event()
    for k in ("ok", "project", "volumes_removed", "bytes_reclaimed", "reason"):
        assert k in evt
    assert evt["bytes_reclaimed"] == 250 * (1024 ** 2)
    assert evt["project"] == "p"


# ─── reap_many ────────────────────────────────────────────────────────────


def test_reap_many_runs_each_project_once() -> None:
    stdouts = [
        b"Deleted Volumes:\na\nb\nTotal reclaimed space: 1GB\n",
        b"Total reclaimed space: 0B\n",
        b"Deleted Volumes:\nc\nTotal reclaimed space: 100MB\n",
    ]
    procs = [_fake_proc(0, stdout=s) for s in stdouts]
    call_count = {"n": 0}
    async def _create(*_a, **_kw):
        i = call_count["n"]
        call_count["n"] += 1
        return procs[i]
    with patch(
        "asyncio.create_subprocess_exec",
        new=_create,
    ):
        results = _run(vr.reap_many(["proj-a", "proj-b", "proj-c"]))
    assert len(results) == 3
    assert call_count["n"] == 3
    assert results[0].volumes_removed == 2
    assert results[1].volumes_removed == 0
    assert results[2].bytes_reclaimed == 100 * (1024 ** 2)


def test_reap_many_includes_noops_for_falsy_projects() -> None:
    """A None or '' entry in the list returns a noop result without
    invoking docker — used by callers that pass pre_proj/post_proj
    which may be None when run_id was unavailable."""
    stdout = b"Total reclaimed space: 0B\n"
    proc = _fake_proc(0, stdout=stdout)
    create_called = {"n": 0}
    async def _create(*_a, **_kw):
        create_called["n"] += 1
        return proc
    with patch(
        "asyncio.create_subprocess_exec",
        new=_create,
    ):
        results = _run(vr.reap_many([None, "proj-a", "", "proj-b"]))
    assert len(results) == 4
    assert results[0].ok is True and "no compose_project" in results[0].reason
    assert results[2].ok is True and "no compose_project" in results[2].reason
    # docker was called only for the two real names
    assert create_called["n"] == 2
