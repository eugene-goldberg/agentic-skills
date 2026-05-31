"""Tests for ABL-0014 Batch A: acceptance_validator.

Validates the contract in
``skills/brownfield/brownfield-acceptance-agent/SKILLS.md`` against a
golden valid acceptance/ tree plus five specific invalid fixtures + the
two cost-cap rejections (§E.1 Q4 layer-2 enforcement).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import acceptance_validator as av  # noqa: E402


# ─── fixture helpers ───────────────────────────────────────────────────────


def _journey(id_: int, slug: str, n_steps: int = 2) -> dict:
    return {
        "id": id_,
        "slug": slug,
        "brief_refs": ["REQ-0001"],
        "backlog_refs": ["BL-0001"],
        "actors": ["user"],
        "steps": [
            {
                "name": f"step_{i}",
                "action": "click x",
                "assert": "y visible",
                "screenshot": f"step_{i:02d}_{slug}.png",
            }
            for i in range(1, n_steps + 1)
        ],
    }


def _write_report_json(acc_dir: Path, journeys: list[dict], outcomes: list[dict] | None = None) -> None:
    if outcomes is None:
        outcomes = [{"id": j["id"], "slug": j["slug"], "outcome": "passed"} for j in journeys]
    (acc_dir / "report.json").write_text(json.dumps({"journeys": outcomes}, indent=2))


def _build_valid_acceptance_dir(tmp_path: Path, n_journeys: int = 2, n_steps: int = 2) -> Path:
    acc = tmp_path / "acceptance"
    acc.mkdir(parents=True)
    (acc / "fixtures").mkdir()
    (acc / "screenshots").mkdir()

    journeys = [_journey(i, f"slug_{i}", n_steps=n_steps) for i in range(1, n_journeys + 1)]
    (acc / "journeys.yaml").write_text(yaml.safe_dump(journeys))

    # Plausible-length report.md so the ≥120-byte floor passes.
    (acc / "report.md").write_text("# Acceptance report\n\n" + ("Lorem ipsum dolor sit amet. " * 10))
    _write_report_json(acc, journeys)
    (acc / "fixtures" / "seed_log.txt").write_text(
        "user_id=1 alice approver\nuser_id=2 bob member\nuser_id=3 carol member\n"
        "timesheet_id=10 user=1 week=2026-W18 status=submitted\n"
    )

    # Screenshots on disk under screenshots/journey_<NN>_<slug>/...
    for j in journeys:
        jdir = acc / "screenshots" / f"journey_{j['id']:02d}_{j['slug']}"
        jdir.mkdir(parents=True)
        for step in j["steps"]:
            (jdir / step["screenshot"]).write_bytes(b"\x89PNG\r\n\x1a\nfake")

    return acc


# ─── golden valid ──────────────────────────────────────────────────────────


def test_valid_acceptance_dir_passes(tmp_path: Path) -> None:
    acc = _build_valid_acceptance_dir(tmp_path)
    result = av.validate_acceptance(acc)
    assert result["ok"] is True, result
    assert result["missing"] == []
    assert result["empty"] == []


# ─── 5 specific invalid fixtures ───────────────────────────────────────────


def test_missing_screenshot_flagged(tmp_path: Path) -> None:
    acc = _build_valid_acceptance_dir(tmp_path)
    # delete one declared screenshot
    target = acc / "screenshots" / "journey_01_slug_1" / "step_01_slug_1.png"
    target.unlink()
    result = av.validate_acceptance(acc)
    assert result["ok"] is False
    assert any("step_01_slug_1.png" in m for m in result["missing"])


def test_malformed_journeys_yaml_flagged(tmp_path: Path) -> None:
    acc = _build_valid_acceptance_dir(tmp_path)
    (acc / "journeys.yaml").write_text(":\n  not valid yaml: ][[")
    result = av.validate_acceptance(acc)
    assert result["ok"] is False
    assert any("journeys.yaml" in m for m in result["missing"])


def test_invalid_classification_enum_flagged(tmp_path: Path) -> None:
    acc = _build_valid_acceptance_dir(tmp_path)
    journeys = yaml.safe_load((acc / "journeys.yaml").read_text())
    _write_report_json(acc, journeys, outcomes=[
        {"id": 1, "slug": "slug_1", "outcome": "failed", "classification": "borked"},
        {"id": 2, "slug": "slug_2", "outcome": "passed"},
    ])
    result = av.validate_acceptance(acc)
    assert result["ok"] is False
    assert any("classification='borked'" in m for m in result["missing"])


def test_missing_both_report_variants_flagged(tmp_path: Path) -> None:
    """Smoke-1 calibration: report.md OR report.json satisfies. Only flag
    when NEITHER exists."""
    acc = _build_valid_acceptance_dir(tmp_path)
    (acc / "report.json").unlink()
    (acc / "report.md").unlink()
    result = av.validate_acceptance(acc)
    assert result["ok"] is False
    assert any("need at least one of" in m for m in result["missing"])


def test_report_md_alone_satisfies(tmp_path: Path) -> None:
    """Smoke-1 calibration: report.md alone satisfies the variant rule."""
    acc = _build_valid_acceptance_dir(tmp_path)
    (acc / "report.json").unlink()
    (acc / "report.md").write_text("# Acceptance report\n\n" + ("Lorem ipsum. " * 20))
    result = av.validate_acceptance(acc)
    assert result["ok"] is True, result


def test_journeys_yaml_dict_form_accepted(tmp_path: Path) -> None:
    """Smoke-1 calibration: agent's {journeys: [...], journeys_deferred: [...]}
    dict form is accepted as a legitimate extension."""
    acc = _build_valid_acceptance_dir(tmp_path)
    journeys = yaml.safe_load((acc / "journeys.yaml").read_text())
    # Re-emit as a dict with journeys_deferred (the agent's natural shape)
    (acc / "journeys.yaml").write_text(yaml.safe_dump({
        "journeys": journeys,
        "journeys_deferred": [
            {"id": "98", "slug": "future_idea", "reason": "out of cap"},
        ],
    }))
    result = av.validate_acceptance(acc)
    assert result["ok"] is True, result


def test_lenient_screenshot_accepts_ordinal_match(tmp_path: Path) -> None:
    """Smoke-1 calibration: if a step's declared png is missing but ANY
    step_NN_*.png exists in the journey dir, accept (handles playwright
    auto-failure screenshots at a different path than the spec declared)."""
    acc = _build_valid_acceptance_dir(tmp_path)
    target = acc / "screenshots" / "journey_01_slug_1" / "step_01_slug_1.png"
    target.unlink()  # remove the EXACT declared name
    # ...but leave a different png with the same ordinal prefix
    (target.parent / "step_01_auto_failure.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    result = av.validate_acceptance(acc)
    assert result["ok"] is True, result


def test_failed_journey_only_needs_one_png(tmp_path: Path) -> None:
    """Smoke-1 calibration: when report.json marks the journey as failed,
    only require ≥1 png in the journey dir (steps after the failure point
    legitimately have no screenshot)."""
    acc = _build_valid_acceptance_dir(tmp_path, n_steps=4)
    # Mark journey 1 as failed in report.json (nested classification)
    journeys = yaml.safe_load((acc / "journeys.yaml").read_text())
    _write_report_json(acc, journeys, outcomes=[
        {"id": 1, "slug": "slug_1", "outcome": "failed",
         "failure": {"classification": "product_bug", "step": "step_03"}},
        {"id": 2, "slug": "slug_2", "outcome": "passed"},
    ])
    # Delete 3 of 4 declared pngs for journey 1; one png remains as evidence
    jdir = acc / "screenshots" / "journey_01_slug_1"
    for p in list(jdir.glob("step_0[2-4]_*.png")):
        p.unlink()
    result = av.validate_acceptance(acc)
    assert result["ok"] is True, result


def test_classification_nested_under_failure_accepted(tmp_path: Path) -> None:
    """Smoke-1 calibration: agents may put classification under failure
    rather than at top level."""
    acc = _build_valid_acceptance_dir(tmp_path)
    journeys = yaml.safe_load((acc / "journeys.yaml").read_text())
    _write_report_json(acc, journeys, outcomes=[
        {"id": 1, "slug": "slug_1", "outcome": "failed",
         "failure": {"classification": "test_bug", "step": "x"}},
        {"id": 2, "slug": "slug_2", "outcome": "passed"},
    ])
    # Need a png in journey_01_slug_1 (which the builder already provided)
    result = av.validate_acceptance(acc)
    assert result["ok"] is True, result


def test_status_field_accepted_as_outcome_synonym(tmp_path: Path) -> None:
    """Smoke-2 calibration: agents may write `status` instead of `outcome`."""
    acc = _build_valid_acceptance_dir(tmp_path)
    journeys = yaml.safe_load((acc / "journeys.yaml").read_text())
    _write_report_json(acc, journeys, outcomes=[
        {"id": 1, "slug": "slug_1", "status": "passed"},
        {"id": 2, "slug": "slug_2", "status": "passed"},
    ])
    result = av.validate_acceptance(acc)
    assert result["ok"] is True, result


def test_loose_result_pass_fail_synonyms_accepted(tmp_path: Path) -> None:
    """Smoke-1 calibration: 'pass'/'fail' shorthand in report.json's
    `result` field maps to passed/failed."""
    acc = _build_valid_acceptance_dir(tmp_path)
    journeys = yaml.safe_load((acc / "journeys.yaml").read_text())
    _write_report_json(acc, journeys, outcomes=[
        {"id": 1, "slug": "slug_1", "result": "pass"},
        {"id": 2, "slug": "slug_2", "result": "pass"},
    ])
    result = av.validate_acceptance(acc)
    assert result["ok"] is True, result


def test_lenient_screenshot_accepts_playwright_failure(tmp_path: Path) -> None:
    """Smoke-1 calibration: a 'test-failed-1.png'-style auto-artifact
    in the journey dir counts as evidence."""
    acc = _build_valid_acceptance_dir(tmp_path)
    target = acc / "screenshots" / "journey_01_slug_1" / "step_01_slug_1.png"
    target.unlink()
    (target.parent / "test-failed-1.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    result = av.validate_acceptance(acc)
    assert result["ok"] is True, result


def test_zero_step_journey_flagged(tmp_path: Path) -> None:
    acc = _build_valid_acceptance_dir(tmp_path)
    journeys = yaml.safe_load((acc / "journeys.yaml").read_text())
    journeys[0]["steps"] = []
    (acc / "journeys.yaml").write_text(yaml.safe_dump(journeys))
    result = av.validate_acceptance(acc)
    assert result["ok"] is False
    assert any("≥1 step required" in m for m in result["missing"])


# ─── §E.1 Q4 cost-cap layer-2 enforcement ──────────────────────────────────


def test_too_many_journeys_flagged(tmp_path: Path) -> None:
    # 9 journeys > MAX_JOURNEYS (8)
    acc = _build_valid_acceptance_dir(tmp_path, n_journeys=9)
    result = av.validate_acceptance(acc)
    assert result["ok"] is False
    assert any(f"> MAX {av.MAX_JOURNEYS}" in m for m in result["missing"])


def test_too_many_steps_flagged(tmp_path: Path) -> None:
    # 16 steps in journey 1 > MAX_STEPS_PER_JOURNEY (15)
    acc = _build_valid_acceptance_dir(tmp_path, n_journeys=1, n_steps=16)
    result = av.validate_acceptance(acc)
    assert result["ok"] is False
    assert any(f"> MAX {av.MAX_STEPS_PER_JOURNEY}" in m for m in result["missing"])


# ─── nonexistent dir ───────────────────────────────────────────────────────


def test_nonexistent_dir_flagged(tmp_path: Path) -> None:
    result = av.validate_acceptance(tmp_path / "does_not_exist")
    assert result["ok"] is False
    assert any("acceptance dir not created" in m for m in result["missing"])
