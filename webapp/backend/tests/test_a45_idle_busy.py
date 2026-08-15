"""Batch 2-3 (AUTONOMY_HARDENING_PLAN.md, C4 / A45) — the idle-timeout
distinguishes *busy* (tool in flight) from *silent* (hung).

The BL-0014 incident: an engineer with a verified fix blocked silently on
a long child process and was killed by the 600s idle timeout — a correct
fix thrown away by a liveness heuristic. These tests run the REAL
stream_agent_task loop against a fake `claude` CLI (via $CLAUDE_BIN):

1. tool_use emitted, then silence longer than idle_timeout, then
   tool_result → agent SURVIVES (idle clock suspended while busy);
2. bare silence longer than idle_timeout → agent still killed (B5
   behavior preserved for genuine hangs);
3. tool in flight but wall budget exceeded → killed as wall_timeout
   (busy is not immortal).
"""
from __future__ import annotations

import asyncio
import os
import stat
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.claude_agent import stream_agent_task  # noqa: E402

FAKE_CLI = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json, os, sys, time

    def emit(obj):
        sys.stdout.write(json.dumps(obj) + "\\n")
        sys.stdout.flush()

    mode = os.environ.get("FAKE_CLAUDE_MODE", "busy")
    if mode == "busy":
        emit({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "tu1", "name": "Bash",
             "input": {"command": "pytest"}}]}})
        time.sleep(6.5)  # longer than idle_timeout=4, shorter than wall
        emit({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "tu1"}]}})
        emit({"type": "result", "is_error": False, "result": "done"})
    elif mode == "silent":
        time.sleep(60)   # no tool in flight — genuine hang
    elif mode == "busy_forever":
        emit({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "tu1", "name": "Bash",
             "input": {"command": "sleep"}}]}})
        time.sleep(60)   # tool never completes — wall must bound it
""")


def _setup(tmp_path: Path, monkeypatch, mode: str) -> Path:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    cli = tmp_path / "fake_claude.py"
    cli.write_text(FAKE_CLI)
    cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("CLAUDE_BIN", str(cli))
    monkeypatch.setenv("FAKE_CLAUDE_MODE", mode)
    return repo


def _collect(repo: Path, *, idle: int, wall: int) -> list[dict]:
    async def main():
        return [e async for e in stream_agent_task(
            "task", repo, timeout_seconds=wall, idle_timeout=idle)]
    return asyncio.run(main())


def test_busy_agent_survives_idle_silence(tmp_path, monkeypatch) -> None:
    """tool_use in flight → 6.5s of stream silence with idle_timeout=4
    must NOT kill the agent (the A45 false positive)."""
    repo = _setup(tmp_path, monkeypatch, "busy")
    events = _collect(repo, idle=4, wall=40)
    kinds = [e.get("kind") for e in events if e.get("type") == "_error"]
    assert "idle_timeout" not in kinds, (
        "agent with a tool in flight was killed as idle (A45 regression)"
    )
    phases = [e.get("phase") for e in events if e.get("type") == "_meta"]
    assert "exit" in phases
    exit_evt = next(e for e in events
                    if e.get("type") == "_meta" and e.get("phase") == "exit")
    assert exit_evt["exit_code"] == 0, "fake agent should complete normally"
    # The tool_result and terminal result made it through post-silence.
    assert any(e.get("type") == "result" for e in events)


def test_genuinely_silent_agent_still_killed_as_idle(tmp_path, monkeypatch) -> None:
    """No tool in flight + silence → B5 idle kill preserved."""
    repo = _setup(tmp_path, monkeypatch, "silent")
    events = _collect(repo, idle=4, wall=40)
    errors = [e for e in events if e.get("type") == "_error"]
    assert errors, "silent agent must be killed"
    assert errors[0]["kind"] == "idle_timeout"
    assert errors[0]["in_flight_tools"] == 0


def test_busy_agent_is_still_bounded_by_wall_timeout(tmp_path, monkeypatch) -> None:
    """A tool in flight suspends the idle clock, not the wall clock."""
    repo = _setup(tmp_path, monkeypatch, "busy_forever")
    events = _collect(repo, idle=4, wall=9)
    errors = [e for e in events if e.get("type") == "_error"]
    assert errors, "wall timeout must still bound a busy agent"
    assert errors[0]["kind"] == "wall_timeout"
    assert errors[0]["in_flight_tools"] == 1
