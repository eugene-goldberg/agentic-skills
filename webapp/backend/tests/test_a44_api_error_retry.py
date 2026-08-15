"""Batch 2-2 (AUTONOMY_HARDENING_PLAN.md, C4 / A44 follow-up) — API errors
are retried as infrastructure failures, never burned as doctrine attempts.

Verifies:
- an attempt whose stream carries `phase=api_error` is re-spawned (same
  prompt) with an `infra_retry` event between attempts;
- a clean attempt spawns exactly once;
- exhaustion emits `api_error_exhausted` and stops;
- all 8 role-flow spawn sites route through the wrapper (source check),
  so no flow can silently regress to burning R10.1/R10.2 budget on
  API outages.
"""
from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import orchestrator as orch  # noqa: E402


def _mk_stub(fail_first_n: int, spawns: list):
    """stream_agent_task stub: first N spawns end with an api_error event."""

    async def stub(prompt, wt_path, *, timeout_seconds, trace=None,
                   min_pregrounding=0, **rk):
        n = len(spawns)
        spawns.append({"prompt": prompt, "min_pregrounding": min_pregrounding})
        yield {"type": "_meta", "phase": "spawn"}
        if n < fail_first_n:
            yield {"type": "_meta", "phase": "api_error",
                   "api_error_status": 400, "subtype": "error_during_execution"}
        else:
            yield {"type": "assistant", "message": {"content": []}}
        yield {"type": "_meta", "phase": "exit", "exit_code": 0}

    return stub


def _run(coro):
    return asyncio.run(coro)


def test_api_error_respawns_same_prompt_with_infra_retry_event(monkeypatch) -> None:
    monkeypatch.setattr(orch, "_API_ERROR_BACKOFF_S", (0, 0))
    spawns: list = []
    monkeypatch.setattr(orch, "stream_agent_task", _mk_stub(1, spawns))

    async def main():
        return [e async for e in orch._stream_role_attempt(
            "TASK", Path("/tmp"), timeout_seconds=60)]

    events = _run(main())
    assert len(spawns) == 2, "api_error attempt must be re-spawned"
    assert spawns[0]["prompt"] == spawns[1]["prompt"] == "TASK"
    retries = [e for e in events if e.get("phase") == "infra_retry"]
    assert len(retries) == 1
    assert retries[0]["kind"] == "api_error"
    # Events from both attempts pass through to the caller/trace.
    assert sum(1 for e in events if e.get("phase") == "spawn") == 2


def test_clean_attempt_spawns_exactly_once(monkeypatch) -> None:
    monkeypatch.setattr(orch, "_API_ERROR_BACKOFF_S", (0, 0))
    spawns: list = []
    monkeypatch.setattr(orch, "stream_agent_task", _mk_stub(0, spawns))

    async def main():
        return [e async for e in orch._stream_role_attempt(
            "TASK", Path("/tmp"), timeout_seconds=60, min_pregrounding=3)]

    events = _run(main())
    assert len(spawns) == 1
    assert spawns[0]["min_pregrounding"] == 3, "kwargs must pass through"
    assert not [e for e in events if e.get("phase") == "infra_retry"]


def test_persistent_api_error_exhausts_and_stops(monkeypatch) -> None:
    monkeypatch.setattr(orch, "_API_ERROR_BACKOFF_S", (0, 0))
    spawns: list = []
    monkeypatch.setattr(orch, "stream_agent_task", _mk_stub(99, spawns))

    async def main():
        return [e async for e in orch._stream_role_attempt(
            "TASK", Path("/tmp"), timeout_seconds=60)]

    events = _run(main())
    # 1 initial + len(backoff)=2 infra retries = 3 spawns, then exhausted.
    assert len(spawns) == 3
    kinds = [e.get("kind") for e in events if e.get("phase") == "infra_retry"]
    assert kinds == ["api_error", "api_error", "api_error_exhausted"]


def test_all_role_flow_spawn_sites_use_the_wrapper() -> None:
    """Source contract: _po_flow, _engineer_flow and _qa_or_scorer_flow must
    never call stream_agent_task directly — a direct call reintroduces the
    'API outage burns doctrine budget' failure mode."""
    for flow in (orch._po_flow, orch._engineer_flow, orch._qa_or_scorer_flow):
        src = inspect.getsource(flow)
        assert "stream_agent_task(" not in src, (
            f"{flow.__name__} bypasses _stream_role_attempt (A44)"
        )
        assert "_stream_role_attempt(" in src
