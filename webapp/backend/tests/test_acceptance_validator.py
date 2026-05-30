"""Tests for ABL-0010 Batch A: acceptance_validator.

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


def test_missing_report_json_flagged(tmp_path: Path) -> None:
    acc = _build_valid_acceptance_dir(tmp_path)
    (acc / "report.json").unlink()
    result = av.validate_acceptance(acc)
    assert result["ok"] is False
    assert "report.json" in result["missing"]


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
