"""Tests for POST /api/projects/{repo}/init-feature (Option-A).

Validates the runbook-automation endpoint that replaces the manual
RUNBOOK_clean_brownfield_reset.md procedure. Each test sets up an
isolated bare git repo with a master ref, exposes it via REPOS_ROOT,
calls the endpoint, and asserts the post-state of the target repo.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _git(cwd: Path, *args: str) -> str:
    res = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
    )
    return res.stdout.strip()


@pytest.fixture
def target_repo(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """Create a minimal git repo on master, expose under a temp REPOS_ROOT."""
    repos_root = tmp_path / "repos"
    repos_root.mkdir()
    repo = repos_root / "demo-target"
    repo.mkdir()
    _git(repo, "init", "-b", "master")
    (repo / "README.md").write_text("# demo\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "initial")

    # Point the router's REPOS_ROOT at our temp tree.
    import app.routers.projects as projects_mod
    monkeypatch.setattr(projects_mod, "REPOS_ROOT", repos_root)

    return repo, repos_root


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


def test_init_feature_creates_branch_with_harness(target_repo, client):
    repo, _ = target_repo
    r = client.post(
        "/api/projects/demo-target/init-feature",
        json={"feature_name": "Audit Log"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slug"] == "audit-log"
    assert body["agent_branch"] == "audit-log"
    assert body["main_ref"] == "master"
    assert len(body["branch_sha"]) == 40

    # Branch exists and is currently checked out.
    cur = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    assert cur == "audit-log"

    # Harness applied.
    assert (repo / "scripts" / "regression_gate.sh").exists()
    assert (repo / "compose.gate.yml").exists()
    gi = (repo / ".gitignore").read_text()
    assert "graphify-out" in gi
    assert "_brownfield/features/*/events.jsonl" in gi

    # Config written.
    cfg = json.loads((repo / ".agentic-skills.json").read_text())
    assert cfg["agent_branch"] == "audit-log"
    assert cfg["main_ref"] == "master"
    assert cfg["doctrine"] == "brownfield"
    assert cfg["test_cmd"] == ["sh", "scripts/regression_gate.sh"]

    # Feature dir created with .gitkeep so it survives commit.
    feature_dir = repo / "_brownfield" / "features" / "audit-log"
    assert feature_dir.is_dir()
    assert (feature_dir / ".gitkeep").exists()

    # Bootstrap commit present.
    log = _git(repo, "log", "--oneline", "-1")
    assert "audit-log" in log
    assert "bootstrap feature branch" in log


def test_init_feature_refuses_dirty_working_tree(target_repo, client):
    repo, _ = target_repo
    (repo / "uncommitted.txt").write_text("dirty\n")
    r = client.post(
        "/api/projects/demo-target/init-feature",
        json={"feature_name": "Test"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "working_tree_dirty"


def test_init_feature_refuses_existing_branch(target_repo, client):
    repo, _ = target_repo
    _git(repo, "checkout", "-b", "rbac")
    _git(repo, "checkout", "master")
    r = client.post(
        "/api/projects/demo-target/init-feature",
        json={"feature_name": "rbac"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "branch_exists"


def test_init_feature_rejects_invalid_slug(target_repo, client):
    r = client.post(
        "/api/projects/demo-target/init-feature",
        json={"feature_name": "!!!"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "invalid_feature_name"


def test_init_feature_main_ref_override(target_repo, client):
    repo, _ = target_repo
    # Add a second ref to fork from.
    _git(repo, "checkout", "-b", "main")
    (repo / "README.md").write_text("# main\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "main commit")
    _git(repo, "checkout", "master")

    r = client.post(
        "/api/projects/demo-target/init-feature",
        json={"feature_name": "From Main", "main_ref": "main"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["main_ref"] == "main"
    # New branch's parent should be the main commit, not master.
    log = _git(repo, "log", "--oneline", "from-main")
    assert "main commit" in log


def test_init_feature_idempotent_gitignore(target_repo, client):
    repo, _ = target_repo
    # Pre-existing gitignore that already has one of the harness entries.
    (repo / ".gitignore").write_text("# preexisting\ngraphify-out\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "add gitignore")

    r = client.post(
        "/api/projects/demo-target/init-feature",
        json={"feature_name": "billing"},
    )
    assert r.status_code == 200
    gi = (repo / ".gitignore").read_text()
    # graphify-out should appear exactly once; events.jsonl line should be added.
    assert gi.count("graphify-out\n") == 1
    assert "_brownfield/features/*/events.jsonl" in gi
