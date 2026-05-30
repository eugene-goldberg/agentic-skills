"""ABL-0014 Batch B — B.4: closure_check acceptance-stack extension.

Verifies that ``closure_check`` enumerates surviving acceptance docker
containers (``acceptance-<run_id>*``) and worktrees
(``.agent-worktrees/accept-<run_id>``), reporting them under the new
``by_kind`` keys ``acceptance_docker`` and ``acceptance_worktree``.

Docker is mocked via a fake ``asyncio.create_subprocess_exec`` so the
test runs without requiring a real docker daemon.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import closure_check as cc  # noqa: E402


class _FakeProc:
    def __init__(self, stdout: bytes, returncode: int = 0) -> None:
        self._stdout = stdout
        self.returncode = returncode

    async def communicate(self):
        return self._stdout, b""

    def kill(self) -> None:  # pragma: no cover
        pass


def _fake_create_subprocess_factory(stdout: bytes):
    async def fake(*_args, **_kwargs):
        return _FakeProc(stdout)
    return fake


# ─── acceptance_docker scan ────────────────────────────────────────────────


def test_scan_finds_acceptance_containers() -> None:
    docker_output = (
        b"acceptance-run-x-backend\trunning\tabc123\n"
        b"acceptance-run-x-db\tup 2 hours\tdef456\n"
    )
    with patch.object(asyncio, "create_subprocess_exec",
                       side_effect=_fake_create_subprocess_factory(docker_output)):
        violations = asyncio.run(cc.scan_orphan_acceptance_containers("run-x"))
    assert len(violations) == 2
    kinds = {v.kind for v in violations}
    assert kinds == {"acceptance_docker"}
    names = {v.resource for v in violations}
    assert "acceptance-run-x-backend" in names
    assert "acceptance-run-x-db" in names
    for v in violations:
        assert v.detail["project_prefix"] == "acceptance-run-x"


def test_scan_empty_when_no_containers() -> None:
    with patch.object(asyncio, "create_subprocess_exec",
                       side_effect=_fake_create_subprocess_factory(b"")):
        violations = asyncio.run(cc.scan_orphan_acceptance_containers("run-x"))
    assert violations == []


def test_scan_no_docker_cli_returns_error_violation() -> None:
    async def raises(*_a, **_k):
        raise FileNotFoundError("docker not on PATH")
    with patch.object(asyncio, "create_subprocess_exec", side_effect=raises):
        violations = asyncio.run(cc.scan_orphan_acceptance_containers("run-x"))
    assert len(violations) == 1
    assert violations[0].kind == "closure_check_error"
    assert violations[0].resource == "docker_cli_missing"
    assert violations[0].detail["check"] == "scan_orphan_acceptance_containers"


# ─── acceptance_worktree scan ──────────────────────────────────────────────


def test_scan_finds_acceptance_worktree(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    leaked = repo_root.parent / ".agent-worktrees" / "accept-run-x"
    leaked.mkdir(parents=True)

    violations = cc.scan_stale_acceptance_worktrees(repo_root, "run-x")
    assert len(violations) == 1
    assert violations[0].kind == "acceptance_worktree"
    assert violations[0].detail["basename"] == "accept-run-x"


def test_scan_no_acceptance_worktree(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    violations = cc.scan_stale_acceptance_worktrees(repo_root, "run-x")
    assert violations == []


# ─── scan_all integration: by_kind histogram ──────────────────────────────


def test_scan_all_includes_acceptance_kinds(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root.parent / ".agent-worktrees" / "accept-run-x").mkdir(parents=True)

    docker_output = b"acceptance-run-x-svc\trunning\txyz\n"
    with patch.object(asyncio, "create_subprocess_exec",
                       side_effect=_fake_create_subprocess_factory(docker_output)):
        violations = asyncio.run(cc.scan_all(repo_root, "run-x"))
    kinds = {v.kind for v in violations}
    assert "acceptance_docker" in kinds
    assert "acceptance_worktree" in kinds
