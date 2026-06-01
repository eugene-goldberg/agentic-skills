"""Tests for ABL-0014 Item 1 Batch B: _compute_backend_bls.

Builds a small real git repo with multiple BL-prefixed commits — some
touching backend route files, some touching pure frontend or tests — and
asserts the helper picks out only the BLs whose commits matched the
configured route globs.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import orchestrator as orch  # noqa: E402
from app.services.repo_config import DEFAULT_API_ROUTE_GLOBS  # noqa: E402


# ─── helpers ──────────────────────────────────────────────────────────────


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _write(repo: Path, rel: str, content: str = "x\n") -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def _init_repo_with_baseline(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    _write(repo, "README.md", "baseline\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "baseline")
    return repo


def _commit(repo: Path, subject: str, files: dict[str, str]) -> None:
    for rel, body in files.items():
        _write(repo, rel, body)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", subject)


def _run(coro):
    return asyncio.run(coro)


# ─── tests ────────────────────────────────────────────────────────────────


def test_picks_only_bls_touching_backend_routes(tmp_path: Path) -> None:
    repo = _init_repo_with_baseline(tmp_path)
    _git(repo, "checkout", "-q", "-b", "agent_branch")

    # BL-0001: pure frontend → NOT a backend BL
    _commit(repo, "BL-0001(brownfield): add login page",
            {"frontend/src/login.tsx": "// login\n"})

    # BL-0002: backend route + frontend → backend BL (one route file is enough)
    _commit(repo, "BL-0002(brownfield): client auth backend",
            {"backend/app/api/routes/portal_auth.py": "# auth\n",
             "frontend/src/auth.tsx": "// auth\n"})

    # BL-0003: tests only → NOT a backend BL (tests are excluded)
    _commit(repo, "BL-0003(brownfield): regression tests",
            {"backend/tests/api/routes/test_portal_auth.py": "# t\n"})

    # BL-0004: backend route only → backend BL
    _commit(repo, "BL-0004(brownfield): documents endpoint",
            {"backend/app/api/routes/portal_documents.py": "# docs\n"})

    # Non-BL commit (a fix) — should be ignored
    _commit(repo, "fix(BL-0002): typo", {"README.md": "fix\n"})

    bls, evidence = _run(orch._compute_backend_bls(
        repo, target_ref="main", agent_branch="agent_branch",
        api_route_globs=DEFAULT_API_ROUTE_GLOBS,
    ))
    assert bls == ["BL-0002", "BL-0004"], bls
    assert "BL-0002" in evidence
    assert "BL-0004" in evidence
    assert any("portal_auth.py" in p for p in evidence["BL-0002"])
    assert any("portal_documents.py" in p for p in evidence["BL-0004"])


def test_returns_empty_for_pure_frontend_sprint(tmp_path: Path) -> None:
    repo = _init_repo_with_baseline(tmp_path)
    _git(repo, "checkout", "-q", "-b", "agent_branch")
    _commit(repo, "BL-0001(brownfield): frontend only",
            {"frontend/src/x.tsx": "// x\n"})
    _commit(repo, "BL-0002(brownfield): more frontend",
            {"frontend/src/y.tsx": "// y\n"})
    bls, evidence = _run(orch._compute_backend_bls(
        repo, target_ref="main", agent_branch="agent_branch",
        api_route_globs=DEFAULT_API_ROUTE_GLOBS,
    ))
    assert bls == []
    assert evidence == {}


def test_no_double_listing_when_bl_has_multiple_commits(tmp_path: Path) -> None:
    """A single BL with multiple commits (e.g. fix-up follow-ups) still
    appears once in the output, with merged evidence."""
    repo = _init_repo_with_baseline(tmp_path)
    _git(repo, "checkout", "-q", "-b", "agent_branch")
    _commit(repo, "BL-0006(brownfield): comments backend",
            {"backend/app/api/routes/portal_projects.py": "# comments\n"})
    _commit(repo, "fix(BL-0006): rename helper",
            {"backend/app/api/routes/portal_projects.py": "# comments v2\n"})
    bls, evidence = _run(orch._compute_backend_bls(
        repo, target_ref="main", agent_branch="agent_branch",
        api_route_globs=DEFAULT_API_ROUTE_GLOBS,
    ))
    # "fix(BL-0006):" subject is matched by ^BL-NNNN regex only when the
    # subject starts with BL-NNNN. Our extractor uses ^(BL-\d{4})\b on
    # multi-line mode against the SUBJECT — the "fix(...)" form does NOT
    # start with BL-, so only the original commit counts. That is by
    # design (subject-line convention); BL appears once.
    assert bls == ["BL-0006"]
    assert len(evidence["BL-0006"]) >= 1


def test_evidence_capped_at_five_paths(tmp_path: Path) -> None:
    repo = _init_repo_with_baseline(tmp_path)
    _git(repo, "checkout", "-q", "-b", "agent_branch")
    files = {
        f"backend/app/api/routes/portal_module_{i}.py": f"# m{i}\n"
        for i in range(8)
    }
    _commit(repo, "BL-0010(brownfield): many route files", files)
    bls, evidence = _run(orch._compute_backend_bls(
        repo, target_ref="main", agent_branch="agent_branch",
        api_route_globs=DEFAULT_API_ROUTE_GLOBS,
    ))
    assert bls == ["BL-0010"]
    assert len(evidence["BL-0010"]) == 5  # cap


def test_glob_override_excludes_default_matches(tmp_path: Path) -> None:
    """A target with a different layout overrides DEFAULT_API_ROUTE_GLOBS.

    Uses a custom glob that's specific enough to NOT match the
    default-shaped path (`backend/app/api/routes/x.py`) but does match a
    Django-style `myapp/views/*.py` path.
    """
    repo = _init_repo_with_baseline(tmp_path)
    _git(repo, "checkout", "-q", "-b", "agent_branch")
    # Default-shaped path — would be picked up by DEFAULTS but NOT by the
    # custom glob we'll pass in.
    _commit(repo, "BL-0001(brownfield): default-matching route",
            {"backend/app/api/routes/x.py": "# x\n"})
    # Django-style view path — matches the custom glob.
    _commit(repo, "BL-0002(brownfield): django-style view",
            {"myapp/views/y.py": "# y\n"})

    bls, _ = _run(orch._compute_backend_bls(
        repo, target_ref="main", agent_branch="agent_branch",
        api_route_globs=["myapp/views/*.py"],
    ))
    assert bls == ["BL-0002"]


def test_returns_empty_on_unknown_target_ref(tmp_path: Path) -> None:
    repo = _init_repo_with_baseline(tmp_path)
    bls, evidence = _run(orch._compute_backend_bls(
        repo, target_ref="this-ref-does-not-exist",
        agent_branch="main",
        api_route_globs=DEFAULT_API_ROUTE_GLOBS,
    ))
    # git log on a bad ref errors out — helper swallows + returns empty.
    assert bls == []
    assert evidence == {}


def test_acceptance_prompt_includes_backend_bls_block(tmp_path: Path) -> None:
    """When backend_bls is non-empty, the agent prompt's API Acceptance
    block names every BL and at least one cited route file."""
    prompt = orch._build_acceptance_task(
        "FAKE SKILL BODY",
        run_id="run-test",
        feature_slug="demo",
        brief_rel="_brownfield/features/demo/brief.md",
        backlog_rel="_brownfield/features/demo/BACKLOG.md",
        acceptance_rel="_brownfield/features/demo/acceptance",
        compose_project="acceptance-run-test",
        attempt=1,
        backend_bls=["BL-0006", "BL-0007"],
        backend_bl_evidence={
            "BL-0006": ["backend/app/api/routes/portal_projects.py"],
            "BL-0007": ["backend/app/api/routes/portal_documents.py"],
        },
    )
    assert "# API Acceptance — REQUIRED for this sprint" in prompt
    assert "BL-0006" in prompt
    assert "BL-0007" in prompt
    assert "portal_projects.py" in prompt
    assert "portal_documents.py" in prompt
    # Final summary contract extended:
    assert "api_journeys_planned" in prompt


def test_acceptance_prompt_empty_block_for_pure_frontend(tmp_path: Path) -> None:
    """When backend_bls is an empty list (caller computed zero), the
    prompt tells the agent to emit api_journeys: [] explicitly."""
    prompt = orch._build_acceptance_task(
        "FAKE SKILL BODY",
        run_id="run-test",
        feature_slug="demo",
        brief_rel="_brownfield/features/demo/brief.md",
        backlog_rel="_brownfield/features/demo/BACKLOG.md",
        acceptance_rel="_brownfield/features/demo/acceptance",
        compose_project="acceptance-run-test",
        attempt=1,
        backend_bls=[],
    )
    assert "# API Acceptance — not required this sprint" in prompt
    assert "api_journeys: []" in prompt


def test_acceptance_prompt_omits_block_when_backend_bls_none(tmp_path: Path) -> None:
    """When backend_bls is None (legacy caller / pre-Batch-B), no API
    block appears — preserves backward compat with the pre-Item-1 prompt
    shape exactly."""
    prompt = orch._build_acceptance_task(
        "FAKE SKILL BODY",
        run_id="run-test",
        feature_slug="demo",
        brief_rel="_brownfield/features/demo/brief.md",
        backlog_rel="_brownfield/features/demo/BACKLOG.md",
        acceptance_rel="_brownfield/features/demo/acceptance",
        compose_project="acceptance-run-test",
        attempt=1,
        backend_bls=None,
    )
    assert "# API Acceptance" not in prompt
