"""A45 (in-flight idle timeout) + A51 (--strict-mcp-config) agent guards."""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import claude_agent as ca  # noqa: E402


# ---- A45: in-flight readline timeout ----

def test_a45_idle_used_when_nothing_in_flight():
    # idle (600) < wall (2400) and no tool in flight → idle applies.
    assert ca._inflight_readline_timeout(0, 600, 2400) == 600


def test_a45_wall_used_when_tool_in_flight():
    # a tool is running (e.g. a long Bash gate / rate-limit backoff) → do NOT
    # idle-kill; fall back to the wall timeout. This is the BL-0006 fix.
    assert ca._inflight_readline_timeout(1, 600, 2400) == 2400
    assert ca._inflight_readline_timeout(3, 600, 2400) == 2400


def test_a45_idle_none_disables_idle():
    assert ca._inflight_readline_timeout(0, None, 2400) == 2400
    assert ca._inflight_readline_timeout(2, None, 2400) == 2400


def test_a45_idle_capped_by_wall():
    assert ca._inflight_readline_timeout(0, 5000, 2400) == 2400


def test_a45_loop_tracks_inflight_and_clears_on_result():
    """The stream loop must add tool_use ids to inflight and discard them on
    the matching tool_result, and feed inflight into the timeout helper."""
    src = inspect.getsource(ca.stream_agent_task)
    assert "inflight_tools" in src
    assert "inflight_tools.add" in src
    assert "inflight_tools.discard" in src
    assert "_inflight_readline_timeout(" in src


# ---- A51: agent MCP isolation ----

def test_a51_strict_mcp_config_passed():
    """Agents must run with --strict-mcp-config so they see ONLY the retrieval
    server, not the operator's global MCP fleet (Gmail/Drive/azure-devops/…)."""
    src = inspect.getsource(ca.stream_agent_task)
    assert "--strict-mcp-config" in src
    # and only alongside the retrieval --mcp-config we control
    assert "--mcp-config" in src
