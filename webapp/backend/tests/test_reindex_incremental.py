"""Unit tests for the flag-gated reindex_incremental wiring (follow-up #5).

Locks the op-selection contract: flag OFF -> "index" everywhere (byte-identical
rollback); flag ON -> index_initial uses "index_baseline" and every reindex_after_*
barrier uses "reindex". Also that run_claude_context_index forwards op into the
bridge command. The bridge ops themselves are proven by a live isolation test.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.services.orchestrator as orch  # noqa: E402
import app.services.indexing as indexing  # noqa: E402


def _op_for(label: str, flag: bool, monkeypatch) -> str:
    captured: dict = {}

    async def fake_cc(repo_path, op="index"):
        captured["op"] = op
        return {"ok": True}

    async def fake_gr(repo_path):
        return {"ok": True}

    monkeypatch.setattr(orch, "run_claude_context_index", fake_cc)
    monkeypatch.setattr(orch, "run_graphify_update", fake_gr)

    async def _drain():
        async for _ in orch._run_indexers(Path("/tmp/x"), label, reindex_incremental=flag):
            pass

    asyncio.run(_drain())
    return captured["op"]


def test_flag_off_always_full_index(monkeypatch):
    assert _op_for("index_initial", False, monkeypatch) == "index"
    assert _op_for("reindex_after_wave.0", False, monkeypatch) == "index"
    assert _op_for("reindex_after_qa.BL-0001", False, monkeypatch) == "index"


def test_flag_on_index_initial_uses_baseline(monkeypatch):
    assert _op_for("index_initial", True, monkeypatch) == "index_baseline"


def test_flag_on_barriers_use_reindex(monkeypatch):
    assert _op_for("reindex_after_wave.0", True, monkeypatch) == "reindex"
    assert _op_for("reindex_after_wave.1", True, monkeypatch) == "reindex"
    assert _op_for("reindex_after_engineer.BL-0002", True, monkeypatch) == "reindex"
    assert _op_for("reindex_after_qa.BL-0003", True, monkeypatch) == "reindex"


def test_run_claude_context_index_forwards_op(monkeypatch):
    captured: dict = {}

    async def fake_run(cmd, cwd=None, timeout=None):
        captured["cmd"] = cmd
        return (0, json.dumps({"ok": True, "result": {"added": 0}}), "")

    monkeypatch.setattr(indexing, "_run", fake_run)
    asyncio.run(indexing.run_claude_context_index(Path("/tmp/x"), op="reindex"))
    payload = json.loads(captured["cmd"][-1])
    assert payload["op"] == "reindex"
    # default stays "index" (rollback)
    asyncio.run(indexing.run_claude_context_index(Path("/tmp/x")))
    assert json.loads(captured["cmd"][-1])["op"] == "index"


def test_reindex_incremental_default_is_on():
    """Operator 2026-06-15: incremental barrier reindex is the DEFAULT for every crew
    run. Lock the default ON in all three layers so an accidental flip-back is caught;
    reindex_incremental=False remains the explicit full-index rollback."""
    import inspect
    from app.routers.projects import RunBriefRequest
    assert inspect.signature(orch.run_brief).parameters["reindex_incremental"].default is True
    assert inspect.signature(orch._run_indexers).parameters["reindex_incremental"].default is True
    assert RunBriefRequest.model_fields["reindex_incremental"].default is True
    # default-constructed request opts into incremental
    assert RunBriefRequest(brief="x" * 30).reindex_incremental is True
