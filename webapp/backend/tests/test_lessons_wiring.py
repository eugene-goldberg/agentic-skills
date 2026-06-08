"""ABL-0016 Batch B — inject_lessons plumbing + prompt-builder wiring.

Verifies the flag threads request -> run_brief -> the three role flows ->
the four build_* dispatchers -> the brownfield builders, and that the
rendered lessons block actually lands in a brownfield prompt when the flag
is on and the target has lessons (and is absent when off).

Behavioral check uses prompts.build_engineer directly against a tmp repo
with a seeded findings ledger — exercises the full dispatcher -> lessons
svc -> renderer -> builder interpolation path without a subprocess.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import orchestrator as orch  # noqa: E402
from app.services import prompts as prompts_svc  # noqa: E402
from app.routers.projects import RunBriefRequest  # noqa: E402
from app.services.findings_ledger import Finding  # noqa: E402


def _seed_confirmed_finding(repo_root: Path, feature_slug: str, evidence: str) -> None:
    d = repo_root / "_brownfield" / "features" / feature_slug / "acceptance"
    d.mkdir(parents=True, exist_ok=True)
    f = Finding(
        finding_id="sha256:wiring", run_id="r1", feature_slug=feature_slug,
        journey_id="03", journey_kind="ui", classification="product_bug",
        evidence_summary=evidence, report_path="/tmp/report.json",
        first_seen_ts="2026-06-02T00:00:00Z", last_seen_ts="2026-06-02T00:00:00Z",
        seen_count=1, verdict="confirmed",
    )
    (d / "findings_log.jsonl").write_text(f.to_jsonl() + "\n", encoding="utf-8")


# ─── request model ─────────────────────────────────────────────────────────


def test_request_has_inject_lessons_default_false() -> None:
    assert RunBriefRequest(brief="x" * 25).inject_lessons is False


def test_request_accepts_inject_lessons_true() -> None:
    assert RunBriefRequest(brief="x" * 25, inject_lessons=True).inject_lessons is True


# ─── signatures: run_brief + the three flows + four dispatchers ────────────


def test_run_brief_signature_has_inject_lessons_default_false() -> None:
    assert inspect.signature(orch.run_brief).parameters["inject_lessons"].default is False


def test_all_flows_accept_inject_lessons() -> None:
    for fn in (orch._po_flow, orch._engineer_flow, orch._qa_or_scorer_flow):
        p = inspect.signature(fn).parameters
        assert "inject_lessons" in p, f"{fn.__name__} missing inject_lessons"
        assert p["inject_lessons"].default is False


def test_all_dispatchers_accept_inject_lessons() -> None:
    for fn in (prompts_svc.build_po, prompts_svc.build_engineer,
               prompts_svc.build_qa, prompts_svc.build_score):
        p = inspect.signature(fn).parameters
        assert "inject_lessons" in p, f"{fn.__name__} missing inject_lessons"
        assert p["inject_lessons"].default is False


# ─── wiring source check: run_brief threads the flag to every flow ─────────


def test_run_brief_threads_inject_lessons_to_flows() -> None:
    src = inspect.getsource(orch.run_brief)
    # every flow invocation in run_brief passes inject_lessons through
    assert src.count("inject_lessons=inject_lessons") >= 4  # po + engineer + qa + scorer


# ─── behavioral: the block lands in a brownfield prompt iff flag on ────────


def test_engineer_prompt_includes_lessons_when_on(tmp_path: Path) -> None:
    _seed_confirmed_finding(tmp_path, "feat-a", "PUT bypasses the state machine")
    prompt = prompts_svc.build_engineer(
        "brownfield", "BL-0001", "do the thing", tmp_path,
        feature_slug="feat-a", inject_lessons=True,
    )
    assert "## Relevant prior lessons (advisory)" in prompt
    assert "PUT bypasses the state machine" in prompt


def test_engineer_prompt_excludes_lessons_when_off(tmp_path: Path) -> None:
    _seed_confirmed_finding(tmp_path, "feat-a", "PUT bypasses the state machine")
    prompt = prompts_svc.build_engineer(
        "brownfield", "BL-0001", "do the thing", tmp_path,
        feature_slug="feat-a", inject_lessons=False,
    )
    assert "Relevant prior lessons" not in prompt


def test_qa_and_scorer_prompts_include_lessons_when_on(tmp_path: Path) -> None:
    _seed_confirmed_finding(tmp_path, "feat-a", "audit trail not written on delete")
    qa = prompts_svc.build_qa("brownfield", "BL-0001", "sec", tmp_path,
                              feature_slug="feat-a", inject_lessons=True)
    score = prompts_svc.build_score("brownfield", "BL-0001", "sec", tmp_path,
                                    feature_slug="feat-a", inject_lessons=True)
    assert "Relevant prior lessons" in qa
    assert "Relevant prior lessons" in score


def test_po_prompt_includes_lessons_when_on(tmp_path: Path) -> None:
    """PO gains 'this target's recurring failure modes at planning time' — the
    one role only signature-checked above. Assert the block actually lands in
    a brownfield PO prompt so all four roles have an end-to-end injection
    proof, not just engineer/QA/scorer."""
    _seed_confirmed_finding(tmp_path, "feat-a", "delete cascades orphan child rows")
    prompt = prompts_svc.build_po(
        "brownfield", "add reporting", "proj", tmp_path,
        feature_slug="feat-a", inject_lessons=True,
    )
    assert "## Relevant prior lessons (advisory)" in prompt
    assert "delete cascades orphan child rows" in prompt


def test_po_prompt_excludes_lessons_when_off(tmp_path: Path) -> None:
    _seed_confirmed_finding(tmp_path, "feat-a", "delete cascades orphan child rows")
    prompt = prompts_svc.build_po(
        "brownfield", "add reporting", "proj", tmp_path,
        feature_slug="feat-a", inject_lessons=False,
    )
    assert "Relevant prior lessons" not in prompt


def test_lessons_silent_when_no_findings(tmp_path: Path) -> None:
    # brownfield repo with no ledger at all -> flag on but block empty
    prompt = prompts_svc.build_engineer(
        "brownfield", "BL-0001", "do the thing", tmp_path,
        feature_slug="feat-a", inject_lessons=True,
    )
    assert "Relevant prior lessons" not in prompt
