"""Simple gating model (operator 2026-06-06): per-BL runs ONLY the BL's own
unit tests (its changed test files) — not the full suite, not Playwright.

Tests the `run_bl_tests` scoped runner: BL-test-file detection, the `no_tests`
verdict (doctrine requires per-BL unit tests), and green/failed verdict shaping
via the no-docker fallback path (no compose.* files → direct runner).
"""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import regression_gate as g  # noqa: E402


def test_bl_test_files_detection() -> None:
    changed = [
        "backend/tests/api/routes/test_comments.py",
        "backend/tests/foo_test.py",
        "backend/app/models.py",            # not a test
        "frontend/tests/comments.spec.ts",  # playwright e2e — excluded
        "README.md",
    ]
    assert g._bl_test_files(changed) == [
        "backend/tests/api/routes/test_comments.py",
        "backend/tests/foo_test.py",
    ]


def _patch_cfg(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(g.repo_config_svc, "load",
                        lambda *a, **k: types.SimpleNamespace(
                            agent_branch="agentic-skills-work",
                            test_cmd=["pytest"], doctrine="brownfield"))


def test_run_bl_tests_no_tests(monkeypatch, tmp_path) -> None:
    """A BL that changed no test files → kind=no_tests (engineer must add them)."""
    _patch_cfg(monkeypatch, tmp_path)

    async def _git(args, cwd):
        if args[:2] == ["diff", "--name-only"]:
            return (0, "backend/app/models.py\nbackend/app/crud.py\n")
        return (0, "")
    monkeypatch.setattr(g, "_git", _git)

    res = asyncio.run(g.run_bl_tests(tmp_path, "agent/x", "agentic-skills-work", run_id="r"))
    assert res["kind"] == "no_tests"
    assert res["ok"] is False


def _drive_with_pytest_output(monkeypatch, tmp_path, *, exit_code: int, stdout: str):
    _patch_cfg(monkeypatch, tmp_path)

    async def _git(args, cwd):
        if args[:2] == ["diff", "--name-only"]:
            return (0, "backend/tests/api/test_comments.py\n")
        return (0, "")  # worktree add / remove

    async def _run_capture(cmd, cwd, timeout=1800, env=None):
        return (exit_code, stdout, "")

    monkeypatch.setattr(g, "_git", _git)
    monkeypatch.setattr(g, "_run_capture", _run_capture)
    # tmp_path has no compose.yml/compose.gate.yml → use_compose=False → fallback.
    return asyncio.run(g.run_bl_tests(tmp_path, "agent/x", "agentic-skills-work", run_id="r"))


def test_run_bl_tests_green(monkeypatch, tmp_path) -> None:
    out = ("backend/tests/api/test_comments.py::test_create PASSED\n"
           "backend/tests/api/test_comments.py::test_delete PASSED\n"
           "===== 2 passed in 0.2s =====\n")
    res = _drive_with_pytest_output(monkeypatch, tmp_path, exit_code=0, stdout=out)
    assert res["kind"] == "green"
    assert res["ok"] is True


def test_run_bl_tests_failed(monkeypatch, tmp_path) -> None:
    out = ("backend/tests/api/test_comments.py::test_create PASSED\n"
           "backend/tests/api/test_comments.py::test_delete FAILED\n"
           "===== 1 failed, 1 passed in 0.2s =====\n")
    res = _drive_with_pytest_output(monkeypatch, tmp_path, exit_code=1, stdout=out)
    assert res["kind"] == "failed"
    assert res["ok"] is False
    # exit-code-primary verdict; failures named (node-ids when parseable, else
    # the BL test files) so the retry prompt has actionable detail.
    assert any("test_comments.py" in r for r in res["regressions"])
