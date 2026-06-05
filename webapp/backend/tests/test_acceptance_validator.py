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
         "failure": {"classification": "product_bug", "step": "step_03",
                     "root_cause": "backend/app/search/engine.py:120 applies @@ tsquery unconditionally",
                     "source_refs": ["backend/app/search/engine.py:120"],
                     "alternatives_falsified": "test_bug ruled out: selector matches; data_bug ruled out: seed_log shows rows"}},
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
         "failure": {"classification": "test_bug", "step": "x",
                     "root_cause": "frontend/tests/search.spec.ts:13 non-strict getByRole resolves 3 elements",
                     "source_refs": ["frontend/tests/search.spec.ts:13"],
                     "alternatives_falsified": "product_bug ruled out: UI renders correctly in screenshot"}},
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


# ─── ABL-0014 Item 1 — API-acceptance validation ──────────────────────────


def _api_journey(id_: str, slug: str, bl: str, n_requests: int = 1) -> dict:
    return {
        "id": id_,
        "slug": slug,
        "backend_bl": bl,
        "brief_refs": ["REQ-0001"],
        "actors": ["alice"],
        "requests": [
            {
                "method": "GET",
                "path": f"/api/v1/{slug}/{i}",
                "auth_actor": "alice",
                "assert_status": 200,
            }
            for i in range(1, n_requests + 1)
        ],
    }


def _write_api_journeys(acc_dir: Path, api_journeys: list[dict]) -> None:
    (acc_dir / "api_journeys.yaml").write_text(
        yaml.safe_dump({"api_journeys": api_journeys})
    )


def test_api_validation_skipped_when_no_backend_bls(tmp_path: Path) -> None:
    """Backward-compat: if caller passes no backend_bls (the default),
    api_journeys.yaml is NOT required and not parsed. Pre-Item-1 behavior."""
    acc = _build_valid_acceptance_dir(tmp_path)
    # No api_journeys.yaml on disk.
    result = av.validate_acceptance(acc)  # backend_bls=None
    assert result["ok"] is True, result


def test_api_validation_skipped_when_backend_bls_empty(tmp_path: Path) -> None:
    """A pure-frontend sprint has zero backend BLs → skip."""
    acc = _build_valid_acceptance_dir(tmp_path)
    result = av.validate_acceptance(acc, backend_bls=[])
    assert result["ok"] is True, result


def test_api_journeys_missing_when_backend_bls_supplied(tmp_path: Path) -> None:
    """Item 1 contract: a sprint shipping backend BLs MUST produce
    api_journeys.yaml. Absence is a hard miss."""
    acc = _build_valid_acceptance_dir(tmp_path)
    result = av.validate_acceptance(acc, backend_bls=["BL-0006"])
    assert result["ok"] is False
    assert any("api_journeys.yaml" in m for m in result["missing"])


def test_api_journeys_coverage_gap_flagged(tmp_path: Path) -> None:
    """If api_journeys.yaml exists but a backend BL has no covering
    api_journey, the coverage assertion fires."""
    acc = _build_valid_acceptance_dir(tmp_path)
    _write_api_journeys(acc, [_api_journey("api_01", "comments", "BL-0006")])
    # BL-0007 is in the prompt but absent from api_journeys → gap
    result = av.validate_acceptance(acc, backend_bls=["BL-0006", "BL-0007"])
    assert result["ok"] is False
    assert any("coverage gap" in m and "BL-0007" in m for m in result["missing"])


def test_api_journeys_full_coverage_passes(tmp_path: Path) -> None:
    """All backend BLs covered by ≥1 api_journey → ok."""
    acc = _build_valid_acceptance_dir(tmp_path)
    _write_api_journeys(acc, [
        _api_journey("api_01", "comments_create", "BL-0006"),
        _api_journey("api_02", "comments_cross_tenant", "BL-0006"),
        _api_journey("api_03", "documents_list", "BL-0007"),
    ])
    result = av.validate_acceptance(acc, backend_bls=["BL-0006", "BL-0007"])
    assert result["ok"] is True, result


def test_api_journey_missing_required_field_flagged(tmp_path: Path) -> None:
    """Each api_journey needs id, slug, backend_bl, requests."""
    acc = _build_valid_acceptance_dir(tmp_path)
    bad = _api_journey("api_01", "x", "BL-0006")
    del bad["backend_bl"]
    _write_api_journeys(acc, [bad])
    result = av.validate_acceptance(acc, backend_bls=["BL-0006"])
    assert result["ok"] is False
    assert any("missing key 'backend_bl'" in m for m in result["missing"])


def test_api_request_missing_required_field_flagged(tmp_path: Path) -> None:
    """Each request needs method, path, auth_actor, assert_status."""
    acc = _build_valid_acceptance_dir(tmp_path)
    j = _api_journey("api_01", "x", "BL-0006")
    del j["requests"][0]["assert_status"]
    _write_api_journeys(acc, [j])
    result = av.validate_acceptance(acc, backend_bls=["BL-0006"])
    assert result["ok"] is False
    assert any("missing key 'assert_status'" in m for m in result["missing"])


def test_api_invalid_http_method_flagged(tmp_path: Path) -> None:
    acc = _build_valid_acceptance_dir(tmp_path)
    j = _api_journey("api_01", "x", "BL-0006")
    j["requests"][0]["method"] = "TRACE"  # not in our allowlist
    _write_api_journeys(acc, [j])
    result = av.validate_acceptance(acc, backend_bls=["BL-0006"])
    assert result["ok"] is False
    assert any("'TRACE'" in m for m in result["missing"])


def test_api_assert_status_list_accepted(tmp_path: Path) -> None:
    """assert_status can be a list of acceptable codes (e.g. [403, 404])."""
    acc = _build_valid_acceptance_dir(tmp_path)
    j = _api_journey("api_01", "x", "BL-0006")
    j["requests"][0]["assert_status"] = [403, 404]
    _write_api_journeys(acc, [j])
    result = av.validate_acceptance(acc, backend_bls=["BL-0006"])
    assert result["ok"] is True, result


def test_api_assert_status_wrong_type_flagged(tmp_path: Path) -> None:
    acc = _build_valid_acceptance_dir(tmp_path)
    j = _api_journey("api_01", "x", "BL-0006")
    j["requests"][0]["assert_status"] = "two hundred"  # string, not int|list
    _write_api_journeys(acc, [j])
    result = av.validate_acceptance(acc, backend_bls=["BL-0006"])
    assert result["ok"] is False
    assert any("must be int or list[int]" in m for m in result["missing"])


def test_api_too_many_journeys_flagged(tmp_path: Path) -> None:
    acc = _build_valid_acceptance_dir(tmp_path)
    too_many = [
        _api_journey(f"api_{i:02d}", f"x_{i}", "BL-0006")
        for i in range(av.MAX_API_JOURNEYS + 1)
    ]
    _write_api_journeys(acc, too_many)
    result = av.validate_acceptance(acc, backend_bls=["BL-0006"])
    assert result["ok"] is False
    assert any(f"> MAX {av.MAX_API_JOURNEYS}" in m for m in result["missing"])


def test_api_too_many_requests_per_journey_flagged(tmp_path: Path) -> None:
    acc = _build_valid_acceptance_dir(tmp_path)
    j = _api_journey("api_01", "x", "BL-0006",
                     n_requests=av.MAX_REQUESTS_PER_API_JOURNEY + 1)
    _write_api_journeys(acc, [j])
    result = av.validate_acceptance(acc, backend_bls=["BL-0006"])
    assert result["ok"] is False
    assert any(f"> MAX {av.MAX_REQUESTS_PER_API_JOURNEY}" in m
               for m in result["missing"])


# ─── SKILLS v0.2: verified root-cause dossier enforcement ─────────────────


def _failed_finding(**extra) -> dict:
    base = {"id": 1, "slug": "slug_1", "outcome": "failed",
            "failure": {"classification": "product_bug", "step": "step_02"}}
    base["failure"].update(extra)
    return base


def test_product_bug_without_source_is_flagged(tmp_path: Path) -> None:
    """A code-fault finding with no source location is incomplete (v0.2)."""
    acc = _build_valid_acceptance_dir(tmp_path)
    journeys = yaml.safe_load((acc / "journeys.yaml").read_text())
    _write_report_json(acc, journeys, outcomes=[
        _failed_finding(alternatives_falsified="x ruled out"),  # source missing
        {"id": 2, "slug": "slug_2", "outcome": "passed"},
    ])
    result = av.validate_acceptance(acc)
    assert result["ok"] is False
    assert any("no verified source location" in m for m in result["missing"]), result


def test_product_bug_without_alternatives_is_flagged(tmp_path: Path) -> None:
    acc = _build_valid_acceptance_dir(tmp_path)
    journeys = yaml.safe_load((acc / "journeys.yaml").read_text())
    _write_report_json(acc, journeys, outcomes=[
        _failed_finding(source_refs=["backend/app/x.py:42"]),  # alternatives missing
        {"id": 2, "slug": "slug_2", "outcome": "passed"},
    ])
    result = av.validate_acceptance(acc)
    assert result["ok"] is False
    assert any("alternatives_falsified" in m for m in result["missing"]), result


def test_product_bug_with_full_dossier_passes(tmp_path: Path) -> None:
    acc = _build_valid_acceptance_dir(tmp_path)
    journeys = yaml.safe_load((acc / "journeys.yaml").read_text())
    _write_report_json(acc, journeys, outcomes=[
        _failed_finding(
            root_cause="backend/app/x.py:42 returns None for empty input",
            source_refs=["backend/app/x.py:42"],
            alternatives_falsified="test_bug ruled out: selector ok; data_bug ruled out: seed present",
        ),
        {"id": 2, "slug": "slug_2", "outcome": "passed"},
    ])
    result = av.validate_acceptance(acc)
    assert result["ok"] is True, result


def test_root_cause_inline_file_line_satisfies_source_rule(tmp_path: Path) -> None:
    """A `file.ext:line` token inside root_cause counts as a source location
    even without a separate source_refs list."""
    acc = _build_valid_acceptance_dir(tmp_path)
    journeys = yaml.safe_load((acc / "journeys.yaml").read_text())
    _write_report_json(acc, journeys, outcomes=[
        _failed_finding(
            root_cause="traced to backend/app/search/engine.py:120 (unconditional @@)",
            alternatives_falsified="others ruled out by reading the query builder",
        ),
        {"id": 2, "slug": "slug_2", "outcome": "passed"},
    ])
    result = av.validate_acceptance(acc)
    assert result["ok"] is True, result


def test_uncertain_without_record_is_flagged(tmp_path: Path) -> None:
    acc = _build_valid_acceptance_dir(tmp_path)
    journeys = yaml.safe_load((acc / "journeys.yaml").read_text())
    _write_report_json(acc, journeys, outcomes=[
        _failed_finding(classification="uncertain"),  # no investigation record
        {"id": 2, "slug": "slug_2", "outcome": "passed"},
    ])
    result = av.validate_acceptance(acc)
    assert result["ok"] is False
    assert any("no investigation record" in m for m in result["missing"]), result


def test_uncertain_with_next_steps_passes(tmp_path: Path) -> None:
    acc = _build_valid_acceptance_dir(tmp_path)
    journeys = yaml.safe_load((acc / "journeys.yaml").read_text())
    _write_report_json(acc, journeys, outcomes=[
        _failed_finding(classification="uncertain",
                        next_steps="1) check the FTS index 2) diff the seed"),
        {"id": 2, "slug": "slug_2", "outcome": "passed"},
    ])
    result = av.validate_acceptance(acc)
    assert result["ok"] is True, result


def test_infra_bug_exempt_from_dossier(tmp_path: Path) -> None:
    """infra_bug has no product source line — exempt from the dossier rule."""
    acc = _build_valid_acceptance_dir(tmp_path)
    journeys = yaml.safe_load((acc / "journeys.yaml").read_text())
    _write_report_json(acc, journeys, outcomes=[
        _failed_finding(classification="infra_bug"),  # no dossier needed
        {"id": 2, "slug": "slug_2", "outcome": "passed"},
    ])
    result = av.validate_acceptance(acc)
    assert result["ok"] is True, result
