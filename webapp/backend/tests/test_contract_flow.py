"""Contract-First Phase 1 — _contract_flow orchestration tests (decision c, R22).

Drives the flow's control logic (skip / escalate-on-invalid / no-abort gate loop /
merge+done) with the heavy deps (worktree, agent subprocess, dotnet build, merge)
monkeypatched. The pure validation+conformance core is covered in test_contract.py.
Uses asyncio.run (no pytest-asyncio dependency)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import orchestrator as o  # noqa: E402


VALID_CONTRACT = """\
openapi: 3.1.0
info:
  title: Q API
  version: 1.0.0
paths:
  /api/questions:
    get:
      operationId: listQuestions
      responses:
        '200': {description: ok}
"""


async def _drain(agen):
    return [e async for e in agen]


def _phases(events):
    return [e.get("phase") for e in events if e.get("phase")]


def _wire(monkeypatch, tmp_path, *, gate_results):
    """Monkeypatch the heavy deps; return the contract dir so a test can write
    (or omit) the contract. gate_results = list of dicts _r22_gate returns in
    order (so a test can script fail->pass)."""
    wt_dir = tmp_path / "wt"
    wt_dir.mkdir(exist_ok=True)

    monkeypatch.setattr(o, "repo_config_svc",
                        SimpleNamespace(load=lambda rd: SimpleNamespace(agent_branch="integration", doctrine="brownfield")))
    monkeypatch.setattr(o, "classify_target", lambda rd: {})

    async def _fake_create_worktree(repo_dir, task_id=None, *, base_ref=None):
        return SimpleNamespace(path=wt_dir, branch="agent/contract", task_id="contract1")
    monkeypatch.setattr(o, "create_worktree", _fake_create_worktree)

    async def _fake_remove_worktree(repo_dir, wt, *, force=True):
        return None
    monkeypatch.setattr(o, "remove_worktree", _fake_remove_worktree)

    async def _fake_ff(repo_dir, branch, *, target_ref=None):
        return {"ok": True, "kind": "ff"}
    monkeypatch.setattr(o, "fast_forward_target", _fake_ff)

    async def _fake_stream(prompt, cwd, **kw):
        yield {"type": "token", "text": "ok"}
    monkeypatch.setattr(o, "stream_agent_task", _fake_stream)

    monkeypatch.setattr(o, "TraceWriter",
                        lambda **kw: SimpleNamespace(dir=tmp_path / "trace", retrieval_path=tmp_path / "r.jsonl",
                                                     write_phase_event=lambda ev: None))

    seq = list(gate_results)

    async def _fake_gate(wt_path, base_ref, spec_text, timeout, **_kw):
        return seq.pop(0) if seq else {"ok": True, "validation_errors": [], "unconformant": [],
                                       "build_ok": True, "build_kind": "build", "build_tail": ""}
    monkeypatch.setattr(o, "_r22_gate", _fake_gate)

    art = tmp_path / o.feature_artifact_dir(tmp_path, "feat")
    (art / "contract").mkdir(parents=True, exist_ok=True)
    return art / "contract" / "openapi.yaml"


def _run_flow(tmp_path):
    return _drain(o._contract_flow(tmp_path, "repo", run_id="r1", feature_slug="feat",
                                   timeout=10, retrieval_kwargs_builder=lambda *a: {}))


# ── skip / escalate ────────────────────────────────────────────────────────────

def test_skip_when_no_contract(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, gate_results=[])  # do not write the contract file
    events = asyncio.run(_run_flow(tmp_path))
    ph = _phases(events)
    assert "orchestrator.contract.start" in ph
    assert "orchestrator.contract.skipped" in ph
    assert "orchestrator.contract.done" not in ph


def test_escalate_on_invalid_contract(monkeypatch, tmp_path):
    cpath = _wire(monkeypatch, tmp_path, gate_results=[])
    cpath.write_text("openapi: '2.0'\ninfo: {}\npaths: {}\n", encoding="utf-8")
    events = asyncio.run(_run_flow(tmp_path))
    ph = _phases(events)
    assert "orchestrator.contract.escalated" in ph
    esc = next(e for e in events if e.get("phase") == "orchestrator.contract.escalated")
    assert "structural validation" in esc.get("reason", "")


# ── happy path + no-abort loop ───────────────────────────────────────────────────

def test_happy_path_materializes(monkeypatch, tmp_path):
    cpath = _wire(monkeypatch, tmp_path,
                  gate_results=[{"ok": True, "validation_errors": [], "unconformant": [],
                                 "build_ok": True, "build_kind": "build", "build_tail": ""}])
    cpath.write_text(VALID_CONTRACT, encoding="utf-8")
    events = asyncio.run(_run_flow(tmp_path))
    ph = _phases(events)
    assert "orchestrator.contract.materialized" in ph
    done = next(e for e in events if e.get("phase") == "orchestrator.contract.done")
    assert done.get("ok") is True


def test_no_abort_loop_fail_then_pass(monkeypatch, tmp_path):
    cpath = _wire(monkeypatch, tmp_path, gate_results=[
        {"ok": False, "validation_errors": [], "unconformant": ["GET /api/questions (listQuestions)"],
         "build_ok": True, "build_kind": "build", "build_tail": ""},
        {"ok": True, "validation_errors": [], "unconformant": [],
         "build_ok": True, "build_kind": "build", "build_tail": ""},
    ])
    cpath.write_text(VALID_CONTRACT, encoding="utf-8")
    events = asyncio.run(_run_flow(tmp_path))
    ph = _phases(events)
    # two gate checks (initial fail + retry pass) then done
    assert ph.count("orchestrator.contract.contract_gate") == 2 or \
        len([e for e in events if e.get("phase", "").endswith("contract_gate")]) == 2
    assert "orchestrator.contract.done" in ph


def test_escalate_when_gate_never_green(monkeypatch, tmp_path):
    bad = {"ok": False, "validation_errors": [], "unconformant": ["GET /api/questions (listQuestions)"],
           "build_ok": False, "build_kind": "build_failed", "build_tail": "CSxxxx"}
    cpath = _wire(monkeypatch, tmp_path, gate_results=[bad] * (o.MAX_FIX_ATTEMPTS + 2))
    cpath.write_text(VALID_CONTRACT, encoding="utf-8")
    events = asyncio.run(_run_flow(tmp_path))
    ph = _phases(events)
    assert "orchestrator.contract.escalated" in ph
    assert "orchestrator.contract.done" not in ph


# ── R22 fix prompt ───────────────────────────────────────────────────────────────

def test_r22_fix_prompt_mentions_failures():
    p = o._r22_fix_prompt({"build_ok": False, "build_kind": "build_failed",
                           "build_tail": "error CS1002", "unconformant": ["POST /x (addX)"],
                           "validation_errors": []})
    assert "dotnet build" in p and "CS1002" in p and "addX" in p
