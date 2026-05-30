"""Tests for ABL-0014 Batch B: orchestrator._acceptance_flow with spawn.

Three skip-path tests short-circuit before any external dependency. The
happy-path tests mock create_worktree/remove_worktree/stream_agent_task/
_load_skill/repo_config.load so the flow can be exercised without git or
the claude CLI.

Uses ``asyncio.run`` directly (backend test env has anyio but not
pytest-asyncio).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import orchestrator as orch  # noqa: E402


async def _collect(agen):
    return [e async for e in agen]


def _make_repo(tmp_path: Path, slug: str = "demo", with_brief: bool = True) -> Path:
    repo = tmp_path / "repo"
    feature = repo / "_brownfield" / "features" / slug
    feature.mkdir(parents=True)
    if with_brief:
        (feature / "brief.md").write_text("# Brief\n\nA capability.\n")
    return repo


# ─── skip paths (no external dep) ─────────────────────────────────────────


def test_skips_when_no_feature_slug(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    with patch.object(orch, "_gate_stack_present", new=AsyncMock(return_value=False)):
        events = asyncio.run(_collect(orch._acceptance_flow(repo, "demo", "run-x", None)))
    assert len(events) == 1
    assert events[0]["phase"] == "orchestrator.acceptance.skipped"
    assert events[0]["reason"] == "no_feature_slug"


def test_skips_when_brief_missing(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, with_brief=False)
    with patch.object(orch, "_gate_stack_present", new=AsyncMock(return_value=False)):
        events = asyncio.run(_collect(orch._acceptance_flow(repo, "demo", "run-x", "demo")))
    assert len(events) == 1
    assert events[0]["phase"] == "orchestrator.acceptance.skipped"
    assert events[0]["reason"] == "no_brief"


def test_skips_when_gate_stack_still_up(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    with patch.object(orch, "_gate_stack_present", new=AsyncMock(return_value=True)):
        events = asyncio.run(_collect(orch._acceptance_flow(repo, "demo", "run-x", "demo")))
    assert len(events) == 1
    assert events[0]["phase"] == "orchestrator.acceptance.skipped"
    assert events[0]["reason"] == "gate_stack_still_up"


# ─── happy-path helpers ────────────────────────────────────────────────────


def _setup_happy_path(tmp_path: Path, monkeypatch) -> Path:
    """Mock all external dependencies the flow needs."""
    repo = _make_repo(tmp_path)

    # Fake worktree that returns the feature dir under tmp_path so the
    # validator + archive can find a real on-disk acceptance/ tree.
    wt_path = tmp_path / "wt"
    wt_path.mkdir()
    # mirror the feature layout INSIDE the worktree
    (wt_path / "_brownfield" / "features" / "demo").mkdir(parents=True)

    fake_wt = SimpleNamespace(
        task_id="accept-run-x", path=wt_path, branch="agent/accept-run-x",
    )

    monkeypatch.setattr(orch, "_gate_stack_present", AsyncMock(return_value=False))
    monkeypatch.setattr(orch, "create_worktree", AsyncMock(return_value=fake_wt))
    monkeypatch.setattr(orch, "remove_worktree", AsyncMock(return_value=None))
    monkeypatch.setattr(orch.repo_config_svc, "load", MagicMock(
        return_value=SimpleNamespace(agent_branch="agentic-skills-work")
    ))
    monkeypatch.setattr(orch.prompts_brownfield_svc, "_load_skill",
                        MagicMock(return_value="# fake acceptance SKILLS.md"))
    return repo


def _fake_stream(*_args, **_kwargs):
    """An async generator that yields nothing (agent did no work)."""
    async def _g():
        if False:
            yield {}
    return _g()


def _fake_stream_that_writes_outputs(wt_path: Path):
    """An async generator that fakes a successful agent: yields one
    message event AND writes a valid acceptance/ tree on the way through."""
    from tests.test_acceptance_validator import _build_valid_acceptance_dir

    async def _g():
        # simulate the agent producing artifacts mid-stream
        feature_dir = wt_path / "_brownfield" / "features" / "demo"
        _build_valid_acceptance_dir(feature_dir)
        yield {"type": "assistant", "message": "I wrote the report."}
    return _g


# ─── happy-path: agent produces nothing → R10.1 give_up ──────────────────


def test_validator_give_up_after_max_retries(tmp_path: Path, monkeypatch) -> None:
    repo = _setup_happy_path(tmp_path, monkeypatch)
    monkeypatch.setattr(orch, "stream_agent_task", _fake_stream)
    monkeypatch.setattr(orch, "TraceWriter", MagicMock())

    events = asyncio.run(_collect(
        orch._acceptance_flow(repo, "demo", "run-x", "demo")
    ))
    phases = [e.get("phase") for e in events if e.get("phase")]

    assert phases[0] == "orchestrator.acceptance.start"
    # Three attempts (1 + R10.1=2) each followed by incomplete/give_up
    assert phases.count("orchestrator.acceptance.attempt.start") == 3
    assert "orchestrator.acceptance.validator.incomplete" in phases
    assert "orchestrator.acceptance.validator.give_up" in phases
    assert phases[-1] == "orchestrator.acceptance.done"
    assert events[-1]["validator_ok"] is False
    assert events[-1]["attempts"] == 3


# ─── happy-path: agent produces valid outputs on first try ───────────────


def test_validator_ok_on_first_attempt(tmp_path: Path, monkeypatch) -> None:
    repo = _setup_happy_path(tmp_path, monkeypatch)
    wt_path = tmp_path / "wt"

    # Stream yields nothing but the side effect of "calling it" is that the
    # outputs appear — we wire a writer-once side_effect.
    call_count = {"n": 0}

    def stream_side_effect(*_args, **_kwargs):
        call_count["n"] += 1
        return _fake_stream_that_writes_outputs(wt_path)()

    monkeypatch.setattr(orch, "stream_agent_task", stream_side_effect)
    monkeypatch.setattr(orch, "TraceWriter", MagicMock())

    events = asyncio.run(_collect(
        orch._acceptance_flow(repo, "demo", "run-x", "demo")
    ))
    phases = [e.get("phase") for e in events if e.get("phase")]

    assert "orchestrator.acceptance.validator.ok" in phases
    assert phases[-1] == "orchestrator.acceptance.done"
    assert events[-1]["validator_ok"] is True
    assert events[-1]["attempts"] == 1
    assert call_count["n"] == 1  # no retry on success
    # Archive event fires regardless of give_up vs ok
    assert "orchestrator.acceptance.archived" in phases
