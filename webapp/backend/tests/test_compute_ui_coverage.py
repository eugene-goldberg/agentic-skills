"""Tests for ABL-0014 Item 2 Batch C: _compute_ui_coverage.

Builds a small git repo with mixed UI/backend/backend-only BL commits
and asserts the helper produces an accurate UI-coverage breakdown.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import orchestrator as orch  # noqa: E402
from app.services.repo_config import DEFAULT_UI_GLOBS  # noqa: E402


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _write(repo: Path, rel: str, content: str = "x\n") -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    _write(repo, "README.md", "baseline\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "baseline")
    _git(repo, "checkout", "-q", "-b", "agent")
    return repo


def _commit(repo: Path, subject: str, files: dict[str, str]) -> None:
    for rel, body in files.items():
        _write(repo, rel, body)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", subject)


def _run(coro):
    return asyncio.run(coro)


# ─── tests ────────────────────────────────────────────────────────────────


def test_full_ui_coverage_when_every_bl_touches_ui(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit(repo, "BL-0001(brownfield): login page",
            {"frontend/src/login.tsx": "// l\n"})
    _commit(repo, "BL-0002(brownfield): dashboard",
            {"frontend/src/dashboard.tsx": "// d\n"})
    result = _run(orch._compute_ui_coverage(
        repo, target_ref="main", agent_branch="agent",
        ui_globs=DEFAULT_UI_GLOBS,
        merged_bl_ids=["BL-0001", "BL-0002"],
    ))
    assert result["merged_total"] == 2
    assert result["ui_bls"] == ["BL-0001", "BL-0002"]
    assert result["backend_only"] == []
    assert result["ratio"] == 1.0


def test_partial_coverage_when_backend_only_bls_present(tmp_path: Path) -> None:
    """Reproduces the Client_Portal sprint's BL-0010-only-UI pattern."""
    repo = _init_repo(tmp_path)
    # 4 backend-only BLs + 1 UI BL = 1/5 = 0.20 ratio
    _commit(repo, "BL-0006(brownfield): comments backend",
            {"backend/app/api/routes/portal_projects.py": "# c\n"})
    _commit(repo, "BL-0007(brownfield): documents backend",
            {"backend/app/api/routes/portal_documents.py": "# d\n"})
    _commit(repo, "BL-0008(brownfield): support backend",
            {"backend/app/api/routes/portal_support.py": "# s\n"})
    _commit(repo, "BL-0009(brownfield): branding backend",
            {"backend/app/api/routes/portal_branding.py": "# b\n"})
    _commit(repo, "BL-0010(brownfield): portal frontend shell",
            {"frontend/src/routes/portal/login.tsx": "// login\n"})
    result = _run(orch._compute_ui_coverage(
        repo, target_ref="main", agent_branch="agent",
        ui_globs=DEFAULT_UI_GLOBS,
        merged_bl_ids=["BL-0006", "BL-0007", "BL-0008", "BL-0009", "BL-0010"],
    ))
    assert result["merged_total"] == 5
    assert result["ui_bls"] == ["BL-0010"]
    assert result["backend_only"] == ["BL-0006", "BL-0007", "BL-0008", "BL-0009"]
    assert abs(result["ratio"] - 0.2) < 1e-9
    assert "frontend/src/routes/portal/login.tsx" in result["evidence"]["BL-0010"]


def test_bl_touching_both_counts_as_ui(tmp_path: Path) -> None:
    """A BL whose commit touches BOTH backend AND frontend is UI-covered
    (it has user-reachable surface), even though it's also a backend BL."""
    repo = _init_repo(tmp_path)
    _commit(repo, "BL-0001(brownfield): full-stack feature",
            {
                "backend/app/api/routes/x.py": "# x\n",
                "frontend/src/x.tsx": "// x\n",
            })
    result = _run(orch._compute_ui_coverage(
        repo, target_ref="main", agent_branch="agent",
        ui_globs=DEFAULT_UI_GLOBS,
        merged_bl_ids=["BL-0001"],
    ))
    assert result["ui_bls"] == ["BL-0001"]
    assert result["backend_only"] == []
    assert result["ratio"] == 1.0


def test_unmerged_bls_ignored(tmp_path: Path) -> None:
    """Commits exist for BL-0003 but operator filters it out via
    merged_bl_ids — only merged BLs are counted in the ratio."""
    repo = _init_repo(tmp_path)
    _commit(repo, "BL-0001(brownfield): login",
            {"frontend/src/login.tsx": "// l\n"})
    _commit(repo, "BL-0002(brownfield): backend",
            {"backend/app/api/routes/x.py": "# x\n"})
    _commit(repo, "BL-0003(brownfield): partial — should be excluded",
            {"frontend/src/halfdone.tsx": "// h\n"})
    result = _run(orch._compute_ui_coverage(
        repo, target_ref="main", agent_branch="agent",
        ui_globs=DEFAULT_UI_GLOBS,
        merged_bl_ids=["BL-0001", "BL-0002"],  # BL-0003 absent
    ))
    assert result["merged_total"] == 2
    assert result["ui_bls"] == ["BL-0001"]
    assert result["backend_only"] == ["BL-0002"]
    assert result["ratio"] == 0.5


def test_tests_only_does_not_count_as_ui(tmp_path: Path) -> None:
    """A BL whose only frontend touch is a *.tsx UNDER /tests/ is NOT
    counted as UI-covered. Same exclusion rule as backend_bls."""
    repo = _init_repo(tmp_path)
    _commit(repo, "BL-0001(brownfield): test-only frontend",
            {"frontend/tests/foo.spec.tsx": "// test\n"})
    _commit(repo, "BL-0002(brownfield): real UI",
            {"frontend/src/foo.tsx": "// foo\n"})
    result = _run(orch._compute_ui_coverage(
        repo, target_ref="main", agent_branch="agent",
        ui_globs=DEFAULT_UI_GLOBS,
        merged_bl_ids=["BL-0001", "BL-0002"],
    ))
    assert result["ui_bls"] == ["BL-0002"]
    assert result["backend_only"] == ["BL-0001"]


def test_empty_merged_returns_zero_ratio(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    result = _run(orch._compute_ui_coverage(
        repo, target_ref="main", agent_branch="agent",
        ui_globs=DEFAULT_UI_GLOBS,
        merged_bl_ids=[],
    ))
    assert result["merged_total"] == 0
    assert result["ratio"] == 0.0


def test_graceful_on_unknown_target_ref(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    result = _run(orch._compute_ui_coverage(
        repo, target_ref="bad-ref", agent_branch="agent",
        ui_globs=DEFAULT_UI_GLOBS,
        merged_bl_ids=["BL-0001"],
    ))
    # Best-effort: ratio=0.0, backend_only includes all supplied ids.
    assert result["merged_total"] == 1
    assert result["ratio"] == 0.0
    assert result["backend_only"] == ["BL-0001"]
