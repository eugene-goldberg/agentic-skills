"""Batch 3 (AUTONOMY_HARDENING_PLAN.md, C2 / A49 + ABL-0002 v1 + R16).

Covers:
- 3-1 dependency gating: a failed BL's dependents get `deferred_dep`
  (never dispatched, never built on air); independent BLs still run;
  sprint completes with the worst-wins `complete_with_deferrals` label.
- 3-2 triage: RETRY_REWRITE grants exactly ONE guided engineer retry
  (R16); DEFER/ESCALATE record decisions and the sprint continues;
  triage validator is enum-constrained with DEFER fallback; QA-context
  RETRY_REWRITE is coerced to DEFER.
- run_triage default is False everywhere (D1).
"""
from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import orchestrator as orch  # noqa: E402
from app.services import run_state as run_state_svc  # noqa: E402
from app.services.doctrine_validator import (  # noqa: E402
    parse_triage_decision,
    validate_triage,
)
from app.routers.projects import RunBriefRequest  # noqa: E402


BACKLOG = """# Backlog: X

## BL-0001: Foundation
**Story:** base · **Dependencies:** none

## BL-0002: Dependent
**Story:** needs base · **Dependencies:** BL-0001

## BL-0003: Independent
**Story:** standalone · **Dependencies:** none
"""


def _mk_repo(tmp_path: Path, feature: str = "feat") -> Path:
    import subprocess
    repo = tmp_path / "repo"
    d = repo / "_brownfield" / "features" / feature
    d.mkdir(parents=True)
    (d / "BACKLOG.md").write_text(BACKLOG)
    subprocess.run(["git", "-C", str(repo), "init", "-b", "main"],
                   check=True, capture_output=True)
    return repo


def _stub_flows(monkeypatch, *, fail_bls: set[str], eng_calls: list[dict]):
    """Stub every heavy flow. Engineer fails for bl_ids in fail_bls."""

    async def fake_engineer(repo_dir, repo_name, bl_id, timeout, rk_builder,
                            *, run_id=None, feature_slug=None,
                            section_override=None, task_id=None):
        eng_calls.append({"bl_id": bl_id, "section_override": section_override})
        merged = bl_id not in fail_bls
        if not merged:
            yield {"type": "_meta", "phase": "regression_gate", "ok": False,
                   "kind": "build_fail", "gate_failure_class": "build",
                   "reason": "build failed", "regressions": []}
        yield {"_orchestrator_outcome": True, "role": "engineer",
               "bl_id": bl_id, "merged": merged, "no_op": False}

    async def fake_qa_scorer(repo_dir, repo_name, bl_id, role, timeout,
                             rk_builder, *, run_id=None, feature_slug=None):
        yield {"_orchestrator_outcome": True, "role": role, "bl_id": bl_id,
               "merged": True, "doctrine_ok": True, "doctrine_summary": "ok"}

    async def fake_indexers(repo_dir, label):
        yield {"type": "_meta", "phase": f"orchestrator.{label}.done"}
        return

    async def fake_scan_all(repo_dir, run_id):
        return []

    monkeypatch.setattr(orch, "_engineer_flow", fake_engineer)
    monkeypatch.setattr(orch, "_qa_or_scorer_flow", fake_qa_scorer)
    monkeypatch.setattr(orch, "_run_indexers", fake_indexers)
    monkeypatch.setattr(orch.closure_check_svc, "scan_all", fake_scan_all)
    monkeypatch.setattr(orch.run_state_svc, "write_checkpoint",
                        lambda **k: None)
    monkeypatch.setattr(orch.run_state_svc, "mark_terminated",
                        lambda *a, **k: None)
    monkeypatch.setattr(orch, "_archive_traces_since", lambda *a, **k: 0)
    monkeypatch.setattr(orch, "_qa_commit_landed", lambda *a, **k: False)


def _run_sprint(repo, *, run_triage=False, monkeypatch=None, triage_stub=None):
    if triage_stub is not None:
        monkeypatch.setattr(orch, "_triage_flow", triage_stub)

    async def main():
        events = []
        async for e in orch.run_brief(
            repo_dir=repo, repo_name="repo", brief="x" * 25,
            project_name="p", retrieval_kwargs_builder=lambda *a: {},
            skip_po=True, stop_on_failure=False,
            run_doctrine_meta=False, run_acceptance=False,
            feature_slug="feat", run_triage=run_triage,
        ):
            events.append(e)
        return events

    return asyncio.run(main())


def _outcomes(events) -> dict:
    return {e["bl_id"]: e["outcome"] for e in events
            if e.get("phase") == "orchestrator.bl.done"}


# ─── 3-1: dependency gating (A49) ───────────────────────────────────────────


def test_dependents_of_failed_bl_are_deferred_not_dispatched(tmp_path, monkeypatch) -> None:
    repo = _mk_repo(tmp_path)
    eng_calls: list = []
    _stub_flows(monkeypatch, fail_bls={"BL-0001"}, eng_calls=eng_calls)
    events = _run_sprint(repo, monkeypatch=monkeypatch)

    out = _outcomes(events)
    assert out["BL-0001"] == "engineer_unmerged"
    assert out["BL-0002"] == "deferred_dep", (
        "a dependent of a failed BL must defer, not build on air (A49)"
    )
    assert out["BL-0003"] == "merged_full", "independent BLs still run"
    # BL-0002's engineer was NEVER spawned.
    assert [c["bl_id"] for c in eng_calls] == ["BL-0001", "BL-0003"]
    # dep_unmet skip event names the missing dependency.
    skip = next(e for e in events if e.get("phase") == "orchestrator.bl.skipped"
                and e.get("kind") == "dep_unmet")
    assert skip["deps_missing"] == ["BL-0001"]


def test_sprint_label_is_worst_wins(tmp_path, monkeypatch) -> None:
    repo = _mk_repo(tmp_path)
    _stub_flows(monkeypatch, fail_bls={"BL-0001"}, eng_calls=[])
    events = _run_sprint(repo, monkeypatch=monkeypatch)
    sc = next(e for e in events if e.get("phase") == "orchestrator.sprint_complete")
    assert sc["sprint_label"] == "complete_with_deferrals"
    assert {d["bl_id"] for d in sc["deferred"]} == {"BL-0002"}

    # Clean sprint → bare complete.
    repo2 = _mk_repo(tmp_path / "two")
    _stub_flows(monkeypatch, fail_bls=set(), eng_calls=[])
    events2 = _run_sprint(repo2, monkeypatch=monkeypatch)
    sc2 = next(e for e in events2 if e.get("phase") == "orchestrator.sprint_complete")
    assert sc2["sprint_label"] == "complete"
    assert sc2["deferred"] == []


def test_all_merged_satisfies_dependents(tmp_path, monkeypatch) -> None:
    repo = _mk_repo(tmp_path)
    eng_calls: list = []
    _stub_flows(monkeypatch, fail_bls=set(), eng_calls=eng_calls)
    events = _run_sprint(repo, monkeypatch=monkeypatch)
    out = _outcomes(events)
    assert out == {"BL-0001": "merged_full", "BL-0002": "merged_full",
                   "BL-0003": "merged_full"}


# ─── 3-2: triage decisions drive the loop ───────────────────────────────────


def _mk_triage_stub(decision: dict, calls: list):
    async def stub(repo_dir, repo_name, bl_id, *, failed_role, signals,
                   bl_section, timeout, run_id=None, feature_slug=None):
        calls.append({"bl_id": bl_id, "failed_role": failed_role,
                      "signals": signals})
        yield {"type": "_meta", "phase": "triage_agent_ran"}
        yield {"_triage_decision": True, "bl_id": bl_id, **decision}
    return stub


def test_retry_rewrite_grants_exactly_one_guided_attempt_r16(tmp_path, monkeypatch) -> None:
    repo = _mk_repo(tmp_path)
    eng_calls: list = []
    triage_calls: list = []
    _stub_flows(monkeypatch, fail_bls={"BL-0001"}, eng_calls=eng_calls)
    events = _run_sprint(
        repo, run_triage=True, monkeypatch=monkeypatch,
        triage_stub=_mk_triage_stub(
            {"decision": "RETRY_REWRITE",
             "guidance": "fix the routeTree regen", "reasoning": "x" * 130},
            triage_calls),
    )
    # Engineer BL-0001 attempted exactly twice (initial + ONE triage retry)
    bl1 = [c for c in eng_calls if c["bl_id"] == "BL-0001"]
    assert len(bl1) == 2, "R16: exactly one triage-granted retry"
    assert bl1[0]["section_override"] is None
    assert "fix the routeTree regen" in (bl1[1]["section_override"] or ""), (
        "triage guidance must be injected into the retry prompt"
    )
    # Triage consulted exactly once for the BL despite two failures.
    assert len([c for c in triage_calls if c["bl_id"] == "BL-0001"]) == 1
    # Failure signals reached triage.
    assert "regression_gate" in triage_calls[0]["signals"]
    # Both attempts failed → normal engineer_unmerged path (no abort:
    # stop_on_failure=False in the harness call).
    assert _outcomes(events)["BL-0001"] == "engineer_unmerged"


def test_defer_decision_records_and_continues(tmp_path, monkeypatch) -> None:
    repo = _mk_repo(tmp_path)
    eng_calls: list = []
    _stub_flows(monkeypatch, fail_bls={"BL-0001"}, eng_calls=eng_calls)
    events = _run_sprint(
        repo, run_triage=True, monkeypatch=monkeypatch,
        triage_stub=_mk_triage_stub(
            {"decision": "DEFER", "reasoning": "y" * 130}, []),
    )
    out = _outcomes(events)
    assert out["BL-0001"] == "deferred_triage"
    assert out["BL-0002"] == "deferred_dep"  # dependent auto-defers
    assert out["BL-0003"] == "merged_full"
    assert len([c for c in eng_calls if c["bl_id"] == "BL-0001"]) == 1, (
        "DEFER must not spawn a second engineer"
    )
    sc = next(e for e in events if e.get("phase") == "orchestrator.sprint_complete")
    assert sc["sprint_label"] == "complete_with_deferrals"


def test_escalate_writes_question_file_and_continues(tmp_path, monkeypatch) -> None:
    repo = _mk_repo(tmp_path)
    _stub_flows(monkeypatch, fail_bls={"BL-0001"}, eng_calls=[])
    events = _run_sprint(
        repo, run_triage=True, monkeypatch=monkeypatch,
        triage_stub=_mk_triage_stub(
            {"decision": "ESCALATE", "reasoning": "z" * 130,
             "question": "Should invoices allow negative totals? A) yes B) no"},
            []),
    )
    out = _outcomes(events)
    assert out["BL-0001"] == "escalated"
    esc = repo / "_brownfield" / "features" / "feat" / "escalations" / "BL-0001.md"
    assert esc.exists()
    assert "negative totals" in esc.read_text()
    ev = next(e for e in events if e.get("phase") == "orchestrator.triage.escalated")
    assert "negative totals" in ev["question"]


def test_triage_crash_falls_back_to_defer(tmp_path, monkeypatch) -> None:
    repo = _mk_repo(tmp_path)
    _stub_flows(monkeypatch, fail_bls={"BL-0001"}, eng_calls=[])

    async def crashing_triage(*a, **k):
        raise RuntimeError("triage exploded")
        yield  # pragma: no cover

    events = _run_sprint(repo, run_triage=True, monkeypatch=monkeypatch,
                         triage_stub=crashing_triage)
    dec = next(e for e in events if e.get("phase") == "orchestrator.triage.decision")
    assert dec["decision"] == "DEFER"
    assert dec["fallback"] is True
    assert _outcomes(events)["BL-0001"] == "deferred_triage"


def test_flag_off_means_zero_triage(tmp_path, monkeypatch) -> None:
    repo = _mk_repo(tmp_path)
    calls: list = []
    _stub_flows(monkeypatch, fail_bls={"BL-0001"}, eng_calls=[])
    _run_sprint(repo, run_triage=False, monkeypatch=monkeypatch,
                triage_stub=_mk_triage_stub({"decision": "DEFER"}, calls))
    assert calls == [], "run_triage=False must never invoke triage"


def test_run_triage_defaults_false_everywhere() -> None:
    assert RunBriefRequest(brief="x" * 25).run_triage is False
    sig = inspect.signature(orch.run_brief)
    assert sig.parameters["run_triage"].default is False


# ─── triage.md parsing + validation (enum constraint) ───────────────────────


VALID_TRIAGE = """DECISION: RETRY_REWRITE

## Reasoning

The gate failed on a stale routeTree.gen.ts (error TS2305 at line 12).
The engineer hand-edited imports instead of regenerating. This is
diagnosable and one guided attempt should clear it.

## Guidance

Run `bun run generate-routes` to regenerate routeTree.gen.ts, then re-run
the frontend build locally before committing.
"""


def test_parse_triage_decision_valid() -> None:
    d = parse_triage_decision(VALID_TRIAGE)
    assert d["decision"] == "RETRY_REWRITE"
    assert "regenerate" in d["guidance"]


def test_parse_triage_decision_rejects_free_text() -> None:
    assert parse_triage_decision("DECISION: MAYBE_RETRY\n## Reasoning\nx") is None
    assert parse_triage_decision("I think we should retry") is None


def test_validate_triage_enforces_sections(tmp_path) -> None:
    art = tmp_path / "_brownfield" / "features" / "feat" / "BL-0001"
    art.mkdir(parents=True)
    # Missing file.
    v = validate_triage(tmp_path, "BL-0001", feature_slug="feat")
    assert not v["ok"]
    # RETRY_REWRITE without guidance fails.
    (art / "triage.md").write_text(
        "DECISION: RETRY_REWRITE\n\n## Reasoning\n\n" + "r" * 130 + "\n")
    v2 = validate_triage(tmp_path, "BL-0001", feature_slug="feat")
    assert not v2["ok"] and any("Guidance" in m for m in v2["missing"])
    # Valid document passes and carries the parsed decision.
    (art / "triage.md").write_text(VALID_TRIAGE)
    v3 = validate_triage(tmp_path, "BL-0001", feature_slug="feat")
    assert v3["ok"] and v3["triage"]["decision"] == "RETRY_REWRITE"
    # ESCALATE requires a question.
    (art / "triage.md").write_text(
        "DECISION: ESCALATE\n\n## Reasoning\n\n" + "r" * 130 + "\n")
    v4 = validate_triage(tmp_path, "BL-0001", feature_slug="feat")
    assert not v4["ok"] and any("Question" in m for m in v4["missing"])
