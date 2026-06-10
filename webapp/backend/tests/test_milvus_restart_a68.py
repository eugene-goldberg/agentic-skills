"""A68 — Milvus auto-restart must wait out the multi-minute segment reload.

Regression guard for run-20260610T040613Z-21a088, where a mid-sprint Milvus blip
escalated a BL because the old recovery used `docker start` + a fixed 30s poll +
60s cooldown — far too short for Milvus standalone's segment reload (~3.5 min
observed). The fix: `docker restart` + poll until it serves (default 300s), with
a cooldown that spans the reload window so retries POLL the in-progress reload
instead of thrashing it with another restart.
"""
import types

import pytest

from app.routers import projects


@pytest.fixture(autouse=True)
def _fast_and_reset(monkeypatch):
    # No real sleeping; reset the module-local restart clock per test.
    monkeypatch.setattr(projects.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(projects, "_MILVUS_LAST_RESTART_AT", 0.0, raising=False)


def _fake_run(calls, returncode=0, stderr=""):
    def _run(cmd, *a, **k):
        calls.append(cmd)
        return types.SimpleNamespace(returncode=returncode, stdout="", stderr=stderr)
    return _run


def test_restart_uses_docker_restart_and_waits_for_reload(monkeypatch):
    """Fresh recovery: issues `docker restart` and returns ok once the port
    serves a few polls later (the reload window)."""
    calls = []
    monkeypatch.setattr("subprocess.run", _fake_run(calls))
    monkeypatch.setattr(projects, "_MILVUS_RESTART_WAIT_S", 30.0)
    # Port down for two polls, then up (simulates reload finishing).
    seq = iter([False, False, True])
    monkeypatch.setattr(projects, "_milvus_port_reachable", lambda *a, **k: next(seq))

    ok, msg = projects._try_milvus_restart()

    assert ok is True, msg
    assert calls == [["docker", "restart", projects._MILVUS_CONTAINER]], calls
    assert "restarted" in msg


def test_cooldown_polls_reload_without_rerestarting(monkeypatch):
    """A call arriving while a prior restart is still reloading must POLL the
    in-progress reload, NOT issue another `docker restart` (the key A68 fix)."""
    calls = []
    monkeypatch.setattr("subprocess.run", _fake_run(calls))
    monkeypatch.setattr(projects, "_MILVUS_RESTART_WAIT_S", 30.0)
    monkeypatch.setattr(projects, "_MILVUS_RESTART_COOLDOWN_S", 30.0)
    # A restart happened "just now" → within cooldown.
    monkeypatch.setattr(projects, "_MILVUS_LAST_RESTART_AT", projects.time.time())
    seq = iter([False, True])
    monkeypatch.setattr(projects, "_milvus_port_reachable", lambda *a, **k: next(seq))

    ok, msg = projects._try_milvus_restart()

    assert ok is True, msg
    assert calls == [], "must not re-issue docker restart while mid-reload"
    assert "reachable" in msg


def test_docker_restart_nonzero_exit_fails(monkeypatch):
    calls = []
    monkeypatch.setattr("subprocess.run", _fake_run(calls, returncode=1, stderr="boom"))
    monkeypatch.setattr(projects, "_milvus_port_reachable", lambda *a, **k: False)

    ok, msg = projects._try_milvus_restart()

    assert ok is False
    assert "exit=1" in msg
    assert calls == [["docker", "restart", projects._MILVUS_CONTAINER]]


def test_port_never_serves_within_wait_fails(monkeypatch):
    """If the port never comes up within the (generous) wait, fail honestly —
    but only after actually waiting the configured window, not 30s."""
    calls = []
    monkeypatch.setattr("subprocess.run", _fake_run(calls))
    monkeypatch.setattr(projects, "_MILVUS_RESTART_WAIT_S", 0.0)  # deadline already past → instant
    monkeypatch.setattr(projects, "_milvus_port_reachable", lambda *a, **k: False)

    ok, msg = projects._try_milvus_restart()

    assert ok is False
    assert "still unreachable after" in msg
