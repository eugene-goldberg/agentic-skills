"""Batch 7 (AUTONOMY_HARDENING_PLAN.md, M2–M4) — deployment-grade hygiene.

- 7-1a (A51): PF-6 becomes code — wrong-branch / dirty main checkout
  aborts BEFORE any agent spawns.
- 7-1b (A51): the PO artifact commit is verified; a hook-blocked commit
  yields a structured po_commit failure instead of a sprint that forks
  worktrees without PO context.
- 7-2 (A53): indexer failures trigger one Milvus restart + retry; still
  failing → initial index aborts, mid-sprint reindex degrades LOUDLY.
- 7-3 (A52): agent env is allowlisted — retrieval secrets never reach
  the agent process; operator extension + passthrough escape hatch work.
"""
from __future__ import annotations

import asyncio
import os
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import claude_agent  # noqa: E402
from app.services import orchestrator as orch  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "PATH": "/usr/bin:/bin"}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, env=GIT_ENV)


def _mk_target(tmp_path: Path, *, on_branch: str = "agentic-skills-work") -> Path:
    repo = tmp_path / "target"
    d = repo / "_brownfield" / "features" / "feat"
    d.mkdir(parents=True)
    (d / "BACKLOG.md").write_text(
        "# Backlog: X\n\n## BL-0001: One\n**Story:** s\n")
    subprocess.run(["git", "-C", str(repo), "init", "-b", "main"],
                   check=True, capture_output=True)
    (repo / "a.txt").write_text("x")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    _git(repo, "branch", "agentic-skills-work")
    _git(repo, "checkout", on_branch)
    return repo


def _stub_common(monkeypatch):
    async def fake_engineer(repo_dir, repo_name, bl_id, timeout, rk, **kw):
        yield {"_orchestrator_outcome": True, "role": "engineer",
               "bl_id": bl_id, "merged": True, "no_op": False}

    async def fake_qa_scorer(repo_dir, repo_name, bl_id, role, timeout, rk, **kw):
        yield {"_orchestrator_outcome": True, "role": role, "bl_id": bl_id,
               "merged": True, "doctrine_ok": True, "doctrine_summary": "ok"}

    async def fake_indexers(repo_dir, label):
        yield {"type": "_meta", "phase": f"orchestrator.{label}.done",
               "claude_context": {"ok": True}, "graphify": {"ok": True}}

    async def fake_scan_all(repo_dir, run_id):
        return []

    monkeypatch.setattr(orch, "_engineer_flow", fake_engineer)
    monkeypatch.setattr(orch, "_qa_or_scorer_flow", fake_qa_scorer)
    monkeypatch.setattr(orch, "_run_indexers", fake_indexers)
    monkeypatch.setattr(orch.closure_check_svc, "scan_all", fake_scan_all)
    monkeypatch.setattr(orch.run_state_svc, "write_checkpoint", lambda **k: None)
    monkeypatch.setattr(orch.run_state_svc, "mark_terminated", lambda *a, **k: None)
    monkeypatch.setattr(orch, "_archive_traces_since", lambda *a, **k: 0)
    monkeypatch.setattr(orch, "_qa_commit_landed", lambda *a, **k: False)


def _run(repo, **kwargs):
    async def main():
        return [e async for e in orch.run_brief(
            repo_dir=repo, repo_name="repo", brief="x" * 25, project_name="p",
            retrieval_kwargs_builder=lambda *a: {}, skip_po=True,
            run_doctrine_meta=False,
            run_acceptance=False, feature_slug="feat",
            **{"stop_on_failure": True, **kwargs},
        )]
    return asyncio.run(main())


# ─── 7-1a: checkout preflight ───────────────────────────────────────────────


def test_wrong_branch_aborts_before_any_spawn(tmp_path, monkeypatch) -> None:
    repo = _mk_target(tmp_path, on_branch="main")  # agent branch exists, not checked out
    _stub_common(monkeypatch)
    events = _run(repo)
    pf = next(e for e in events if e.get("phase") == "orchestrator.pre_flight.checkout")
    assert pf["ok"] is False and pf["expected"] == "agentic-skills-work"
    ab = next(e for e in events if e.get("phase") == "orchestrator.aborted")
    assert "A51" in ab["reason"]
    assert not [e for e in events if e.get("phase") == "orchestrator.bl.start"], (
        "abort must land before any BL dispatch"
    )


def test_dirty_tracked_checkout_aborts(tmp_path, monkeypatch) -> None:
    repo = _mk_target(tmp_path)  # on agent branch
    (repo / "a.txt").write_text("modified tracked file")
    _stub_common(monkeypatch)
    events = _run(repo)
    ab = next(e for e in events if e.get("phase") == "orchestrator.aborted")
    assert "modified tracked files" in ab["reason"]


def test_clean_correct_checkout_proceeds(tmp_path, monkeypatch) -> None:
    repo = _mk_target(tmp_path)
    _stub_common(monkeypatch)
    events = _run(repo)
    pf = next(e for e in events if e.get("phase") == "orchestrator.pre_flight.checkout")
    assert pf["ok"] is True
    assert any(e.get("phase") == "orchestrator.sprint_complete" for e in events)


# ─── 7-1b: checked PO commit ────────────────────────────────────────────────


def _run_po(repo, monkeypatch):
    async def stub_stream(prompt, wt_path, *, timeout_seconds, trace=None,
                          min_pregrounding=0, **rk):
        yield {"type": "_meta", "phase": "spawn"}
        yield {"type": "_meta", "phase": "exit", "exit_code": 0}
    monkeypatch.setattr(orch, "stream_agent_task", stub_stream)
    monkeypatch.setattr(orch.doctrine_svc, "validate_po",
                        lambda *a, **k: {"ok": True, "summary": "ok", "missing": []})

    async def main():
        events = []
        async for e in orch._po_flow(repo, "repo", "brief text " * 3, "proj",
                                     60, lambda *a: {}, run_id="run-po",
                                     feature_slug="feat"):
            events.append(e)
        return events
    return asyncio.run(main())


def test_po_commit_verified_ok(tmp_path, monkeypatch) -> None:
    repo = _mk_target(tmp_path, on_branch="main")
    events = _run_po(repo, monkeypatch)
    pc = next(e for e in events if e.get("phase") == "po_commit")
    assert pc["ok"] is True and pc["sha"]
    out = next(e for e in events if e.get("_orchestrator_outcome"))
    assert out["doctrine_ok"] is True
    # The brief actually landed in git.
    tracked = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "_brownfield/"],
        capture_output=True, text=True, check=True).stdout
    assert "brief.md" in tracked


def test_po_commit_blocked_by_hook_is_structured_failure(tmp_path, monkeypatch) -> None:
    """The A51 failure mode: a pre-commit hook (or index lock, or wrong
    branch) blocks the commit. Old code (check=False ×2) proceeded
    silently; every later worktree forked WITHOUT PO context."""
    repo = _mk_target(tmp_path, on_branch="main")
    hooks = repo / ".git" / "hooks"
    hook = hooks / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)

    events = _run_po(repo, monkeypatch)
    pc = next(e for e in events if e.get("phase") == "po_commit")
    assert pc["ok"] is False and pc["leftover"]
    out = next(e for e in events if e.get("_orchestrator_outcome"))
    assert out["doctrine_ok"] is False
    assert out["commit_failed"] is True


# ─── 7-2: indexer health ─────────────────────────────────────────────────────


def _failing_then(monkeypatch, results: list[bool], restarts: list):
    """_run_indexers stub returning ok per results[i] on call i."""
    calls = {"n": 0}

    async def fake_indexers(repo_dir, label):
        ok = results[min(calls["n"], len(results) - 1)]
        calls["n"] += 1
        yield {"type": "_meta", "phase": f"orchestrator.{label}.done",
               "claude_context": {"ok": ok}, "graphify": {"ok": True}}

    async def fake_restart(timeout_s=30.0):
        restarts.append(True)
        return True

    monkeypatch.setattr(orch, "_run_indexers", fake_indexers)
    monkeypatch.setattr(orch, "_restart_milvus", fake_restart)


def test_indexer_failure_restarts_milvus_and_recovers(tmp_path, monkeypatch) -> None:
    restarts: list = []
    _failing_then(monkeypatch, [False, True], restarts)

    async def main():
        events = []
        ok = None
        async for e in orch._run_indexers_checked(tmp_path, "index_initial"):
            if "_indexers_ok" in e:
                ok = e["_indexers_ok"]
                continue
            events.append(e)
        return ok, events

    ok, events = asyncio.run(main())
    assert ok is True
    assert restarts == [True], "one Milvus restart attempt"
    assert any(e.get("phase") == "orchestrator.index_initial.milvus_restart"
               for e in events)


def test_initial_index_failure_aborts_sprint(tmp_path, monkeypatch) -> None:
    repo = _mk_target(tmp_path)
    _stub_common(monkeypatch)
    restarts: list = []
    _failing_then(monkeypatch, [False, False], restarts)  # fails even after restart
    events = _run(repo)
    ab = next(e for e in events if e.get("phase") == "orchestrator.aborted")
    assert "A53" in ab["reason"] and "ungrounded" in ab["reason"]
    assert not [e for e in events if e.get("phase") == "orchestrator.bl.start"]


def test_midsprint_reindex_failure_is_loud(tmp_path, monkeypatch) -> None:
    repo = _mk_target(tmp_path)
    _stub_common(monkeypatch)
    restarts: list = []
    # initial ok; reindex_after_engineer fails; retry fails too
    _failing_then(monkeypatch, [True, False, False], restarts)
    events = _run(repo, stop_on_failure=False)
    deg = [e for e in events if e.get("phase") == "orchestrator.indexing_degraded"]
    assert deg, "mid-sprint reindex failure must be LOUD (A53), never silent"
    assert deg[0]["stage"] == "reindex_after_engineer"
    # stop_on_failure=False → sprint continues past the degradation.
    assert any(e.get("phase") == "orchestrator.sprint_complete" for e in events)


# ─── 7-3: agent env allowlist ───────────────────────────────────────────────


def test_agent_env_excludes_retrieval_secrets(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "sekrit")
    monkeypatch.setenv("OPENAI_API_KEY", "sekrit2")
    monkeypatch.setenv("MILVUS_TOKEN", "sekrit3")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "claude-auth")
    monkeypatch.delenv("AGENT_ENV_PASSTHROUGH_ALL", raising=False)
    monkeypatch.delenv("AGENT_ENV_ALLOWLIST", raising=False)
    env = claude_agent._agent_env()
    assert "AZURE_OPENAI_API_KEY" not in env
    assert "OPENAI_API_KEY" not in env
    assert "MILVUS_TOKEN" not in env
    assert env.get("ANTHROPIC_API_KEY") == "claude-auth", "claude auth passes"
    assert "HOME" in env and "PATH" in env


def test_agent_env_operator_extension_and_escape_hatch(monkeypatch) -> None:
    monkeypatch.setenv("MY_SPECIAL_VAR", "v")
    monkeypatch.delenv("AGENT_ENV_PASSTHROUGH_ALL", raising=False)
    monkeypatch.setenv("AGENT_ENV_ALLOWLIST", "MY_SPECIAL_VAR")
    assert claude_agent._agent_env().get("MY_SPECIAL_VAR") == "v"
    monkeypatch.setenv("AGENT_ENV_ALLOWLIST", "")
    assert "MY_SPECIAL_VAR" not in claude_agent._agent_env()
    monkeypatch.setenv("AGENT_ENV_PASSTHROUGH_ALL", "1")
    assert claude_agent._agent_env().get("MY_SPECIAL_VAR") == "v", (
        "escape hatch restores full inheritance"
    )


def test_mcp_server_env_still_carries_retrieval_secrets(tmp_path, monkeypatch) -> None:
    """A52 must NOT break retrieval: the MCP server (not the agent) still
    gets its secrets via the config env."""
    import json as _json
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "sekrit")
    cfg = claude_agent._build_retrieval_mcp_config(None, tmp_path, None,
                                                   tool_budget=30)
    assert cfg is not None
    path, _ = cfg
    try:
        env = _json.loads(path.read_text())["mcpServers"]["retrieval"]["env"]
        assert env.get("AZURE_OPENAI_API_KEY") == "sekrit"
    finally:
        path.unlink()
