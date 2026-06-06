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
    # No-abort doctrine: the not-merged engineer escalates with a dossier.
    bl_done = _suffix(events, "bl.done")
    assert bl_done and bl_done[-1].get("outcome") == "engineer_escalated"
    # stop_on_failure=True → the sprint terminates with `escalated` (Option A,
    # a terminal event with dossier), never a silent wedge and never a routine
    # abort.
    assert "escalated" in phases
    assert "aborted" not in phases


def test_engineer_raise_continues_when_not_stop_on_failure(monkeypatch) -> None:
    def _raising_engineer(*a, **k):
        async def _gen():
            raise RuntimeError("boom")
            yield {}  # pragma: no cover
        return _gen()

    events = _drive(monkeypatch, engineer_flow=_raising_engineer,
                    indexers=_noop_indexers, stop_on_failure=False)
    phases = _phases(events)
    # engineer_escalated recorded, and with the single BL exhausted the run
    # proceeds to a clean terminal (sprint_complete) rather than wedging.
    assert any(e.get("outcome") == "engineer_escalated" for e in _suffix(events, "bl.done"))
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


# ── A53: auto-merge atomicity — rollback engineer merge on BL-abort ──────────


def test_qa_merge_fail_rolls_back_engineer_merge(monkeypatch) -> None:
    """Engineer merged on its green gate; QA then fails to merge under
    stop_on_failure → the orchestrator must reset the trunk back to the
    pre-BL SHA so the aborted BL leaves no QA-unvalidated engineer code."""
    def _ok_engineer(*a, **k):
        async def _gen():
            yield {"_orchestrator_outcome": True, "role": "engineer",
                   "bl_id": "BL-0001", "merged": True, "no_op": False}
        return _gen()

    def _qa_doc_ok_no_merge(*a, **k):
        async def _gen():
            yield {"_orchestrator_outcome": True, "role": "qa",
                   "bl_id": "BL-0001", "merged": False, "doctrine_ok": True}
        return _gen()

    calls: dict = {}

    async def _fake_rev_parse(repo, ref):
        return "PRE_BL_SHA_abc123"

    async def _fake_reset(repo, target_ref, sha):
        calls["reset"] = (target_ref, sha)
        return {"ok": True, "kind": "reset", "to_sha": sha}

    monkeypatch.setattr(orch, "_qa_or_scorer_flow", _qa_doc_ok_no_merge)
    monkeypatch.setattr(orch, "rev_parse", _fake_rev_parse)
    monkeypatch.setattr(orch, "reset_target_to", _fake_reset)

    events = _drive(monkeypatch, engineer_flow=_ok_engineer, indexers=_noop_indexers)
    phases = _phases(events)

    assert "qa_merge_failed" in phases
    assert "bl.rolled_back" in phases
    # No-abort doctrine: escalate (with dossier), not abort.
    assert "escalated" in phases
    assert "aborted" not in phases
    # The trunk was reset to the pre-BL SHA on the configured agent branch.
    assert calls.get("reset") == ("agentic-skills-work", "PRE_BL_SHA_abc123")
    # The BL outcome is relabelled rolled_back (not merged_no_qa).
    bl_done = _suffix(events, "bl.done")
    assert bl_done and bl_done[-1].get("outcome") == "rolled_back"


def test_qa_merge_fail_no_rollback_when_continue(monkeypatch) -> None:
    """With stop_on_failure=False the engineer merge is intentionally kept
    (best-effort continue) — no rollback, outcome stays merged_no_qa."""
    def _ok_engineer(*a, **k):
        async def _gen():
            yield {"_orchestrator_outcome": True, "role": "engineer",
                   "bl_id": "BL-0001", "merged": True, "no_op": False}
        return _gen()

    def _qa_doc_ok_no_merge(*a, **k):
        async def _gen():
            yield {"_orchestrator_outcome": True, "role": "qa",
                   "bl_id": "BL-0001", "merged": False, "doctrine_ok": True}
        return _gen()

    reset_called = {"n": 0}

    async def _fake_rev_parse(repo, ref):
        return "PRE_BL_SHA_abc123"

    async def _fake_reset(repo, target_ref, sha):
        reset_called["n"] += 1
        return {"ok": True, "kind": "reset", "to_sha": sha}

    monkeypatch.setattr(orch, "_qa_or_scorer_flow", _qa_doc_ok_no_merge)
    monkeypatch.setattr(orch, "rev_parse", _fake_rev_parse)
    monkeypatch.setattr(orch, "reset_target_to", _fake_reset)

    events = _drive(monkeypatch, engineer_flow=_ok_engineer,
                    indexers=_noop_indexers, stop_on_failure=False)
    phases = _phases(events)

    assert "qa_merge_failed" in phases
    assert "bl.rolled_back" not in phases
    assert reset_called["n"] == 0
    bl_done = _suffix(events, "bl.done")
    assert bl_done and bl_done[-1].get("outcome") == "merged_no_qa"
