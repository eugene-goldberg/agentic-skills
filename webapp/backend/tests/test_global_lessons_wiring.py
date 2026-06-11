"""ABL-0018 Stage 3 — inject_global_lessons plumbing + push-block wiring.

Verifies the INDEPENDENT global flag threads request -> run_brief -> the three
role flows -> the four build_* dispatchers -> _lessons_block, and that the
cross-target push block actually lands in a brownfield prompt when the flag is on
(and is absent when off) — including on a target with NO per-target lessons, which
is the whole point (a fresh target inherits the global layer day one).

The global store is redirected to a tmp jsonl via monkeypatch so these tests
never touch the real ``webapp/backend/.crew-memory/`` store.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import orchestrator as orch  # noqa: E402
from app.services import prompts as prompts_svc  # noqa: E402
from app.services import global_lessons as gl  # noqa: E402
from app.routers.projects import RunBriefRequest  # noqa: E402


@pytest.fixture()
def seeded_global(monkeypatch, tmp_path: Path):
    """Point the global store at a tmp jsonl + seed one curated cross-target
    lesson, and ENABLE the Stage-3 master switch for the render-path tests
    (cross-target transfer is dormant by default — operator 2026-06-11). Never
    indexes (index=False), so no Ollama dependency."""
    monkeypatch.setenv("STAGE3_CROSS_TARGET", "1")
    p = tmp_path / "global_lessons.jsonl"
    monkeypatch.setattr(gl, "global_lessons_path", lambda: p)
    gl.seed_global_lesson(
        classification="product_bug",
        body="new business logic added at one layer but pre-existing callers at "
             "another layer still hit the legacy path, so the UI diverges from the API",
        origin_targets=["beaverhabits", "fullstack-ecommerce-app"],
        note="layer-divergence; stack-agnostic", path=p, index=False,
    )
    return p


# ─── request model (independent flag, DEFAULT OFF) ──────────────────────────


def test_request_has_inject_global_lessons_default_false() -> None:
    # Independent from inject_lessons (higher blast radius → separate rollout).
    assert RunBriefRequest(brief="x" * 25).inject_global_lessons is False


def test_request_accepts_inject_global_lessons_true() -> None:
    assert RunBriefRequest(brief="x" * 25, inject_global_lessons=True).inject_global_lessons is True


# ─── signatures: run_brief + the three flows + four dispatchers ────────────


def test_run_brief_signature_has_inject_global_lessons_default_false() -> None:
    assert inspect.signature(orch.run_brief).parameters["inject_global_lessons"].default is False


def test_all_flows_accept_inject_global_lessons() -> None:
    for fn in (orch._po_flow, orch._engineer_flow, orch._qa_or_scorer_flow):
        p = inspect.signature(fn).parameters
        assert "inject_global_lessons" in p, f"{fn.__name__} missing inject_global_lessons"
        assert p["inject_global_lessons"].default is False


def test_all_dispatchers_accept_inject_global_lessons() -> None:
    for fn in (prompts_svc.build_po, prompts_svc.build_engineer,
               prompts_svc.build_qa, prompts_svc.build_score):
        p = inspect.signature(fn).parameters
        assert "inject_global_lessons" in p, f"{fn.__name__} missing inject_global_lessons"
        assert p["inject_global_lessons"].default is False


def test_run_brief_threads_inject_global_lessons_to_flows() -> None:
    src = inspect.getsource(orch.run_brief)
    assert src.count("inject_global_lessons=inject_global_lessons") >= 4  # po+eng+qa+scorer


# ─── behavioral: global block lands iff flag on — even with NO per-target lessons ─


def test_engineer_prompt_includes_global_when_on(seeded_global, tmp_path: Path) -> None:
    # tmp_path is a brownfield repo with NO per-target findings ledger — the
    # global layer must still surface (day-one inheritance).
    repo = tmp_path / "repo"; repo.mkdir()
    prompt = prompts_svc.build_engineer(
        "brownfield", "BL-0001", "do the thing", repo,
        feature_slug="feat-a", inject_lessons=True, inject_global_lessons=True,
    )
    assert "Cross-target lessons" in prompt
    assert "new business logic added at one layer" in prompt
    assert "seen across 2 targets" in prompt
    assert "Relevant prior lessons" not in prompt  # no per-target lessons here


def test_engineer_prompt_excludes_global_when_off(seeded_global, tmp_path: Path) -> None:
    repo = tmp_path / "repo"; repo.mkdir()
    prompt = prompts_svc.build_engineer(
        "brownfield", "BL-0001", "do the thing", repo,
        feature_slug="feat-a", inject_lessons=True, inject_global_lessons=False,
    )
    assert "Cross-target lessons" not in prompt


def test_po_and_qa_and_scorer_include_global_when_on(seeded_global, tmp_path: Path) -> None:
    repo = tmp_path / "repo"; repo.mkdir()
    po = prompts_svc.build_po("brownfield", "add reporting", "proj", repo,
                              feature_slug="feat-a", inject_global_lessons=True)
    qa = prompts_svc.build_qa("brownfield", "BL-0001", "sec", repo,
                              feature_slug="feat-a", inject_global_lessons=True)
    score = prompts_svc.build_score("brownfield", "BL-0001", "sec", repo,
                                    feature_slug="feat-a", inject_global_lessons=True)
    for p in (po, qa, score):
        assert "Cross-target lessons" in p


def test_global_dormant_by_default_even_with_flag_and_store(monkeypatch, tmp_path: Path) -> None:
    """Operator directive 2026-06-11: cross-target transfer is DORMANT. With the
    STAGE3_CROSS_TARGET master switch UNSET (default), the global block must NOT
    render even when inject_global_lessons=True AND the store has lessons."""
    monkeypatch.delenv("STAGE3_CROSS_TARGET", raising=False)
    p = tmp_path / "global_lessons.jsonl"
    monkeypatch.setattr(gl, "global_lessons_path", lambda: p)
    gl.seed_global_lesson(classification="product_bug", body="layer divergence",
                          origin_targets=["a", "b"], note="x", path=p, index=False)
    assert gl.list_global_lessons(path=p)              # store is non-empty
    assert gl.enabled() is False                        # switch off by default
    repo = tmp_path / "repo"; repo.mkdir()
    prompt = prompts_svc.build_engineer(
        "brownfield", "BL-0001", "do the thing", repo,
        feature_slug="feat-a", inject_lessons=True, inject_global_lessons=True,
    )
    assert "Cross-target lessons" not in prompt          # dormant → not surfaced


def test_global_silent_when_store_empty(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(gl, "global_lessons_path", lambda: tmp_path / "empty.jsonl")
    repo = tmp_path / "repo"; repo.mkdir()
    prompt = prompts_svc.build_engineer(
        "brownfield", "BL-0001", "do the thing", repo,
        feature_slug="feat-a", inject_global_lessons=True,
    )
    assert "Cross-target lessons" not in prompt  # silent when nothing graduated yet
