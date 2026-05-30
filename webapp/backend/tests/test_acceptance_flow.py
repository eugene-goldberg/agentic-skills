"""Tests for ABL-0010 Batch A: orchestrator._acceptance_flow skeleton.

Asserts the skip paths and the happy-path event order. Batch A does NOT
spawn the agent — Batch B will. These tests validate plumbing only.

Uses ``asyncio.run`` directly to avoid an extra pytest-asyncio dep
(the backend's test env has anyio but not pytest-asyncio).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import orchestrator as orch  # noqa: E402


async def _collect(agen):
    return [e async for e in agen]


def _run_flow(repo: Path, slug: str | None, *, gate_up: bool = False) -> list[dict]:
    with patch.object(orch, "_gate_stack_present", new=AsyncMock(return_value=gate_up)):
        return asyncio.run(_collect(
            orch._acceptance_flow(repo, "demo-target", "run-x", slug)
        ))


def _make_repo(tmp_path: Path, slug: str = "demo", with_brief: bool = True) -> Path:
    repo = tmp_path / "repo"
    feature = repo / "_brownfield" / "features" / slug
    feature.mkdir(parents=True)
    if with_brief:
        (feature / "brief.md").write_text("# Brief\n\nA capability.\n")
    return repo


# ─── skip paths ────────────────────────────────────────────────────────────


def test_skips_when_no_feature_slug(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    events = _run_flow(repo, None)
    assert len(events) == 1
    assert events[0]["phase"] == "orchestrator.acceptance.skipped"
    assert events[0]["reason"] == "no_feature_slug"


def test_skips_when_brief_missing(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, with_brief=False)
    events = _run_flow(repo, "demo")
    assert len(events) == 1
    assert events[0]["phase"] == "orchestrator.acceptance.skipped"
    assert events[0]["reason"] == "no_brief"


def test_skips_when_gate_stack_still_up(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    events = _run_flow(repo, "demo", gate_up=True)
    assert len(events) == 1
    assert events[0]["phase"] == "orchestrator.acceptance.skipped"
    assert events[0]["reason"] == "gate_stack_still_up"


# ─── happy path (no acceptance/ dir → start + done, no validator event) ───


def test_happy_path_event_order_without_outputs(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    events = _run_flow(repo, "demo")
    phases = [e["phase"] for e in events]
    assert phases == [
        "orchestrator.acceptance.start",
        "orchestrator.acceptance.done",
    ]
    assert events[-1]["batch"] == "A"
    assert events[-1]["validator_ok"] is False


# ─── happy path with pre-existing valid outputs ──────────────────────────


def test_happy_path_with_valid_outputs_emits_validator_ok(tmp_path: Path) -> None:
    """If outputs already exist (Batch B agent left them, or a test
    fixture), the skeleton runs the validator and emits validator.ok."""
    from tests.test_acceptance_validator import _build_valid_acceptance_dir

    repo = _make_repo(tmp_path)
    feature_dir = repo / "_brownfield" / "features" / "demo"
    # _build_valid_acceptance_dir writes <arg>/acceptance/...; pointing it at
    # the feature dir lands the tree at .../features/demo/acceptance/.
    _build_valid_acceptance_dir(feature_dir)

    events = _run_flow(repo, "demo")
    phases = [e["phase"] for e in events]
    assert phases == [
        "orchestrator.acceptance.start",
        "orchestrator.acceptance.validator.ok",
        "orchestrator.acceptance.done",
    ]
    assert events[-1]["validator_ok"] is True
