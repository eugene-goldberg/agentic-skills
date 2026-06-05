"""Regression test for the R11 false-no-op defect (team-calendar-horizon
BL-0001, 2026-06-05).

A pre-grounding/Tier-1.5-killed engineer writes ``eng_patterns.md`` to the
worktree but commits NO code. The old no-op check used working-tree existence
(`artifact_path.exists()`), so it misread that as a legitimate "work already
satisfied upstream" no-op and silently skipped the BL — fatal for a foundation
BL that everything else depends on.

The fix requires the artifact to be COMMITTED at HEAD (`git cat-file -e
HEAD:<rel>`). These tests prove the discrimination:
  - legit no-op (artifact committed, zero diff) → no_op=True  (preserved)
  - false no-op (artifact uncommitted in worktree) → NOT no_op (bug fixed)
  - net-new BL (no artifact at all)             → NOT no_op
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.doctrine_validator import (  # noqa: E402
    feature_artifact_dir,
    validate_engineer,
)

FEATURE = "feat-a"
BL = "BL-0001"


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=repo, check=True,
                       capture_output=True, text=True)
    return r.stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "README.md").write_text("base\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    return repo


def _artifact_path(repo: Path) -> Path:
    return repo / feature_artifact_dir(repo, FEATURE) / BL / "eng_patterns.md"


def _write_artifact(repo: Path) -> Path:
    p = _artifact_path(repo)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# eng patterns\n\nMatched `app/foo.py` per semantic_search.\n" * 5)
    return p


def test_legit_noop_committed_artifact_zero_diff(tmp_path: Path) -> None:
    """Inherited work: artifact COMMITTED at HEAD, zero diff vs base → no_op."""
    repo = _init_repo(tmp_path)
    _write_artifact(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "inherited eng_patterns")
    base_ref = _git(repo, "rev-parse", "HEAD")  # base == HEAD, artifact committed
    result = validate_engineer(repo, BL, base_ref=base_ref,
                               retrieval_log=None, feature_slug=FEATURE)
    assert result.get("no_op") is True, result
    assert result["ok"] is True


def test_false_noop_uncommitted_artifact_is_not_noop(tmp_path: Path) -> None:
    """THE BUG: killed engineer wrote eng_patterns.md to the worktree but
    committed nothing. Working-tree file exists, committed diff is empty — must
    NOT be classified no_op (so the orchestrator retries → engineer_unmerged)."""
    repo = _init_repo(tmp_path)
    base_ref = _git(repo, "rev-parse", "HEAD")  # base has NO artifact
    _write_artifact(repo)  # written to worktree, NOT committed
    result = validate_engineer(repo, BL, base_ref=base_ref,
                               retrieval_log=None, feature_slug=FEATURE)
    assert result.get("no_op") is not True, result
    assert result["ok"] is False, result


def test_net_new_bl_no_artifact_is_not_noop(tmp_path: Path) -> None:
    """Foundation BL of a fresh feature: no artifact anywhere, zero diff.
    Must not be a no_op."""
    repo = _init_repo(tmp_path)
    base_ref = _git(repo, "rev-parse", "HEAD")
    result = validate_engineer(repo, BL, base_ref=base_ref,
                               retrieval_log=None, feature_slug=FEATURE)
    assert result.get("no_op") is not True, result
    assert result["ok"] is False, result
