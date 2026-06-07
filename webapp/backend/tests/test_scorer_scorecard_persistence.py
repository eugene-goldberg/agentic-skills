"""Scorer scorecard persistence (open-item #2, 2026-06-07).

Before the fix, ``_qa_or_scorer_flow`` gated the *merge* block to ``role == "qa"``
(orchestrator.py), so the scorer's committed, doctrine-validated scorecard
(``.agile-v/scorecards/<bl>.md``) was never fast-forwarded onto the agent_branch
— it was dropped on the reaped scorer worktree. The fix adds a scorer ``elif``
that persists the scorecard via a GATE-FREE fast-forward: the scorer is read-only
(``validate_scorer``: "makes no source-code changes, so R3 does not apply"), so
A55's QA-only regression gate has nothing to run for it.

These tests drive the real ``_qa_or_scorer_flow`` with role="scorer" and every
heavy collaborator mocked, to prove (1) the scorecard now merges, (2) the gate is
NOT run for the read-only scorer, (3) doctrine failure still blocks the merge, and
(4) the A1 non-ff auto-rebase path still applies.
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


class _FakeBacklog:
    def read_text(self, *a, **k) -> str:  # noqa: D401
        return "BACKLOG"


def _patch_scorer_flow(monkeypatch, *, validation: dict, merge_results: list[dict],
                       new_commits: int = 1, rebase_ok: bool = True) -> dict:
    """Mock every collaborator the scorer path of _qa_or_scorer_flow touches."""
    counters = {"run_bl_tests": 0, "fast_forward_target": 0, "rebase": 0}

    monkeypatch.setattr(orch.repo_config_svc, "load",
                        lambda *a, **k: types.SimpleNamespace(
                            doctrine="brownfield", agent_branch="integration",
                            test_cmd=None))
    monkeypatch.setattr(orch.backlog_svc, "find_backlog", lambda *a, **k: _FakeBacklog())
    monkeypatch.setattr(orch.backlog_svc, "extract_section", lambda *a, **k: "S")
    monkeypatch.setattr(orch.prompts_svc, "build_score", lambda *a, **k: "PROMPT")
    monkeypatch.setattr(orch, "TraceWriter", lambda *a, **k: _FakeTrace())
    monkeypatch.setattr(orch, "_ptag", lambda event, *a, **k: event)
    monkeypatch.setattr(orch, "_tag", lambda event, *a, **k: event)

    async def _mk_wt(*a, **k):
        return Worktree("task", Path("/tmp/x"), "agent/task")

    async def _noop(*a, **k):
        return None

    async def _commits(*a, **k):
        return new_commits

    async def _stream(*a, **k):
        if False:
            yield {}

    async def _run_bl_tests(*a, **k):
        counters["run_bl_tests"] += 1
        return {"ok": True, "kind": "green", "reason": "x"}

    async def _ff(*a, **k):
        idx = min(counters["fast_forward_target"], len(merge_results) - 1)
        counters["fast_forward_target"] += 1
        return dict(merge_results[idx])

    async def _rebase(*a, **k):
        counters["rebase"] += 1
        return {"ok": rebase_ok, "error": None if rebase_ok else "conflict"}

    monkeypatch.setattr(orch, "create_worktree", _mk_wt)
    monkeypatch.setattr(orch, "remove_worktree", _noop)
    monkeypatch.setattr(orch, "has_new_commits", _commits)
    monkeypatch.setattr(orch, "stream_agent_task", _stream)
    monkeypatch.setattr(orch.regression_gate_svc, "run_bl_tests", _run_bl_tests)
    monkeypatch.setattr(orch, "fast_forward_target", _ff)
    monkeypatch.setattr(orch, "_rebase_in_worktree", _rebase)
    monkeypatch.setattr(orch.doctrine_svc, "validate_scorer", lambda *a, **k: dict(validation))
    monkeypatch.setattr(orch.doctrine_svc, "build_fix_prompt", lambda *a, **k: "FIX")
    return counters


def _drive_scorer(monkeypatch, **kw) -> tuple[dict | None, list[dict], dict]:
    counters = _patch_scorer_flow(monkeypatch, **kw)

    async def _collect():
        outcome = None
        events: list[dict] = []
        async for e in orch._qa_or_scorer_flow(
            Path("/tmp/repo"), "repo", "BL-0001", "scorer", 600,
            lambda *a, **k: {}, run_id="run-x", feature_slug="feat",
        ):
            if "_orchestrator_outcome" in e:
                outcome = e
            else:
                events.append(e)
        return outcome, events

    outcome, events = asyncio.run(_collect())
    return outcome, events, counters


def test_scorer_persists_scorecard_via_gate_free_merge(monkeypatch) -> None:
    """The fix: a doctrine-ok scorer with new commits fast-forwards onto the
    agent_branch (scorecard lands) WITHOUT running the regression gate."""
    outcome, events, counters = _drive_scorer(
        monkeypatch,
        validation={"ok": True, "summary": "doctrine ok"},
        merge_results=[{"ok": True, "kind": "ff", "merged_sha": "abc123"}],
    )
    assert outcome is not None
    assert outcome["role"] == "scorer"
    assert outcome["merged"] is True              # scorecard now persisted
    assert outcome["doctrine_ok"] is True
    assert counters["run_bl_tests"] == 0          # read-only: gate must NOT run
    assert counters["fast_forward_target"] == 1
    assert any(e.get("phase") == "merge_to_target" and e.get("ok") for e in events)


def test_scorer_doctrine_fail_does_not_merge(monkeypatch) -> None:
    """Guard: a scorer that never satisfies doctrine validation must NOT merge."""
    outcome, _events, counters = _drive_scorer(
        monkeypatch,
        validation={"ok": False, "summary": "missing scorecard"},
        merge_results=[{"ok": True, "kind": "ff"}],
    )
    assert outcome is not None
    assert outcome["merged"] is False
    assert outcome["doctrine_ok"] is False
    assert counters["fast_forward_target"] == 0   # merge never attempted
    assert counters["run_bl_tests"] == 0


def test_scorer_non_ff_auto_rebases_then_merges(monkeypatch) -> None:
    """A1 parity: when QA worktrees advance the agent_branch under the scorer,
    the first ff is non_ff; the scorer rebases and re-merges — still gate-free
    (a read-only branch can't regress, so no post-rebase gate runs)."""
    outcome, events, counters = _drive_scorer(
        monkeypatch,
        validation={"ok": True, "summary": "doctrine ok"},
        merge_results=[{"ok": False, "kind": "non_ff"},
                       {"ok": True, "kind": "ff", "merged_sha": "def456"}],
        rebase_ok=True,
    )
    assert outcome is not None
    assert outcome["merged"] is True
    assert counters["rebase"] == 1
    assert counters["fast_forward_target"] == 2    # initial non_ff + post-rebase
    assert counters["run_bl_tests"] == 0           # never a gate, even post-rebase
    assert any(e.get("phase") == "merge_rebase_succeeded" for e in events)
