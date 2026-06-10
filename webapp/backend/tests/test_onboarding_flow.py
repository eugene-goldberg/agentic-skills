"""Onboarding flow — the Janitor/Ops-Steward in onboarding mode.

Covers the orchestrator-side pieces that don't need a live agent: the
independent postcondition verifier (the trust gate) and the task builder.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import orchestrator as o  # noqa: E402
from app.services import prompts_brownfield as pb  # noqa: E402


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _make_repo(tmp_path: Path, *, with_cfg=True, with_branch=True, with_ignore=True) -> Path:
    repo = tmp_path / "target"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "t@t.local"], repo)
    _git(["config", "user.name", "t"], repo)
    (repo / "README.md").write_text("x")
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", "init"], repo)
    if with_cfg:
        (repo / ".agentic-skills.json").write_text(json.dumps({
            "agent_branch": "integration", "main_ref": "main",
            "doctrine": "brownfield", "test_cmd": ["dotnet", "test"]}))
    if with_branch:
        _git(["branch", "integration", "main"], repo)
    if with_ignore:
        (repo / ".gitignore").write_text(
            "graphify-out\n_brownfield/**/events.jsonl\n_brownfield/_pattern_profile/\n")
    return repo


def test_verify_postconditions_all_present(tmp_path):
    repo = _make_repo(tmp_path)
    res = o._verify_onboarding_postconditions(repo)
    assert res["ok"] is True
    assert res["checks"] == {
        "agentic_skills_json": True,
        "integration_branch": True,
        "gitignore_hygiene": True,
    }
    assert res["missing"] == []


def test_verify_postconditions_missing_config(tmp_path):
    repo = _make_repo(tmp_path, with_cfg=False)
    res = o._verify_onboarding_postconditions(repo)
    assert res["ok"] is False
    assert res["checks"]["agentic_skills_json"] is False
    assert any("agentic-skills.json" in m for m in res["missing"])


def test_verify_postconditions_missing_branch(tmp_path):
    repo = _make_repo(tmp_path, with_branch=False)
    res = o._verify_onboarding_postconditions(repo)
    assert res["ok"] is False
    assert res["checks"]["integration_branch"] is False
    assert any("integration" in m for m in res["missing"])


def test_verify_postconditions_missing_gitignore(tmp_path):
    repo = _make_repo(tmp_path, with_ignore=False)
    res = o._verify_onboarding_postconditions(repo)
    assert res["ok"] is False
    assert res["checks"]["gitignore_hygiene"] is False


def test_verify_postconditions_invalid_config_no_testcmd(tmp_path):
    repo = _make_repo(tmp_path)
    # a config with no test_cmd is invalid for gate-readiness
    (repo / ".agentic-skills.json").write_text(json.dumps({"agent_branch": "integration"}))
    res = o._verify_onboarding_postconditions(repo)
    assert res["checks"]["agentic_skills_json"] is False


def test_build_onboarding_task_carries_skill_and_scope():
    skill = pb._load_skill("onboarder")
    task = o._build_onboarding_task(
        skill, run_id="onboard-x", repo_name="acme",
        main_ref="main", report_rel="r.md", report_json_rel="r.json",
        brief="Add billing")
    # the skill doctrine is embedded
    assert "ONBOARDING MODE" in task
    # the hard scope line: provision env, never edit committed source
    assert "never edit" in task.lower() or "NEVER edit" in task
    assert "PROVISION THE ENVIRONMENT" in task
    # run context + deliverables + brief-as-context (not "build it")
    assert "acme" in task and "onboard-x" in task
    assert "r.json" in task
    assert "Add billing" in task and "do NOT" in task


def test_build_onboarding_task_no_brief():
    skill = pb._load_skill("onboarder")
    task = o._build_onboarding_task(
        skill, run_id="onboard-y", repo_name="acme",
        main_ref="master", report_rel="r.md", report_json_rel="r.json",
        brief=None)
    assert "No specific brief yet" in task
    assert "master" in task
