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
                            test_cmd=["pytest"], test_env=None,
                            doctrine="brownfield"))


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


def test_run_bl_tests_multitoken_cmd_and_env(monkeypatch, tmp_path) -> None:
    """A57: a target whose test_cmd is multi-token (e.g. `uv run pytest`) and
    needs env (DATABASE_URL/HABITS_STORAGE) must run with the FULL command —
    not just test_cmd[0] — and with test_env merged into the subprocess.

    Regression guard for the beaverhabits wiring: the native run_bl_tests path
    previously kept only `test_cmd[0]`, silently dropping `run pytest`, and had
    no path to inject per-target env.
    """
    captured: dict = {}

    monkeypatch.setattr(g.repo_config_svc, "load",
                        lambda *a, **k: types.SimpleNamespace(
                            agent_branch="integration",
                            test_cmd=["uv", "run", "pytest"],
                            test_env={"DATABASE_URL": "sqlite+aiosqlite:///:memory:",
                                      "HABITS_STORAGE": "USER_DISK"},
                            doctrine="brownfield"))

    async def _git(args, cwd):
        if args[:2] == ["diff", "--name-only"]:
            return (0, "tests/test_apis.py\n")
        return (0, "")
    monkeypatch.setattr(g, "_git", _git)

    async def _run_capture(cmd, cwd, timeout=1800, env=None):
        captured["cmd"] = cmd
        captured["env"] = env
        return (0, "tests/test_apis.py::test_create PASSED\n== 1 passed ==\n", "")
    monkeypatch.setattr(g, "_run_capture", _run_capture)

    res = asyncio.run(g.run_bl_tests(tmp_path, "agent/x", "integration", run_id="r"))
    assert res["kind"] == "green"
    # FULL command preserved (not truncated to test_cmd[0]), -v inserted, BL file appended.
    assert captured["cmd"] == ["uv", "run", "pytest", "-v", "tests/test_apis.py"]
    # Per-target env reached the subprocess.
    assert captured["env"] == {"DATABASE_URL": "sqlite+aiosqlite:///:memory:",
                               "HABITS_STORAGE": "USER_DISK"}


# --- D9: language-agnostic per-BL test scoping ------------------------------

def test_bl_test_files_cross_language() -> None:
    """The per-BL gate must recognize a BL's unit tests whatever the stack is —
    not just Python. .NET *Tests.cs, go *_test.go, JUnit *Test.java, vitest
    *.test.ts all count; Playwright/e2e specs and non-test sources do not."""
    changed = [
        "backend/tests/api/test_comments.py",                       # py  ✓
        "backend/Ecommerce.Tests/src/Service/OrderServiceTests.cs",  # .NET ✓
        "backend/Ecommerce.Service/src/OrderService/OrderManagement.cs",  # .cs prod ✗
        "pkg/store/store_test.go",                                  # go  ✓
        "src/main/java/com/x/FooTest.java",                         # java ✓
        "frontend/src/utils/format.test.ts",                       # vitest unit ✓
        "frontend/e2e/checkout.spec.ts",                           # playwright .spec ✗
        "frontend/tests/comments.spec.ts",                         # .spec (Cypress/PW) ✗
        "README.md",                                               # ✗
    ]
    got = g._bl_test_files(changed)
    assert "backend/tests/api/test_comments.py" in got
    assert "backend/Ecommerce.Tests/src/Service/OrderServiceTests.cs" in got
    assert "pkg/store/store_test.go" in got
    assert "src/main/java/com/x/FooTest.java" in got
    assert "frontend/src/utils/format.test.ts" in got
    # production .cs and docs are not tests
    assert "backend/Ecommerce.Service/src/OrderService/OrderManagement.cs" not in got
    assert "README.md" not in got
    # `.spec.*` is excluded everywhere (Playwright/Cypress convention → acceptance phase)
    assert "frontend/e2e/checkout.spec.ts" not in got
    assert "frontend/tests/comments.spec.ts" not in got


def test_bl_test_files_globs_override() -> None:
    """An explicit test_file_globs in .agentic-skills.json overrides the
    built-in conventions entirely (fnmatch on full path or bare filename)."""
    changed = [
        "backend/Ecommerce.Tests/src/Service/OrderServiceTests.cs",
        "backend/Ecommerce.Service/src/OrderService/OrderManagement.cs",
        "weird/CustomChecks.verify",
    ]
    got = g._bl_test_files(changed, ["*.verify", "*Tests.cs"])
    assert got == [
        "backend/Ecommerce.Tests/src/Service/OrderServiceTests.cs",
        "weird/CustomChecks.verify",
    ]


def _patch_cfg_dotnet(monkeypatch) -> None:
    monkeypatch.setattr(g.repo_config_svc, "load",
                        lambda *a, **k: types.SimpleNamespace(
                            agent_branch="integration",
                            test_cmd=["dotnet", "test", "backend/Ecommerce.sln", "--nologo"],
                            test_env=None, doctrine="brownfield",
                            test_file_globs=None))


def test_run_bl_tests_dotnet_runs_suite_as_is(monkeypatch, tmp_path) -> None:
    """A non-pytest runner (dotnet test) must NOT have changed source-file paths
    appended (the runner would reject `.cs` paths) and must NOT get a `-v`
    pytest flag. The BL still gated on its tests' presence; verdict from exit
    code (dotnet output isn't pytest-parseable)."""
    _patch_cfg_dotnet(monkeypatch)
    captured: dict = {}

    async def _git(args, cwd):
        if args[:2] == ["diff", "--name-only"]:
            return (0, "backend/Ecommerce.Tests/src/Service/OrderServiceTests.cs\n")
        return (0, "")
    monkeypatch.setattr(g, "_git", _git)

    async def _run_capture(cmd, cwd, timeout=1800, env=None):
        captured["cmd"] = cmd
        return (0, "Passed!  - Failed: 0, Passed: 75, Total: 75\n", "")
    monkeypatch.setattr(g, "_run_capture", _run_capture)

    res = asyncio.run(g.run_bl_tests(tmp_path, "agent/x", "integration", run_id="r"))
    assert res["kind"] == "green"
    assert res["ok"] is True
    # configured command run verbatim — no -v, no appended .cs path
    assert captured["cmd"] == ["dotnet", "test", "backend/Ecommerce.sln", "--nologo"]
    assert "-v" not in captured["cmd"]
    assert not any(c.endswith(".cs") for c in captured["cmd"])


def test_run_bl_tests_dotnet_failed_names_bl_files(monkeypatch, tmp_path) -> None:
    """On a non-pytest failure (exit!=0, unparseable output) the verdict is
    failed and the BL's changed test files are named for the retry prompt."""
    _patch_cfg_dotnet(monkeypatch)

    async def _git(args, cwd):
        if args[:2] == ["diff", "--name-only"]:
            return (0, "backend/Ecommerce.Tests/src/Service/OrderServiceTests.cs\n")
        return (0, "")
    monkeypatch.setattr(g, "_git", _git)

    async def _run_capture(cmd, cwd, timeout=1800, env=None):
        return (1, "Failed!  - Failed: 2, Passed: 73, Total: 75\n", "")
    monkeypatch.setattr(g, "_run_capture", _run_capture)

    res = asyncio.run(g.run_bl_tests(tmp_path, "agent/x", "integration", run_id="r"))
    assert res["kind"] == "failed"
    assert res["ok"] is False
    assert any("OrderServiceTests.cs" in r for r in res["regressions"])
