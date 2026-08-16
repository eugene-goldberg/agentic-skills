"""Batch 5 (AUTONOMY_HARDENING_PLAN.md, C5) — economics.

- 5-2 (A29): PRE-baseline cache — second gate against an unchanged
  target skips the PRE run entirely (`pre_cache_hit`), a merge moves the
  SHA and invalidates, unhealthy baselines are never cached.
- 5-3: cost aggregation — result-frame `total_cost_usd` accumulates into
  `bl.done cost_usd` and `sprint_complete total_cost_usd`/`cost_by_role`.
- 5-4: `max_sprint_usd` — over-cap BLs defer honestly (`deferred_budget`),
  checked between BLs only.
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import orchestrator as orch  # noqa: E402
from app.services import regression_gate as rg  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "PATH": "/usr/bin:/bin"}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, env=GIT_ENV)


# ─── 5-2: PRE-baseline cache ────────────────────────────────────────────────


def _gate_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "target"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-b", "main"],
                   check=True, capture_output=True)
    (repo / ".agentic-skills.json").write_text(json.dumps(
        {"agent_branch": "work", "main_ref": "main", "test_cmd": ["echo", "run"]}))
    (repo / "a.txt").write_text("x")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    _git(repo, "branch", "work")
    _git(repo, "checkout", "-b", "agent/abc", "work")
    (repo / "b.txt").write_text("y")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "BL-0001 change")
    _git(repo, "checkout", "main")
    return repo


def _patch_run_tests(monkeypatch, calls: list):
    async def fake_run_tests(cwd, cmd, *, compose_project=None):
        calls.append(str(cwd))
        return rg.TestSet(passed={"tests/t.py::test_a"}, failed=set(),
                          raw_exit=0, raw_tail="tests/t.py::test_a PASSED")
    monkeypatch.setattr(rg, "_run_tests", fake_run_tests)


def test_pre_cache_hit_skips_pre_run(tmp_path, monkeypatch) -> None:
    repo = _gate_repo(tmp_path)
    calls: list = []
    _patch_run_tests(monkeypatch, calls)

    async def main():
        r1 = await rg.run_gate(repo, agent_branch="agent/abc", target_ref="work")
        assert r1["kind"] == "green" and r1["pre_cache_hit"] is False
        n_after_first = len(calls)
        assert n_after_first == 2, "first gate runs PRE + POST"
        r2 = await rg.run_gate(repo, agent_branch="agent/abc", target_ref="work")
        assert r2["kind"] == "green"
        assert r2["pre_cache_hit"] is True, "unchanged target → cache hit"
        assert len(calls) == n_after_first + 1, "second gate runs POST only"
        assert r2["pre"] == r1["pre"], "cached baseline identical"

    asyncio.run(main())


def test_pre_cache_invalidated_by_target_merge(tmp_path, monkeypatch) -> None:
    repo = _gate_repo(tmp_path)
    calls: list = []
    _patch_run_tests(monkeypatch, calls)

    async def main():
        await rg.run_gate(repo, agent_branch="agent/abc", target_ref="work")
        # A merge lands on the target branch → SHA moves → cache miss.
        _git(repo, "checkout", "work")
        (repo / "c.txt").write_text("z")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "BL-0000 landed")
        _git(repo, "checkout", "main")
        # Recreate agent branch off the new tip so the FF dry-run works.
        _git(repo, "branch", "-f", "agent/abc", "work")
        calls.clear()
        r = await rg.run_gate(repo, agent_branch="agent/abc", target_ref="work")
        assert r["pre_cache_hit"] is False, "moved SHA must invalidate"
        assert len(calls) == 2

    asyncio.run(main())


def test_unhealthy_baseline_is_never_cached(tmp_path, monkeypatch) -> None:
    repo = _gate_repo(tmp_path)
    calls: list = []

    async def infra_run_tests(cwd, cmd, *, compose_project=None):
        calls.append(str(cwd))
        return rg.TestSet(passed=set(), failed=set(), raw_exit=1,
                          raw_tail="No space left on device")
    monkeypatch.setattr(rg, "_run_tests", infra_run_tests)

    async def main():
        await rg.run_gate(repo, agent_branch="agent/abc", target_ref="work")
        cache_files = list(rg._pre_cache_dir(repo).glob("pre-*.json")) \
            if rg._pre_cache_dir(repo).exists() else []
        assert cache_files == [], "an infra-poisoned baseline must not be cached"

    asyncio.run(main())


def test_pre_cache_store_load_roundtrip_and_ttl(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path / "r"
    repo_root.mkdir()
    ts = rg.TestSet(passed={"a", "b"}, failed={"c"}, raw_exit=1, raw_tail="t" * 5000)
    rg._pre_cache_store(repo_root, "deadbeef" * 5, ["pytest"], ts)
    got = rg._pre_cache_load(repo_root, "deadbeef" * 5, ["pytest"])
    assert got is not None
    assert got.passed == {"a", "b"} and got.failed == {"c"} and got.raw_exit == 1
    # Different cmd → miss; different sha → miss.
    assert rg._pre_cache_load(repo_root, "deadbeef" * 5, ["tox"]) is None
    assert rg._pre_cache_load(repo_root, "feedface" * 5, ["pytest"]) is None
    # TTL expiry.
    monkeypatch.setattr(rg, "_PRE_CACHE_TTL_S", -1)
    assert rg._pre_cache_load(repo_root, "deadbeef" * 5, ["pytest"]) is None
    # Empty baseline is not cacheable.
    rg._pre_cache_store(repo_root, "aa" * 20, ["pytest"],
                        rg.TestSet(passed=set(), failed=set(), raw_exit=1, raw_tail=""))
    assert rg._pre_cache_load(repo_root, "aa" * 20, ["pytest"]) is None


# ─── 5-3 / 5-4: cost aggregation + budget cap ───────────────────────────────


BACKLOG3 = """# Backlog: X

## BL-0001: One
**Story:** s · **Dependencies:** none

## BL-0002: Two
**Story:** s · **Dependencies:** none

## BL-0003: Three
**Story:** s · **Dependencies:** none
"""


def _mk_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    d = repo / "_brownfield" / "features" / "feat"
    d.mkdir(parents=True)
    (d / "BACKLOG.md").write_text(BACKLOG3)
    subprocess.run(["git", "-C", str(repo), "init", "-b", "main"],
                   check=True, capture_output=True)
    return repo


def _stub_flows_with_cost(monkeypatch, *, cost_per_engineer: float):
    async def fake_engineer(repo_dir, repo_name, bl_id, timeout, rk, **kw):
        yield {"type": "result", "total_cost_usd": cost_per_engineer,
               "orchestrator_step": "engineer"}
        yield {"_orchestrator_outcome": True, "role": "engineer",
               "bl_id": bl_id, "merged": True, "no_op": False}

    async def fake_qa_scorer(repo_dir, repo_name, bl_id, role, timeout, rk, **kw):
        yield {"type": "result", "total_cost_usd": 0.5,
               "orchestrator_step": role}
        out = {"_orchestrator_outcome": True, "role": role, "bl_id": bl_id,
               "merged": True, "doctrine_ok": True, "doctrine_summary": "ok"}
        if role == "scorer":
            out.update({"score_verdict": "Pass", "score_total": 90,
                        "score_min_dim": 4})
        yield out

    async def fake_indexers(repo_dir, label):
        return
        yield  # pragma: no cover

    async def fake_scan_all(repo_dir, run_id):
        return []

    monkeypatch.setattr(orch, "_engineer_flow", fake_engineer)
    monkeypatch.setattr(orch, "_qa_or_scorer_flow", fake_qa_scorer)
    monkeypatch.setattr(orch, "_run_indexers", fake_indexers)
    monkeypatch.setattr(orch.closure_check_svc, "scan_all", fake_scan_all)
    monkeypatch.setattr(orch.run_state_svc, "write_checkpoint", lambda **k: None)
    monkeypatch.setattr(orch.run_state_svc, "mark_terminated", lambda *a, **k: None)
    monkeypatch.setattr(orch, "_archive_traces_since", lambda *a, **k: 0)
    monkeypatch.setattr(orch, "_qa_commit_landed", lambda *a, **k: False)


def _run(repo, **kwargs):
    async def main():
        return [e async for e in orch.run_brief(
            repo_dir=repo, repo_name="repo", brief="x" * 25, project_name="p",
            retrieval_kwargs_builder=lambda *a: {}, skip_po=True,
            stop_on_failure=False, run_doctrine_meta=False,
            run_acceptance=False, feature_slug="feat", **kwargs,
        )]
    return asyncio.run(main())


def test_cost_aggregates_per_bl_and_sprint(tmp_path, monkeypatch) -> None:
    repo = _mk_repo(tmp_path)
    _stub_flows_with_cost(monkeypatch, cost_per_engineer=2.0)
    events = _run(repo)
    dones = [e for e in events if e.get("phase") == "orchestrator.bl.done"]
    # Each BL: engineer 2.0 + qa 0.5 + scorer 0.5 = 3.0
    assert all(abs(d["cost_usd"] - 3.0) < 1e-6 for d in dones)
    sc = next(e for e in events if e.get("phase") == "orchestrator.sprint_complete")
    assert abs(sc["total_cost_usd"] - 9.0) < 1e-6
    assert abs(sc["cost_by_role"]["engineer"] - 6.0) < 1e-6
    assert abs(sc["cost_by_role"]["qa"] - 1.5) < 1e-6


def test_budget_cap_defers_remaining_bls_honestly(tmp_path, monkeypatch) -> None:
    repo = _mk_repo(tmp_path)
    _stub_flows_with_cost(monkeypatch, cost_per_engineer=2.0)
    # Cap allows BL-0001 (3.0) and BL-0002 (6.0); at BL-0003 the check
    # sees 6.0 >= 5.0 → deferred_budget.
    events = _run(repo, max_sprint_usd=5.0)
    out = {e["bl_id"]: e["outcome"] for e in events
           if e.get("phase") == "orchestrator.bl.done"}
    assert out["BL-0001"] == "merged_full"
    assert out["BL-0002"] == "merged_full"
    assert out["BL-0003"] == "deferred_budget", (
        "over-cap BLs must defer, never run silently"
    )
    be = next(e for e in events if e.get("phase") == "orchestrator.budget_exhausted")
    assert be["max_sprint_usd"] == 5.0 and be["spent_usd"] >= 5.0
    sc = next(e for e in events if e.get("phase") == "orchestrator.sprint_complete")
    assert sc["sprint_label"] == "complete_with_deferrals"
    assert {d["bl_id"] for d in sc["deferred"]} == {"BL-0003"}


def test_no_budget_means_no_deferrals(tmp_path, monkeypatch) -> None:
    repo = _mk_repo(tmp_path)
    _stub_flows_with_cost(monkeypatch, cost_per_engineer=2.0)
    events = _run(repo)  # max_sprint_usd defaults None
    assert not [e for e in events
                if e.get("phase") == "orchestrator.budget_exhausted"]
    sc = next(e for e in events if e.get("phase") == "orchestrator.sprint_complete")
    assert sc["sprint_label"] == "complete"
