"""Tests for #3 wedge-proof (A45-coupled): the orchestrator must ALWAYS emit a
terminal event, even when a flow raises before yielding its outcome sentinel.

Before this fix the outer `try` in `run_brief` had only a `finally` (which
cannot `yield` during aclose — PEP 525), so any unhandled exception in the
sprint body propagated out of `run_brief` and the SSE stream ended with NO
terminal event — the 0-procs-no-terminal wedge that only the End-Sprint button
could clear (BL-0006, search_and_discovery_2, 2026-06-04).

Two layers are verified:
  A. engineer wrap   — `_engineer_flow` raising → `engineer_unmerged` + the
                       standard not-merged path (honors stop_on_failure).
  B. outer backstop  — any other sprint-body raise → terminal `aborted` with
                       `error_type`.
"""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app.services.orchestrator as orch  # noqa: E402


class _Item:
    def __init__(self, id: str, title: str) -> None:
        self.id = id
        self.title = title
        self.meta: dict = {}


def _noop_indexers(*a, **k):
    async def _gen():
        if False:
            yield {}
    return _gen()


def _raising_indexers(*a, **k):
    async def _gen():
        raise RuntimeError("indexer boom")
        yield {}  # pragma: no cover
    return _gen()


def _drive(monkeypatch, *, engineer_flow, indexers, stop_on_failure=True) -> list[dict]:
    """Run run_brief with all heavy collaborators mocked; return event list."""
    monkeypatch.setattr(orch, "_run_indexers", indexers)
    monkeypatch.setattr(orch, "_engineer_flow", engineer_flow)
    monkeypatch.setattr(orch, "_dep_order", lambda items: items)
    monkeypatch.setattr(orch.backlog_svc, "find_backlog", lambda *a, **k: Path("/tmp/FAKE_BACKLOG.md"))
    monkeypatch.setattr(orch.backlog_svc, "parse_file", lambda *a, **k: [_Item("BL-0001", "only bl")])
    monkeypatch.setattr(orch.repo_config_svc, "load",
                        lambda *a, **k: types.SimpleNamespace(agent_branch="agentic-skills-work"))
    monkeypatch.setattr(orch, "_qa_commit_landed", lambda *a, **k: False)
    # checkpoints / archival are advisory disk IO — neutralize for hermeticity.
    monkeypatch.setattr(orch.run_state_svc, "write_checkpoint", lambda **k: None)
    monkeypatch.setattr(orch.run_state_svc, "mark_terminated", lambda *a, **k: None)
    monkeypatch.setattr(orch, "_archive_traces_since", lambda *a, **k: None)

    async def _collect() -> list[dict]:
        out: list[dict] = []
        async for ev in orch.run_brief(
            repo_dir=Path("/tmp/fake-repo"),
            repo_name="fake-repo",
            brief="brief",
            project_name="proj",
            retrieval_kwargs_builder=lambda *a, **k: {},
            skip_po=True,
            stop_on_failure=stop_on_failure,
            run_doctrine_meta=False,
            run_acceptance=False,
        ):
            out.append(ev)
        return out

    return asyncio.run(_collect())


def _phases(events: list[dict]) -> list[str]:
    # Events are emitted with an `orchestrator.` prefix; compare on suffix.
    return [str(e.get("phase", "")).removeprefix("orchestrator.") for e in events]


def _suffix(events: list[dict], suffix: str) -> list[dict]:
    return [e for e in events if str(e.get("phase", "")).removeprefix("orchestrator.") == suffix]


# ── Layer A: engineer flow raises ─────────────────────────────────────────


def test_engineer_raise_yields_terminal_not_wedge(monkeypatch) -> None:
    def _raising_engineer(*a, **k):
        async def _gen():
            raise RuntimeError("idle-kill simulated mid-await")
            yield {}  # pragma: no cover
        return _gen()

    events = _drive(monkeypatch, engineer_flow=_raising_engineer, indexers=_noop_indexers)
    phases = _phases(events)

    # The exception is surfaced, NOT swallowed silently.
    assert "engineer.error" in phases
    # The standard not-merged path fired a terminal bl.done(engineer_unmerged).
    bl_done = _suffix(events, "bl.done")
    assert bl_done and bl_done[-1].get("outcome") == "engineer_unmerged"
    # stop_on_failure=True → the sprint terminates with `aborted` (a terminal
    # event), never a silent 0-procs wedge.
    assert "aborted" in phases


def test_engineer_raise_continues_when_not_stop_on_failure(monkeypatch) -> None:
    def _raising_engineer(*a, **k):
        async def _gen():
            raise RuntimeError("boom")
            yield {}  # pragma: no cover
        return _gen()

    events = _drive(monkeypatch, engineer_flow=_raising_engineer,
                    indexers=_noop_indexers, stop_on_failure=False)
    phases = _phases(events)
    # engineer_unmerged recorded, and with the single BL exhausted the run
    # proceeds to a clean terminal (sprint_complete) rather than wedging.
    assert any(e.get("outcome") == "engineer_unmerged" for e in _suffix(events, "bl.done"))
    assert "sprint_complete" in phases


# ── Layer B: outer backstop on any other sprint-body raise ─────────────────


def test_indexer_raise_hits_outer_backstop(monkeypatch) -> None:
    def _ok_engineer(*a, **k):
        async def _gen():
            yield {"_orchestrator_outcome": True, "role": "engineer",
                   "bl_id": "BL-0001", "merged": True, "no_op": False}
        return _gen()

    events = _drive(monkeypatch, engineer_flow=_ok_engineer, indexers=_raising_indexers)
    aborted = _suffix(events, "aborted")
    assert aborted, "outer backstop must emit a terminal aborted event"
    assert aborted[-1].get("error_type") == "RuntimeError"
    assert "unhandled orchestrator error" in aborted[-1].get("reason", "")
