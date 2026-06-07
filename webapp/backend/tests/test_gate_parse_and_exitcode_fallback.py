"""Item #1 fix (2026-06-07): pytest parse + run_gate exit-code fallback.

Two complementary fixes so a CORRECT change isn't blocked:

1. `_parse_pytest` / `PYTEST_RESULT_RE` now accept an optional directory prefix
   before the `tests/` segment, so node-ids like `backend/tests/test_x.py::test_y`
   parse (the prior `^tests?/` anchor matched ZERO when pytest runs from the repo
   root, e.g. `pytest backend/tests`). Backward-compatible with bare `tests/…`.

2. `_run_gate_once` falls back to exit-code authority when the suite exits clean
   (raw_exit == 0) but emits no parseable per-test lines (e.g. a `-q` test_cmd).
   pytest exit 0 == all collected tests passed, so the gate returns `green`
   instead of `inconclusive` (which previously blocked the acceptance
   regression_checkpoint on the project-management-app target).
"""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import regression_gate as g  # noqa: E402
from app.services.regression_gate import _parse_pytest  # noqa: E402


# ── 1. parser anchor ──────────────────────────────────────────────────────────

def test_parse_pytest_accepts_backend_prefix() -> None:
    out = (
        "backend/tests/test_x.py::test_a PASSED [ 10%]\n"
        "backend/tests/test_y.py::test_b FAILED [ 20%]\n"
    )
    passed, failed = _parse_pytest(out, "")
    assert "backend/tests/test_x.py::test_a" in passed
    assert "backend/tests/test_y.py::test_b" in failed


def test_parse_pytest_still_parses_bare_tests_prefix() -> None:
    passed, failed = _parse_pytest("tests/test_z.py::test_c PASSED\n", "")
    assert "tests/test_z.py::test_c" in passed
    assert not failed


def test_parse_pytest_nested_prefix() -> None:
    passed, _ = _parse_pytest("services/api/tests/test_q.py::test_d PASSED\n", "")
    assert "services/api/tests/test_q.py::test_d" in passed


# ── 2. run_gate exit-code fallback ────────────────────────────────────────────

def _patch_gate(monkeypatch, *, pre: g.TestSet, post: g.TestSet) -> None:
    """Mock the heavy collaborators of _run_gate_once so only the kind-decision
    logic is exercised. test_cmd uses an absolute path so the PATH check is
    skipped; agent_branch != 'main' so the greenfield skip does not fire."""
    monkeypatch.setattr(g.repo_config_svc, "load",
                        lambda *a, **k: types.SimpleNamespace(
                            test_cmd=["/abs/.venv/bin/pytest", "backend/tests", "-q"],
                            agent_branch="integration"))
    monkeypatch.setattr(g, "_free_gb", lambda *a, **k: 999.0)

    async def _git(args, cwd=None):
        return 0, ""  # rev-parse / worktree add / merge / cleanup all succeed

    results = iter([pre, post])

    async def _run_tests(cwd, cmd, **k):
        return next(results)

    monkeypatch.setattr(g, "_git", _git)
    monkeypatch.setattr(g, "_run_tests", _run_tests)


def _run(monkeypatch, pre: g.TestSet, post: g.TestSet) -> dict:
    _patch_gate(monkeypatch, pre=pre, post=post)
    return asyncio.run(
        g._run_gate_once(Path("/tmp/repo"), "integration", "main", run_id="run-x"))


def test_unparseable_but_exit0_is_green_not_inconclusive(monkeypatch) -> None:
    """The bug: -q output → 0 parsed → was `inconclusive`. Now exit 0 → green."""
    empty0 = g.TestSet(passed=set(), failed=set(), raw_exit=0, raw_tail="111 passed in 1.6s")
    res = _run(monkeypatch, pre=empty0, post=empty0)
    assert res["kind"] == "green", res
    assert res["ok"] is True
    assert "exit code" in res["reason"].lower()


def test_unparseable_nonzero_exit_is_not_green(monkeypatch) -> None:
    """The fallback must NOT mask a real failure: clean-parse-but-nonzero stays
    inconclusive/regressed, never green."""
    pre = g.TestSet(passed=set(), failed=set(), raw_exit=0, raw_tail="ok")
    post = g.TestSet(passed=set(), failed=set(), raw_exit=1, raw_tail="boom")
    res = _run(monkeypatch, pre=pre, post=post)
    assert res["kind"] != "green", res
    assert res["ok"] is False


def test_parsed_regression_still_detected(monkeypatch) -> None:
    """With the wider regex, a genuinely regressed test (passing pre, gone post)
    is still caught — the fallback only applies when NOTHING parses."""
    pre = g.TestSet(passed={"backend/tests/t.py::a", "backend/tests/t.py::b"},
                    failed=set(), raw_exit=0, raw_tail="")
    post = g.TestSet(passed={"backend/tests/t.py::a"}, failed=set(),
                     raw_exit=1, raw_tail="1 failed")
    res = _run(monkeypatch, pre=pre, post=post)
    assert res["kind"] == "regressed", res
    assert res["ok"] is False
