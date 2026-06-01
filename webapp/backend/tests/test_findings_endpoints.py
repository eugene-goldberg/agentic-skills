"""Tests for ABL-0014 §I.3 Batch C: findings ledger HTTP endpoints.

Covers GET /api/projects/{repo}/findings and POST /api/projects/{repo}/verdict.

The fixture builds a tmp directory tree that looks like a real repo
(``<tmp>/repos/<repo_name>/`` with a ``.git`` marker), points
``AGENT_REPOS_ROOT`` at it via monkeypatch, and reloads the projects
router module so its ``REPOS_ROOT`` constant picks up the override.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def app_and_repo(tmp_path: Path, monkeypatch):
    """Build a fake REPOS_ROOT, reload the router so it sees the new
    constant, mount it on a minimal FastAPI app, and yield the
    TestClient + on-disk repo dir."""
    # On macOS tmp_path lives under /var which is a symlink to /private/var.
    # _repo_dir() calls .resolve() so we must seed under the resolved path
    # or the endpoint will read a different ledger from the one we wrote.
    repos_root = (tmp_path / "repos").resolve()
    repos_root.mkdir()
    repo_name = "demo"
    repo_dir = (repos_root / repo_name).resolve()
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()  # _repo_dir() requires a .git child

    # Import projects once; monkeypatch the module-level REPOS_ROOT
    # directly. env-var reload would race with pytest's test ordering
    # (an earlier test that imported projects before our env-var set
    # would freeze REPOS_ROOT at its first-import value).
    from app.routers import projects as projects_router  # noqa: WPS433
    monkeypatch.setattr(projects_router, "REPOS_ROOT", repos_root)

    app = FastAPI()
    app.include_router(projects_router.router)
    client = TestClient(app)
    yield client, repo_dir, repo_name


# ─── helpers ──────────────────────────────────────────────────────────────


def _seed_ledger(repo_dir: Path, slug: str, classifications: list[str]) -> list[str]:
    """Append one finding per classification via the ledger module directly
    and return the resulting finding_ids in insertion order."""
    from app.services.findings_ledger import FindingsLedger  # noqa: WPS433

    ledger = FindingsLedger(repo_dir, slug)
    journeys = []
    for n, cls in enumerate(classifications, start=1):
        journeys.append({
            "id": f"j{n:02d}",
            "status": "fail",
            "classification": cls,
            "evidence": f"evidence for {cls} #{n}",
        })
    report = {"api_journeys": journeys}
    persisted = ledger.append_from_report(
        report, run_id="seed-run", report_path="seed.json",
    )
    return [f.finding_id for f in persisted]


# ─── GET /findings ────────────────────────────────────────────────────────


def test_get_findings_empty_ledger_returns_empty_list(app_and_repo):
    client, _repo_dir, repo = app_and_repo
    r = client.get(f"/api/projects/{repo}/findings", params={"feature_slug": "feat_a"})
    assert r.status_code == 200
    assert r.json() == {"findings": [], "count": 0}


def test_get_findings_returns_persisted(app_and_repo):
    client, repo_dir, repo = app_and_repo
    fids = _seed_ledger(repo_dir, "feat_a", ["product_bug", "test_bug"])
    r = client.get(f"/api/projects/{repo}/findings",
                   params={"feature_slug": "feat_a", "status": "all"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    returned_ids = {f["finding_id"] for f in body["findings"]}
    assert returned_ids == set(fids)


def test_get_findings_pending_excludes_verdicted(app_and_repo):
    client, repo_dir, repo = app_and_repo
    fids = _seed_ledger(repo_dir, "feat_a", ["product_bug", "infra_bug"])
    # Verdict the first via the API itself (also exercises POST round-trip).
    r = client.post(
        f"/api/projects/{repo}/verdict",
        json={"feature_slug": "feat_a", "finding_id": fids[0],
              "verdict": "confirmed"},
    )
    assert r.status_code == 200
    # Pending should now only carry the infra_bug.
    r = client.get(f"/api/projects/{repo}/findings",
                   params={"feature_slug": "feat_a"})  # status default = pending
    body = r.json()
    assert body["count"] == 1
    assert body["findings"][0]["classification"] == "infra_bug"


def test_get_findings_bad_status_400(app_and_repo):
    client, _repo_dir, repo = app_and_repo
    r = client.get(f"/api/projects/{repo}/findings",
                   params={"feature_slug": "feat_a", "status": "lolwhat"})
    assert r.status_code == 400


def test_get_findings_bad_slug_400(app_and_repo):
    client, _repo_dir, repo = app_and_repo
    r = client.get(f"/api/projects/{repo}/findings",
                   params={"feature_slug": "../etc/passwd"})
    assert r.status_code == 400
    assert "feature_slug" in r.json()["detail"]


def test_get_findings_unknown_repo_404(app_and_repo):
    client, _repo_dir, _repo = app_and_repo
    r = client.get("/api/projects/no_such_repo/findings",
                   params={"feature_slug": "feat_a"})
    assert r.status_code == 404


# ─── POST /verdict ────────────────────────────────────────────────────────


def test_post_verdict_happy_path(app_and_repo):
    client, repo_dir, repo = app_and_repo
    fids = _seed_ledger(repo_dir, "feat_a", ["product_bug"])
    r = client.post(
        f"/api/projects/{repo}/verdict",
        json={
            "feature_slug": "feat_a",
            "finding_id": fids[0],
            "verdict": "refuted",
            "note": "the test was wrong, fixed selector in PR #99",
        },
    )
    assert r.status_code == 200
    f = r.json()["finding"]
    assert f["verdict"] == "refuted"
    assert f["verdict_ts"] is not None
    assert f["verdict_note"] == "the test was wrong, fixed selector in PR #99"


def test_post_verdict_unknown_finding_id_404(app_and_repo):
    client, repo_dir, repo = app_and_repo
    _seed_ledger(repo_dir, "feat_a", ["product_bug"])
    r = client.post(
        f"/api/projects/{repo}/verdict",
        json={"feature_slug": "feat_a",
              "finding_id": "sha256:" + "0" * 64,
              "verdict": "confirmed"},
    )
    assert r.status_code == 404
    assert "unknown finding_id" in r.json()["detail"]


def test_post_verdict_invalid_enum_422(app_and_repo):
    client, repo_dir, repo = app_and_repo
    fids = _seed_ledger(repo_dir, "feat_a", ["product_bug"])
    r = client.post(
        f"/api/projects/{repo}/verdict",
        json={"feature_slug": "feat_a",
              "finding_id": fids[0],
              "verdict": "wontfix"},  # not in enum
    )
    assert r.status_code == 422


def test_post_verdict_bad_slug_400(app_and_repo):
    client, _repo_dir, repo = app_and_repo
    r = client.post(
        f"/api/projects/{repo}/verdict",
        json={"feature_slug": "../escape",
              "finding_id": "sha256:abc",
              "verdict": "confirmed"},
    )
    assert r.status_code == 400


def test_post_verdict_missing_field_422(app_and_repo):
    client, _repo_dir, repo = app_and_repo
    r = client.post(
        f"/api/projects/{repo}/verdict",
        json={"feature_slug": "feat_a", "verdict": "confirmed"},
        # missing finding_id
    )
    assert r.status_code == 422
