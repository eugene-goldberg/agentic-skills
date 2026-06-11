"""ABL-0002 Stage 1 — the Architect adjudication flow (operator 2026-06-11).

At a CODE-gate exhaustion the orchestrator spawns the Architect to make the
step-back decision the confined engineer cannot. These tests drive
``_architect_flow`` with the agent subprocess mocked, proving:

1. the should-adjudicate gate fires on a CODE failure, NOT on a merge_error
   (Janitor's lane) and NOT when run_architect is off;
2. it reads the deterministic JSON sidecar verdict (disk, not stdout);
3. verdicts map correctly — retry_reframed / defer / escalate carried through;
   split/respec are Stage-1-honoured-as-escalate (no backlog mutation yet);
4. a missing / garbage sidecar, or an agent crash, degrades conservatively to
   escalate (advisory contract: an Architect failure never aborts the run).
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


# ─── the should-adjudicate gate ─────────────────────────────────────────────


def test_should_adjudicate_fires_on_code_failure() -> None:
    assert orch._architect_should_adjudicate({"blocker": None, "last_gate_kind": "failed"}, True) is True


def test_should_not_adjudicate_merge_error() -> None:
    # merge_error is the Janitor's lane — the Architect must not touch it.
    assert orch._architect_should_adjudicate({"blocker": "merge_error"}, True) is False


def test_should_not_adjudicate_when_flag_off() -> None:
    assert orch._architect_should_adjudicate({"blocker": None}, False) is False


# ─── flow: verdict parsing via the deterministic sidecar ────────────────────


def _patch(monkeypatch, repo_dir: Path, *, writes_verdict: dict | None, raises: bool = False):
    monkeypatch.setattr(orch.repo_config_svc, "load",
                        lambda *a, **k: types.SimpleNamespace(agent_branch="integration", main_ref="main"))
    monkeypatch.setattr(orch, "TraceWriter", lambda *a, **k: _FakeTrace())
    monkeypatch.setattr(orch, "_evt", lambda phase, **kw: {"type": "_meta", "phase": f"orchestrator.{phase}", **kw})
    monkeypatch.setattr(orch.prompts_brownfield_svc, "_load_skill", lambda role: "ARCHITECT SKILL")

    async def _stream(task, repo_path, **k):
        if raises:
            raise RuntimeError("agent crashed mid-stream")
        if writes_verdict is not None:
            adir = repo_dir / "_brownfield" / "features" / "_no_feature" / "architect"
            adir.mkdir(parents=True, exist_ok=True)
            (adir / "adjudicate-BL-0001-run-x.json").write_text(
                json.dumps(writes_verdict), encoding="utf-8")
        if False:
            yield {}

    monkeypatch.setattr(orch, "stream_agent_task", _stream)


def _drive(monkeypatch, repo_dir: Path, dossier: dict, **patch_kw) -> dict | None:
    _patch(monkeypatch, repo_dir, **patch_kw)

    async def _collect():
        outcome = None
        async for e in orch._architect_flow(repo_dir, "repo", "run-x", None,
                                            bl_id="BL-0001", dossier=dossier, timeout=60):
            if "_orchestrator_outcome" in e:
                outcome = e
        return outcome

    return asyncio.run(_collect())


def test_retry_reframed_verdict_carried(monkeypatch, tmp_path: Path) -> None:
    out = _drive(monkeypatch, tmp_path, {"last_gate_kind": "failed"},
                 writes_verdict={"mode": "adjudicate", "bl_id": "BL-0001",
                                 "verdict": "retry_reframed",
                                 "directive": "fix the FK at models.py:42",
                                 "root_cause": "models.py:42 missing cascade"})
    assert out["verdict"] == "retry_reframed"
    assert out["directive"] == "fix the FK at models.py:42"
    assert out["root_cause"].startswith("models.py:42")


def test_defer_verdict_carried(monkeypatch, tmp_path: Path) -> None:
    out = _drive(monkeypatch, tmp_path, {"last_gate_kind": "failed"},
                 writes_verdict={"verdict": "defer", "defer_reason": "needs a product decision on X"})
    assert out["verdict"] == "defer"
    assert out["defer_reason"] == "needs a product decision on X"


def test_escalate_verdict(monkeypatch, tmp_path: Path) -> None:
    out = _drive(monkeypatch, tmp_path, {"last_gate_kind": "failed"},
                 writes_verdict={"verdict": "escalate", "root_cause": "genuine wall"})
    assert out["verdict"] == "escalate"


def test_split_and_respec_are_escalate_in_stage1(monkeypatch, tmp_path: Path) -> None:
    for v in ("split", "respec"):
        out = _drive(monkeypatch, tmp_path, {"last_gate_kind": "failed"},
                     writes_verdict={"verdict": v, "root_cause": "too big"})
        assert out["verdict"] == "escalate"      # effective: no backlog mutation in Stage 1
        assert out["raw_verdict"] == v           # the recommendation is preserved


def test_missing_sidecar_degrades_to_escalate(monkeypatch, tmp_path: Path) -> None:
    out = _drive(monkeypatch, tmp_path, {"last_gate_kind": "failed"}, writes_verdict=None)
    assert out["verdict"] == "escalate"


def test_garbage_sidecar_degrades_to_escalate(monkeypatch, tmp_path: Path) -> None:
    _patch(monkeypatch, tmp_path, writes_verdict=None)
    adir = tmp_path / "_brownfield" / "features" / "_no_feature" / "architect"
    adir.mkdir(parents=True, exist_ok=True)
    (adir / "adjudicate-BL-0001-run-x.json").write_text("{not json", encoding="utf-8")

    async def _collect():
        outcome = None
        async for e in orch._architect_flow(tmp_path, "repo", "run-x", None,
                                            bl_id="BL-0001", dossier={"last_gate_kind": "failed"}, timeout=60):
            if "_orchestrator_outcome" in e:
                outcome = e
        return outcome

    out = asyncio.run(_collect())
    assert out["verdict"] == "escalate"


def test_agent_crash_never_aborts_yields_escalate(monkeypatch, tmp_path: Path) -> None:
    out = _drive(monkeypatch, tmp_path, {"last_gate_kind": "failed"}, writes_verdict=None, raises=True)
    assert out is not None and out["verdict"] == "escalate"  # advisory: degrade, never raise


def test_build_task_carries_dossier_and_schema() -> None:
    task = orch._build_architect_adjudicate_task(
        "SKILL", run_id="run-x", feature_slug="feat", bl_id="BL-0001",
        dossier={"last_failing_tests": ["test_x"], "blocker": None},
        agent_branch_failed="agent/abc",
        report_rel="r.md", report_json_rel="r.json")
    assert "MODE: adjudicate" in task
    assert "test_x" in task                     # the dossier is embedded
    assert "git diff agent/abc" in task         # the failed branch is inspectable
    assert "retry_reframed" in task and "defer" in task and "escalate" in task
    assert "BACKLOG.md" in task                 # the agent reads its own BL spec
