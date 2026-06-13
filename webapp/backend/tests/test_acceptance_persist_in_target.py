"""Acceptance evidence must persist PERMANENTLY in-target (operator 2026-06-13).

_persist_acceptance_in_target copies the worktree acceptance tree into the real
checkout under _brownfield/features/<slug>/acceptance/ and commits it on the
current (agent) branch, so journeys/screenshots/api-logs/report travel with the
feature — not only in the ephemeral harness-side traces_archive.
"""
import subprocess
from pathlib import Path

from app.services.orchestrator import _persist_acceptance_in_target as persist


def _git(repo: Path, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "target"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "README").write_text("x")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    return repo


def test_persists_and_commits_in_target(tmp_path: Path):
    repo = _init_repo(tmp_path)
    slug = "ecommerce-reviews"
    feature_dir = repo / "_brownfield" / "features" / slug
    # ledger already written in-target by the orchestrator:
    (feature_dir / "acceptance").mkdir(parents=True)
    (feature_dir / "acceptance" / "findings_log.jsonl").write_text('{"f":1}\n')
    # worktree acceptance evidence the agent produced:
    wt = tmp_path / "wt_acceptance"
    (wt / "screenshots" / "j1").mkdir(parents=True)
    (wt / "screenshots" / "j1" / "step_01.png").write_bytes(b"\x89PNG")
    (wt / "report.json").write_text('{"ac_coverage":[]}')
    (wt / "fixtures" / "api_logs").mkdir(parents=True)
    (wt / "fixtures" / "api_logs" / "j1.jsonl").write_text('{"status":401}\n')

    res = persist(wt, feature_dir, repo, run_id="run-X", feature_slug=slug)

    assert res["ok"] is True
    assert res["committed"] is True, res["reason"]
    # evidence copied into the real target tree
    assert (feature_dir / "acceptance" / "report.json").exists()
    assert (feature_dir / "acceptance" / "screenshots" / "j1" / "step_01.png").exists()
    assert (feature_dir / "acceptance" / "fixtures" / "api_logs" / "j1.jsonl").exists()
    # the pre-existing ledger is preserved (merge, not replace)
    assert (feature_dir / "acceptance" / "findings_log.jsonl").read_text() == '{"f":1}\n'
    # and the evidence is tracked/committed on the branch
    tracked = _git(repo, "ls-files", f"_brownfield/features/{slug}/acceptance").stdout
    assert "report.json" in tracked
    assert "step_01.png" in tracked
    assert "j1.jsonl" in tracked
    log = _git(repo, "log", "--oneline", "-1").stdout
    assert "persist results (run run-X)" in log


def test_missing_worktree_dir_is_noop(tmp_path: Path):
    repo = _init_repo(tmp_path)
    res = persist(tmp_path / "nope", repo / "_brownfield" / "features" / "f",
                  repo, run_id="r", feature_slug="f")
    assert res["ok"] is False
    assert "no acceptance dir" in res["reason"]


def test_only_acceptance_pathspec_committed(tmp_path: Path):
    """Committing must be scoped to the acceptance dir — unrelated dirty files stay uncommitted."""
    repo = _init_repo(tmp_path)
    slug = "f"
    feature_dir = repo / "_brownfield" / "features" / slug
    (feature_dir / "acceptance").mkdir(parents=True)
    (repo / "unrelated_dirty.txt").write_text("should NOT be committed")  # untracked, outside pathspec
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / "report.json").write_text("{}")

    res = persist(wt, feature_dir, repo, run_id="r", feature_slug=slug)
    assert res["committed"] is True
    # unrelated file remains untracked (not swept into the acceptance commit)
    status = _git(repo, "status", "--porcelain").stdout
    assert "unrelated_dirty.txt" in status  # still untracked/uncommitted
