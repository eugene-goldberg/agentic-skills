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
        return_value=SimpleNamespace(
            agent_branch="agentic-skills-work",
            main_ref="main",
            effective_api_route_globs=lambda: [],
        )
    ))
    # ABL-0014 Item 1 Batch B: stub the backend-BL computation to []
    # so the legacy flow tests don't depend on a real git repo.
    monkeypatch.setattr(orch, "_compute_backend_bls",
                        AsyncMock(return_value=([], {})))
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
    # ABL-0014 §I.3 Batch B: ledger append event fires after archive,
    # and acceptance.done carries findings_persisted count (zero for
    # a clean run — the validator helper builds an all-pass report).
    assert "orchestrator.acceptance.ledger.appended" in phases
    appended_evt = next(
        e for e in events
        if e.get("phase") == "orchestrator.acceptance.ledger.appended"
    )
    assert appended_evt["findings_persisted"] == 0
    assert appended_evt["ledger_path"].endswith(
        "_brownfield/features/demo/acceptance/findings_log.jsonl"
    )
    assert events[-1]["findings_persisted"] == 0


# ─── happy-path: agent emits a failed journey → ledger persists 1 finding ──


def _fake_stream_that_writes_failed_report(wt_path: Path):
    """Stream that writes a minimal valid acceptance/ tree containing
    one failed api_journey with SKILLS.md-shaped top-level classification.
    Exercises the ledger integration end-to-end through _acceptance_flow."""
    from tests.test_acceptance_validator import _build_valid_acceptance_dir

    async def _g():
        feature_dir = wt_path / "_brownfield" / "features" / "demo"
        _build_valid_acceptance_dir(feature_dir)
        # Overwrite report.json with one that contains a failed journey.
        import json as _json
        report_path = feature_dir / "acceptance" / "report.json"
        report = _json.loads(report_path.read_text(encoding="utf-8"))
        report.setdefault("api_journeys", []).append({
            "id": "api_99",
            "status": "fail",
            "classification": "product_bug",
            "evidence": "POST /api/widgets returned 500 with FK violation",
            "hypothesis": "widget.owner_id constraint missing cascade",
        })
        report_path.write_text(_json.dumps(report), encoding="utf-8")
        yield {"type": "assistant", "message": "I reported a product bug."}
    return _g


def test_ledger_persists_failed_journey_finding(tmp_path: Path, monkeypatch) -> None:
    repo = _setup_happy_path(tmp_path, monkeypatch)
    wt_path = tmp_path / "wt"

    def stream_side_effect(*_args, **_kwargs):
        return _fake_stream_that_writes_failed_report(wt_path)()

    monkeypatch.setattr(orch, "stream_agent_task", stream_side_effect)
    monkeypatch.setattr(orch, "TraceWriter", MagicMock())

    events = asyncio.run(_collect(
        orch._acceptance_flow(repo, "demo", "run-x", "demo")
    ))
    phases = [e.get("phase") for e in events if e.get("phase")]
    appended = next(
        e for e in events
        if e.get("phase") == "orchestrator.acceptance.ledger.appended"
    )
    assert appended["findings_persisted"] == 1
    assert events[-1]["findings_persisted"] == 1
    # Ledger file was actually written under the repo root (not the
    # worktree — the ledger is per-feature persistence, not per-run).
    ledger_path = (
        repo / "_brownfield" / "features" / "demo" / "acceptance"
        / "findings_log.jsonl"
    )
    assert ledger_path.exists()
    line = ledger_path.read_text(encoding="utf-8").strip().splitlines()[0]
    import json as _json
    parsed = _json.loads(line)
    assert parsed["classification"] == "product_bug"
    assert parsed["journey_kind"] == "api"
    assert parsed["journey_id"] == "api_99"


# ─── ledger error path: corrupt report.json must not abort the flow ───────


def test_ledger_error_event_on_corrupt_report(tmp_path: Path, monkeypatch) -> None:
    repo = _setup_happy_path(tmp_path, monkeypatch)
    wt_path = tmp_path / "wt"

    def stream_side_effect(*_args, **_kwargs):
        # Build a valid tree first, then clobber report.json with bad JSON.
        from tests.test_acceptance_validator import _build_valid_acceptance_dir

        async def _g():
            feature_dir = wt_path / "_brownfield" / "features" / "demo"
            _build_valid_acceptance_dir(feature_dir)
            (feature_dir / "acceptance" / "report.json").write_text(
                "{this is not valid json", encoding="utf-8",
            )
            yield {"type": "assistant", "message": "I produced bad output."}
        return _g()

    monkeypatch.setattr(orch, "stream_agent_task", stream_side_effect)
    monkeypatch.setattr(orch, "TraceWriter", MagicMock())

    events = asyncio.run(_collect(
        orch._acceptance_flow(repo, "demo", "run-x", "demo")
    ))
    phases = [e.get("phase") for e in events if e.get("phase")]
    # Validator catches the corrupt JSON first, so flow ends in give_up,
    # but the ledger step still runs in the finally block and surfaces
    # an error event (and acceptance.done still fires — flow not aborted).
    assert "orchestrator.acceptance.ledger.error" in phases
    assert "orchestrator.acceptance.done" in phases
    assert events[-1]["findings_persisted"] == 0
