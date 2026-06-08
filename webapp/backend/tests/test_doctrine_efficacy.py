"""ABL-0017 Stage 2 — doctrine efficacy aggregator tests (synthetic, deterministic)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import doctrine_efficacy as de  # noqa: E402
from app.services.traces import PHASE_EVENTS_SCHEMA_VERSION  # noqa: E402


def _write_phase_events(trace_dir: Path, events: list[dict]) -> None:
    trace_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"_schema_version": PHASE_EVENTS_SCHEMA_VERSION})]
    lines += [json.dumps(e) for e in events]
    (trace_dir / "phase_events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _setup_run(tmp_path: Path, run_id: str, *, traces: dict[str, list[dict]],
               manifest_rules: list[dict], outcomes: list[dict], done: bool = True) -> tuple[Path, Path]:
    archive_root = tmp_path / "traces_archive"
    for dirname, events in traces.items():
        _write_phase_events(archive_root / run_id / dirname, events)
    state_root = tmp_path / "state"
    sub = state_root / ("done" if done else ".")
    sub.mkdir(parents=True, exist_ok=True)
    (sub / f"{run_id}.json").write_text(json.dumps({
        "run_id": run_id, "repo": "beaverhabits", "status": "sprint_complete",
        "bl_outcomes": outcomes,
        "doctrine_manifest": {"harness_sha": "abc123", "rules": manifest_rules},
    }), encoding="utf-8")
    return archive_root, state_root


_MANIFEST = [{"id": r, "enforced": True} for r in ("R5", "R5b", "R8", "R10", "R13", "Tier1.5")]


def test_extract_firings_maps_rules_and_catches(tmp_path: Path) -> None:
    run = "run-X"
    archive_root, _ = _setup_run(tmp_path, run, traces={
        "20260608T000000Z-engineer-BL-0001-aaa": [
            {"type": "_meta", "phase": "worktree_ready"},                       # ignored
            {"type": "_meta", "phase": "doctrine_check", "kind": "incomplete",
             "summary": "0 grounded retrieval calls, need >=3"},               # R5 catch
            {"type": "_meta", "phase": "bl_tests", "kind": "failed"},           # R10 catch
            {"type": "_meta", "phase": "pre_grounding_violation", "kind": "insufficient",
             "rule_id": "Tier1.5"},                                            # Tier1.5 catch
            {"type": "_meta", "phase": "doctrine_check", "kind": "complete"},   # clean
            {"type": "_meta", "phase": "bl_tests", "kind": "green"},            # R10 clean
            {"type": "_meta", "phase": "merge_to_target", "ok": True},          # ignored
        ],
    }, manifest_rules=_MANIFEST, outcomes=[{"bl_id": "BL-0001", "outcome": "merged_full"}])
    firings = de.extract_firings(run, archive_root=archive_root)
    by = {}
    for f in firings:
        by.setdefault(f.rule_id, {"caught": 0, "clean": 0})["caught" if f.caught else "clean"] += 1
    assert by["R5"] == {"caught": 1, "clean": 0}
    assert by["R10"] == {"caught": 1, "clean": 1}
    assert by["Tier1.5"] == {"caught": 1, "clean": 0}
    assert by["doctrine_check"] == {"caught": 0, "clean": 1}  # the clean doctrine_check
    # non-rule phases excluded
    assert all(f.phase not in de._NON_RULE_PHASES for f in firings)


def test_run_efficacy_joins_manifest_and_outcomes(tmp_path: Path) -> None:
    run = "run-Y"
    archive_root, state_root = _setup_run(tmp_path, run, traces={
        "20260608T000000Z-engineer-BL-0001-bbb": [
            {"type": "_meta", "phase": "bl_tests", "kind": "failed"},
        ],
    }, manifest_rules=_MANIFEST, outcomes=[
        {"bl_id": "BL-0001", "outcome": "merged_full"},
        {"bl_id": "BL-0002", "outcome": "escalated"},
    ])
    rep = de.run_efficacy(run, archive_root=archive_root, state_root=state_root)
    assert rep["harness_sha"] == "abc123"
    assert "R10" in rep["rules_enforced"]
    assert rep["by_rule"]["R10"]["caught"] == 1
    assert rep["outcome_counts"] == {"merged_full": 1, "escalated": 1}


def test_efficacy_report_separates_never_fired_from_unobserved(tmp_path: Path) -> None:
    """The real-data honesty trap: an enforced rule whose phase never appears is
    UNOBSERVED (can't assess), NOT a retirement candidate. Only an enforced rule
    OBSERVED running yet never catching is a review candidate."""
    run = "run-Z"
    archive_root, state_root = _setup_run(tmp_path, run, traces={
        "20260608T000000Z-engineer-BL-0001-ccc": [
            {"type": "_meta", "phase": "bl_tests", "kind": "green"},   # R10 OBSERVED clean only
        ],
    }, manifest_rules=_MANIFEST, outcomes=[{"bl_id": "BL-0001", "outcome": "merged_full"}])
    rep = de.efficacy_report([run], archive_root=archive_root, state_root=state_root)
    # R10 observed running (green) but never caught → review candidate (could be
    # a clean crew, not a dead rule — the report flags, never verdicts).
    assert "R10" in rep["never_fired_review_candidates"]
    # R8/R13/Tier1.5/R5/R5b enforced but their phases never appeared → UNOBSERVED,
    # explicitly NOT retirement candidates (this is the pre-A13-sealing trap).
    assert "R13" in rep["unobserved_rules"]
    assert "R8" in rep["unobserved_rules"]
    assert "R13" not in rep["never_fired_review_candidates"]
    assert rep["run_count"] == 1
    assert rep["confidence"].startswith("low")
    assert rep["rules"]["R5"]["targeted_failure_class"] is not None


def test_efficacy_report_fire_rate(tmp_path: Path) -> None:
    # R10 catches in 2 of 2 runs → fire_rate 1.0
    archive_root = tmp_path / "traces_archive"
    state_root = tmp_path / "state"
    for run in ("run-A", "run-B"):
        _write_phase_events(archive_root / run / "20260608T000000Z-engineer-BL-0001-x",
                            [{"type": "_meta", "phase": "bl_tests", "kind": "failed"}])
        (state_root / "done").mkdir(parents=True, exist_ok=True)
        (state_root / "done" / f"{run}.json").write_text(json.dumps({
            "run_id": run, "doctrine_manifest": {"rules": _MANIFEST},
            "bl_outcomes": [{"bl_id": "BL-0001", "outcome": "merged_full"}],
        }), encoding="utf-8")
    rep = de.efficacy_report(["run-A", "run-B"], archive_root=archive_root, state_root=state_root)
    assert rep["rules"]["R10"]["caught"] == 2
    assert rep["rules"]["R10"]["fire_rate_per_run"] == 1.0


def test_missing_archive_is_empty(tmp_path: Path) -> None:
    assert de.extract_firings("nope", archive_root=tmp_path / "x") == []
    assert de.run_efficacy("nope", archive_root=tmp_path / "x", state_root=tmp_path / "y")["n_firings"] == 0
