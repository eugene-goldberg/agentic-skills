"""Batch 6 (AUTONOMY_HARDENING_PLAN.md, M1) — within-sprint lesson memory.

The BL-0001-learns-migration-naming → BL-0004-relearns-it-at-full-gate-
price loop closes: resolved retries append to LESSONS.jsonl; subsequent
engineer/QA prompts carry the last N as a paid-for-lessons block.
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import orchestrator as orch  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "PATH": "/usr/bin:/bin"}


def _mk_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    d = repo / "_brownfield" / "features" / "feat"
    d.mkdir(parents=True)
    (d / "BACKLOG.md").write_text(
        "# Backlog: X\n\n"
        "## BL-0001: One\n**Story:** s\n\n"
        "## BL-0002: Two\n**Story:** s\n"
    )
    subprocess.run(["git", "-C", str(repo), "init", "-b", "main"],
                   check=True, capture_output=True)
    (repo / "a.txt").write_text("x")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True,
                   capture_output=True, env=GIT_ENV)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"],
                   check=True, capture_output=True, env=GIT_ENV)
    return repo


# ─── unit: append + block rendering ─────────────────────────────────────────


def test_append_and_block_roundtrip(tmp_path) -> None:
    repo = tmp_path / "r"
    (repo / "_brownfield" / "features" / "feat").mkdir(parents=True)
    orch._append_lesson(repo, "feat", bl_id="BL-0001", role="engineer",
                        phase="gate",
                        failure="build_fail(lint): Sort the imported names",
                        resolved_on_attempt=1)
    block = orch._lessons_block(repo, "feat")
    assert "Lessons already paid for" in block
    assert "[BL-0001/engineer/gate]" in block
    assert "Sort the imported names" in block


def test_block_empty_when_no_lessons(tmp_path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    assert orch._lessons_block(repo, "feat") == ""


def test_block_caps_at_last_n_and_truncates(tmp_path) -> None:
    repo = tmp_path / "r"
    (repo / "_brownfield" / "features" / "feat").mkdir(parents=True)
    for i in range(15):
        orch._append_lesson(repo, "feat", bl_id=f"BL-{i:04d}", role="qa",
                            phase="doctrine", failure="f" * 500,
                            resolved_on_attempt=1)
    block = orch._lessons_block(repo, "feat")
    assert block.count("[BL-") == orch._LESSONS_MAX_INJECTED
    assert "BL-0014" in block and "BL-0004" not in block  # newest N win
    # Field cap applied on write.
    rec = json.loads(orch._lessons_path(repo, "feat").read_text().splitlines()[0])
    assert len(rec["failure"]) == orch._LESSON_FIELD_CAP


def test_append_never_raises_on_bad_dir(tmp_path) -> None:
    # Nonexistent parent chain + unwritable path → silently a no-op.
    orch._append_lesson(tmp_path / "nope" / "deep", None, bl_id="BL-0001",
                        role="engineer", phase="gate", failure="x",
                        resolved_on_attempt=1)


# ─── integration: flows write lessons on resolved retries ───────────────────


def _stub_stream(monkeypatch, prompts: list):
    async def stub(prompt, wt_path, *, timeout_seconds, trace=None,
                   min_pregrounding=0, **rk):
        prompts.append(prompt)
        yield {"type": "_meta", "phase": "spawn"}
        yield {"type": "_meta", "phase": "exit", "exit_code": 0}
    monkeypatch.setattr(orch, "stream_agent_task", stub)


def test_engineer_doctrine_recovery_writes_lesson(tmp_path, monkeypatch) -> None:
    repo = _mk_repo(tmp_path)
    prompts: list = []
    _stub_stream(monkeypatch, prompts)

    calls = {"n": 0}

    def fake_validate(wt_path, bl_id, base_ref=None, retrieval_log=None,
                      feature_slug=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"ok": False, "no_op": False,
                    "summary": "missing eng_patterns.md (R5b citations absent)",
                    "missing": ["eng_patterns.md"]}
        return {"ok": True, "no_op": False, "summary": "complete", "missing": []}

    monkeypatch.setattr(orch.doctrine_svc, "validate_engineer", fake_validate)

    async def fake_gate(*a, **k):
        return {"ok": True, "kind": "green", "reason": "green",
                "regressions": [], "new_failures": [],
                "gate_failure_class": None, "pre_cache_hit": False}
    monkeypatch.setattr(orch.regression_gate_svc, "run_gate", fake_gate)

    async def fake_ff(*a, **k):
        return {"ok": True, "kind": "ff", "merged_sha": "abc123"}
    monkeypatch.setattr(orch, "fast_forward_target", fake_ff)

    async def main():
        events = []
        async for e in orch._engineer_flow(
            repo, "repo", "BL-0001", 60, lambda *a: {},
            run_id="run-x", feature_slug="feat",
        ):
            events.append(e)
        return events

    asyncio.run(main())
    lessons = orch._lessons_path(repo, "feat")
    assert lessons.exists(), "resolved doctrine retry must write a lesson"
    rec = json.loads(lessons.read_text().splitlines()[0])
    assert rec["bl_id"] == "BL-0001"
    assert rec["phase"] == "doctrine"
    assert "eng_patterns" in rec["failure"]
    assert rec["resolved_on_attempt"] == 1


def test_next_bl_prompt_carries_lessons_block(tmp_path, monkeypatch) -> None:
    repo = _mk_repo(tmp_path)
    # Seed a lesson as if BL-0001 already paid for it.
    orch._append_lesson(repo, "feat", bl_id="BL-0001", role="engineer",
                        phase="gate",
                        failure="regressed(test): migration name mismatch workspacemember vs workspace_member",
                        resolved_on_attempt=2)
    prompts: list = []
    _stub_stream(monkeypatch, prompts)
    monkeypatch.setattr(
        orch.doctrine_svc, "validate_engineer",
        lambda *a, **k: {"ok": False, "no_op": False, "summary": "nope",
                         "missing": ["x"]})

    async def main():
        async for _e in orch._engineer_flow(
            repo, "repo", "BL-0002", 60, lambda *a: {},
            run_id="run-x", feature_slug="feat",
        ):
            pass

    asyncio.run(main())
    assert prompts, "engineer spawned"
    assert "Lessons already paid for" in prompts[0], (
        "BL-0002's prompt must carry BL-0001's paid-for lesson (M1)"
    )
    assert "workspacemember vs workspace_member" in prompts[0]


def test_gate_recovery_writes_gate_lesson(tmp_path, monkeypatch) -> None:
    repo = _mk_repo(tmp_path)
    prompts: list = []
    _stub_stream(monkeypatch, prompts)
    monkeypatch.setattr(
        orch.doctrine_svc, "validate_engineer",
        lambda *a, **k: {"ok": True, "no_op": False, "summary": "ok",
                         "missing": []})

    gates = {"n": 0}

    async def fake_gate(*a, **k):
        gates["n"] += 1
        if gates["n"] == 1:
            return {"ok": False, "kind": "build_fail",
                    "gate_failure_class": "lint",
                    "reason": "lint step failed; downstream tests not run",
                    "regressions": [], "new_failures": [],
                    "build_error": "Sort the imported names", "post_tail": ""}
        return {"ok": True, "kind": "green", "reason": "green",
                "regressions": [], "new_failures": [],
                "gate_failure_class": None, "pre_cache_hit": True}
    monkeypatch.setattr(orch.regression_gate_svc, "run_gate", fake_gate)

    async def fake_hnc(wt, base_ref=None):
        return 1
    monkeypatch.setattr(orch, "has_new_commits", fake_hnc)

    async def fake_ff(*a, **k):
        return {"ok": True, "kind": "ff", "merged_sha": "abc123"}
    monkeypatch.setattr(orch, "fast_forward_target", fake_ff)

    async def main():
        async for _e in orch._engineer_flow(
            repo, "repo", "BL-0001", 60, lambda *a: {},
            run_id="run-x", feature_slug="feat",
        ):
            pass

    asyncio.run(main())
    lessons = orch._lessons_path(repo, "feat")
    assert lessons.exists(), "gate recovery must write a lesson"
    rec = json.loads(lessons.read_text().splitlines()[-1])
    assert rec["phase"] == "gate"
    assert "build_fail(lint)" in rec["failure"]
