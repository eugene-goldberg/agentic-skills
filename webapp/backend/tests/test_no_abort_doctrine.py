"""No-abort persistence doctrine (operator, 2026-06-06 — BINDING).

An agent that detects an issue must investigate → fix → re-test and keep working
until it is resolved. The per-role fix loops are therefore DEEP (MAX_FIX_ATTEMPTS,
not the old shallow cap of 2), retry on `inconclusive` as well as `regressed`
(both agent-fixable), and on exhaustion the run does not silently `abort` — it
`escalates` to the operator with a full dossier (Option A).

These tests drive `_engineer_flow` directly with all heavy collaborators mocked
to prove the loop depth, the inconclusive-retry, and the escalation dossier.
"""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app.services.orchestrator as orch  # noqa: E402
from app.services.git_worktree import Worktree  # noqa: E402


class _FakeTrace:
    dir = "/tmp/x"
    retrieval_path = "/tmp/x/retrieval.jsonl"

    def close(self) -> None:  # noqa: D401
        pass


def _patch_engineer_flow(monkeypatch, *, gate_result: dict) -> dict:
    """Mock every collaborator _engineer_flow touches; return a call-counter."""
    counters = {"run_bl_tests": 0}

    monkeypatch.setattr(orch.repo_config_svc, "load",
                        lambda *a, **k: types.SimpleNamespace(
                            doctrine="brownfield", agent_branch="agentic-skills-work",
                            test_cmd=None))
    monkeypatch.setattr(orch, "_resolve_engineer_section", lambda *a, **k: "S")
    monkeypatch.setattr(orch.prompts_svc, "build_engineer", lambda *a, **k: "PROMPT")
    monkeypatch.setattr(orch, "TraceWriter", lambda *a, **k: _FakeTrace())
    # passthrough tagging so no trace IO happens
    monkeypatch.setattr(orch, "_ptag", lambda event, *a, **k: event)
    monkeypatch.setattr(orch, "_tag", lambda event, *a, **k: event)

    async def _mk_wt(*a, **k):
        return Worktree("task", Path("/tmp/x"), "agent/task")

    async def _noop(*a, **k):
        return None

    async def _commits(*a, **k):
        return 1

    async def _stream(*a, **k):
        if False:
            yield {}

    async def _run_bl_tests(*a, **k):
        counters["run_bl_tests"] += 1
        return dict(gate_result)

    monkeypatch.setattr(orch, "create_worktree", _mk_wt)
    monkeypatch.setattr(orch, "remove_worktree", _noop)
    monkeypatch.setattr(orch, "has_new_commits", _commits)
    monkeypatch.setattr(orch, "stream_agent_task", _stream)
    monkeypatch.setattr(orch.regression_gate_svc, "run_bl_tests", _run_bl_tests)
    monkeypatch.setattr(orch.doctrine_svc, "validate_engineer",
                        lambda *a, **k: {"ok": True, "summary": "doctrine ok", "no_op": False})
    monkeypatch.setattr(orch.doctrine_svc, "build_gate_fix_prompt",
                        lambda *a, **k: "FIX")
    return counters


def _drive_engineer(monkeypatch, gate_result: dict) -> tuple[dict, list[dict]]:
    counters = _patch_engineer_flow(monkeypatch, gate_result=gate_result)

    async def _collect():
        outcome = None
        events = []
        async for e in orch._engineer_flow(
            Path("/tmp/repo"), "repo", "BL-0001", 600,
            lambda *a, **k: {}, run_id="run-x", feature_slug="feat",
        ):
            if "_orchestrator_outcome" in e:
                outcome = e
            else:
                events.append(e)
        return outcome, events, counters

    outcome, events, counters = asyncio.run(_collect())
    return {"outcome": outcome, "counters": counters}, events


def test_persistent_failed_bl_tests_loops_deep_then_escalates(monkeypatch) -> None:
    """Per-BL: a BL whose own unit tests stay `failed` is retried up to
    MAX_FIX_ATTEMPTS (NOT the old cap of 2), then the engineer escalates with an
    exhausted-ceiling dossier instead of merging or silently aborting."""
    gate = {"ok": False, "kind": "failed",
            "reason": "1 BL unit-test failure(s)", "regressions": ["tests/test_x.py::test_y"],
            "new_failures": ["tests/test_x.py::test_y"], "post_tail": "", "failing_tests": []}
    res, _events = _drive_engineer(monkeypatch, gate)

    # initial scoped run + one per fix attempt up to the ceiling.
    assert res["counters"]["run_bl_tests"] == orch.MAX_FIX_ATTEMPTS + 1
    out = res["outcome"]
    assert out is not None
    assert out.get("merged") is False
    assert out.get("escalated") is True
    d = out.get("dossier") or {}
    assert d.get("gate_attempts") == orch.MAX_FIX_ATTEMPTS
    assert d.get("exhausted_ceiling") is True
    assert d.get("last_gate_kind") == "failed"   # the BL's own tests kept failing


def test_max_fix_attempts_is_deep_not_two() -> None:
    """Guard against a regression back to the old shallow give-up cap."""
    assert orch.MAX_FIX_ATTEMPTS >= 5
