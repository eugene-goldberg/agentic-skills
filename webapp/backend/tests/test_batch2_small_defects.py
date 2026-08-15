"""Batch 2-4 (AUTONOMY_HARDENING_PLAN.md) — small-defect fixes A54–A57.

- A54: has_new_commits counts from the worktree's recorded base SHA,
  not "HEAD~1" (which merely tested that HEAD has a parent).
- A55: a missing BACKLOG section yields a structured
  `backlog_section_missing` failure, never a literal "None" prompt.
- A56: AGENT_MODEL pins --model and is recorded on the spawn event.
- A57: the harness retrieval kill is a 2x backstop; the MCP server's
  graceful denial (RETRIEVAL_TOOL_BUDGET) is the primary enforcement.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import claude_agent  # noqa: E402
from app.services import orchestrator as orch  # noqa: E402
from app.services.git_worktree import create_worktree, has_new_commits, remove_worktree  # noqa: E402


# ─── A54 ─────────────────────────────────────────────────────────────────────


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                        "PATH": "/usr/bin:/bin"})


def test_a54_has_new_commits_counts_from_base_sha(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "a.txt").write_text("one")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "c1")
    (repo / "a.txt").write_text("two")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "c2")

    async def main():
        wt = await create_worktree(repo, base_ref="main")
        try:
            assert wt.base_sha, "create_worktree must record the base SHA"
            # Zero agent commits → 0 (the old HEAD~1 idiom returned 1 here).
            assert await has_new_commits(wt) == 0
            # Two agent commits → 2 (the old idiom returned 1 here).
            (wt.path / "b.txt").write_text("x")
            _git(wt.path, "add", "-A")
            _git(wt.path, "commit", "-m", "agent1")
            (wt.path / "c.txt").write_text("y")
            _git(wt.path, "add", "-A")
            _git(wt.path, "commit", "-m", "agent2")
            assert await has_new_commits(wt) == 2
        finally:
            await remove_worktree(repo, wt)

    asyncio.run(main())


def test_a54_orchestrator_no_longer_uses_head_tilde_one() -> None:
    src = inspect.getsource(orch)
    assert 'base_ref="HEAD~1"' not in src, (
        "A54: HEAD~1 counts 'HEAD has a parent', not 'agent committed'"
    )


# ─── A55 ─────────────────────────────────────────────────────────────────────


def _write_backlog(repo: Path, feature: str) -> None:
    d = repo / "_brownfield" / "features" / feature
    d.mkdir(parents=True)
    (d / "BACKLOG.md").write_text(
        "# Backlog: X\n\n## BL-0001: Real item\n**Story:** s\n"
    )


def test_a55_engineer_flow_fails_structured_on_missing_section(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _write_backlog(repo, "feat")
    (repo / "x.txt").write_text("x")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")

    async def main():
        events = []
        # BL-0099 has no section in the backlog.
        async for e in orch._engineer_flow(
            repo, "repo", "BL-0099", 60,
            lambda *a: {}, run_id="run-x", feature_slug="feat",
        ):
            events.append(e)
        phases = [e.get("phase") for e in events if e.get("type") == "_meta"]
        assert "backlog_section_missing" in phases
        outcome = next(e for e in events if e.get("_orchestrator_outcome"))
        assert outcome["merged"] is False
        assert outcome["section_missing"] is True
        # No worktree/agent was ever spawned.
        assert "worktree_ready" not in phases

    asyncio.run(main())


def test_a55_qa_flow_fails_structured_on_missing_section(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _write_backlog(repo, "feat")
    (repo / "x.txt").write_text("x")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")

    async def main():
        events = []
        async for e in orch._qa_or_scorer_flow(
            repo, "repo", "BL-0099", "qa", 60,
            lambda *a: {}, run_id="run-x", feature_slug="feat",
        ):
            events.append(e)
        outcome = next(e for e in events if e.get("_orchestrator_outcome"))
        assert outcome["merged"] is False
        assert outcome["doctrine_ok"] is False
        assert outcome["section_missing"] is True

    asyncio.run(main())


# ─── A56 ─────────────────────────────────────────────────────────────────────


def test_a56_agent_model_env_pins_model(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_MODEL", "claude-test-model-1")
    assert claude_agent._agent_model() == "claude-test-model-1"
    monkeypatch.delenv("AGENT_MODEL")
    assert claude_agent._agent_model() is None
    # Source contract: the pin reaches the CLI argv and the spawn event.
    src = inspect.getsource(claude_agent.stream_agent_task)
    assert '"--model", model' in src
    assert '"model": model or "(cli default)"' in src


# ─── A57 ─────────────────────────────────────────────────────────────────────


def test_a57_budget_flows_to_mcp_server_env(tmp_path) -> None:
    cfg = claude_agent._build_retrieval_mcp_config(
        None, tmp_path, None, tool_budget=30,
    )
    assert cfg is not None
    path, _tools = cfg
    try:
        data = json.loads(path.read_text())
        env = data["mcpServers"]["retrieval"]["env"]
        assert env["RETRIEVAL_TOOL_BUDGET"] == "30", (
            "A57: the server budget must mirror max_retrieval_calls"
        )
    finally:
        path.unlink()


def test_a57_harness_kill_is_two_x_backstop() -> None:
    src = inspect.getsource(claude_agent.stream_agent_task)
    assert "max_retrieval_calls * 2" in src, (
        "A57: harness kill must be a 2x backstop behind the server's "
        "graceful denial, not the primary enforcement"
    )
