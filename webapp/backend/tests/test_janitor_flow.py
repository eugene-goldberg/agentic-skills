"""Janitor / Ops-Steward flow (R16) — wired with full §6 authority, 2026-06-07.

The orchestrator DETECTS a non-code failure and spawns the Janitor to repair the
live run state in the REAL repo checkout. These tests drive ``_janitor_flow``
with the agent subprocess mocked, proving:

1. it reads the deterministic sidecar verdict (disk-based, not stdout);
2. a ``structural`` verdict emits a ``structural_anomaly`` event (I-7 → doctrine-meta);
3. a missing/garbage verdict degrades conservatively to escalated + retry=False
   (advisory contract: a Janitor failure never aborts the run);
4. the non-code-kind discriminator excludes code-defect gate kinds (so the
   Janitor can never mask a real test failure).
"""
from __future__ import annotations

import asyncio
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app.services.orchestrator as orch  # noqa: E402


class _FakeTrace:
    def close(self) -> None:  # noqa: D401
        pass


def _patch(monkeypatch, repo_dir: Path, *, writes_verdict: dict | None,
           raises: bool = False):
    monkeypatch.setattr(orch.repo_config_svc, "load",
                        lambda *a, **k: types.SimpleNamespace(
                            agent_branch="integration", main_ref="main"))
    monkeypatch.setattr(orch, "TraceWriter", lambda *a, **k: _FakeTrace())
    monkeypatch.setattr(orch, "_evt", lambda phase, **kw: {"type": "_meta",
                                                           "phase": f"orchestrator.{phase}", **kw})

    async def _stream(task, repo_path, **k):
        # Simulate the agent writing its sidecar verdict to disk, then finishing.
        if raises:
            raise RuntimeError("agent crashed mid-stream")
        if writes_verdict is not None:
            # Mirror the real agent: write to the janitor sidecar path the flow
            # computed (slug "_no_feature" when feature_slug is None).
            jdir = repo_dir / "_brownfield" / "features" / "_no_feature" / "janitor"
            jdir.mkdir(parents=True, exist_ok=True)
            # The flow names the file <step>-<run_id>.json with "/" and " " → "_".
            (jdir / "qa.merge_to_target-run-x.json").write_text(
                json.dumps(writes_verdict), encoding="utf-8")
        if False:
            yield {}

    monkeypatch.setattr(orch, "stream_agent_task", _stream)


def _drive(monkeypatch, repo_dir: Path, **patch_kw) -> tuple[dict | None, list[dict]]:
    _patch(monkeypatch, repo_dir, **patch_kw)

    async def _collect():
        outcome = None
        events: list[dict] = []
        async for e in orch._janitor_flow(
            repo_dir, "repo", "run-x", None,
            failed_step="qa.merge_to_target", blocker_reason="merge did not land",
            failing_role="qa", bl_id="BL-0001", timeout=60,
        ):
            if "_orchestrator_outcome" in e:
                outcome = e
            else:
                events.append(e)
        return outcome, events

    return asyncio.run(_collect())


def test_janitor_reads_sidecar_and_signals_retry(tmp_path, monkeypatch) -> None:
    outcome, events = _drive(
        monkeypatch, tmp_path,
        writes_verdict={"status": "repaired", "classification": "transient",
                        "retry": True, "root_cause": "stray dirty file",
                        "actions": ["git restore x"], "summary": "ok"},
    )
    assert outcome is not None
    assert outcome["role"] == "janitor"
    assert outcome["status"] == "repaired"
    assert outcome["retry"] is True
    assert outcome["classification"] == "transient"
    # no structural_anomaly for a transient repair
    assert not any(e["phase"] == "orchestrator.janitor.structural_anomaly" for e in events)
    assert any(e["phase"] == "orchestrator.janitor.done" for e in events)


def test_janitor_structural_routes_to_doctrine_meta(tmp_path, monkeypatch) -> None:
    outcome, events = _drive(
        monkeypatch, tmp_path,
        writes_verdict={"status": "repaired", "classification": "structural",
                        "retry": True, "root_cause": "harness tracks events.jsonl",
                        "proposed_framework_fix": "gitignore the live log",
                        "actions": ["edit .gitignore"], "summary": "structural"},
    )
    assert outcome["classification"] == "structural"
    sa = [e for e in events if e["phase"] == "orchestrator.janitor.structural_anomaly"]
    assert len(sa) == 1
    assert sa[0]["proposed_framework_fix"] == "gitignore the live log"


def test_janitor_no_verdict_degrades_to_escalated(tmp_path, monkeypatch) -> None:
    """Advisory contract: no sidecar verdict → escalated, retry=False (never a
    silent retry on an unverified repair)."""
    outcome, _events = _drive(monkeypatch, tmp_path, writes_verdict=None)
    assert outcome["status"] == "escalated"
    assert outcome["retry"] is False


def test_janitor_agent_crash_never_raises(tmp_path, monkeypatch) -> None:
    """A Janitor subprocess crash must degrade, not propagate (never abort run)."""
    outcome, events = _drive(monkeypatch, tmp_path, writes_verdict=None, raises=True)
    assert outcome["status"] == "escalated"
    assert outcome["retry"] is False
    assert any(e["phase"] == "orchestrator.janitor.error" for e in events)


def test_noncode_kinds_exclude_code_defects() -> None:
    """The discriminator must route ONLY environment failures — never code
    defects (which the engineer/QA no-abort loop owns), so the Janitor can never
    mask a real test failure."""
    assert "error" in orch.JANITOR_NONCODE_KINDS
    assert "infra_fail" in orch.JANITOR_NONCODE_KINDS
    for code_defect in ("failed", "no_tests", "regressed", "inconclusive", "green"):
        assert code_defect not in orch.JANITOR_NONCODE_KINDS


# ── A58: engineer-path merge-error must route to the Janitor ──────────────────

def test_engineer_janitor_trigger_merge_error_after_green_gate() -> None:
    """The regression that escalated Exp-2 BL-0001: the gate was GREEN but
    merge_to_target failed (dirty target checkout). last_gate_kind is "green"
    (NOT a JANITOR_NONCODE_KIND), so the old guard skipped the Janitor. The
    merge_error blocker must now fire it."""
    dossier = {"role": "engineer", "bl_id": "BL-0001",
               "last_gate_kind": "green",
               "last_gate_reason": "BL unit tests green (41 passed)",
               "blocker": "merge_error",
               "merge_kind": "error",
               "merge_error": "main checkout has modified tracked files; not merging"}
    assert orch._engineer_janitor_trigger(dossier, run_janitor=True) is True
    # …and the run_janitor=False rollback flag still disables it.
    assert orch._engineer_janitor_trigger(dossier, run_janitor=False) is False


def test_engineer_janitor_trigger_noncode_gate_kind() -> None:
    """A non-code GATE kind (error/infra_fail) still fires the Janitor."""
    for kind in ("error", "infra_fail"):
        assert orch._engineer_janitor_trigger(
            {"last_gate_kind": kind}, run_janitor=True) is True


def test_engineer_janitor_trigger_green_gate_no_merge_failure_does_not_fire() -> None:
    """A clean green gate with NO merge failure must NOT spawn the Janitor —
    the merged-OK / code-defect paths are never the Janitor's business."""
    assert orch._engineer_janitor_trigger(
        {"last_gate_kind": "green"}, run_janitor=True) is False
    for code_defect in ("failed", "no_tests", "regressed", "inconclusive"):
        assert orch._engineer_janitor_trigger(
            {"last_gate_kind": code_defect}, run_janitor=True) is False


# ── A59: Janitor must FULLY resolve a merge failure (re-merge after repair) ────

def test_remerge_after_janitor_when_repaired() -> None:
    """The full-resolution standard: a merge_error the Janitor REPAIRED, with a
    known branch, must trigger a re-attempt of the merge (not escalation)."""
    assert orch._should_remerge_after_janitor({
        "blocker": "merge_error",
        "merge_branch": "agent/abc123",
        "janitor": {"status": "repaired", "retry": True},
    }) is True


def test_no_remerge_when_janitor_did_not_repair() -> None:
    """If the Janitor could not repair (escalated), do NOT blindly re-merge —
    that would be a give-up dressed as a retry. Fall through to honest escalation."""
    assert orch._should_remerge_after_janitor({
        "blocker": "merge_error",
        "merge_branch": "agent/abc123",
        "janitor": {"status": "escalated", "retry": False},
    }) is False
    # missing janitor outcome entirely → no re-merge
    assert orch._should_remerge_after_janitor({
        "blocker": "merge_error", "merge_branch": "agent/abc123",
    }) is False


def test_no_remerge_when_not_a_merge_error() -> None:
    """A code-defect / non-merge blocker is owned by the engineer's own loop —
    never re-merged by the Janitor path even if a 'repaired' verdict appears."""
    assert orch._should_remerge_after_janitor({
        "last_gate_kind": "error",
        "merge_branch": "agent/abc123",
        "janitor": {"status": "repaired"},
    }) is False


def test_no_remerge_without_known_branch() -> None:
    """Can't re-merge what we can't name — missing merge_branch → no re-merge."""
    assert orch._should_remerge_after_janitor({
        "blocker": "merge_error",
        "janitor": {"status": "repaired"},
    }) is False
