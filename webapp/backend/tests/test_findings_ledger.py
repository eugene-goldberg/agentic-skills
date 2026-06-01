"""Tests for ABL-0014 §I.3 findings feedback ledger (Batch A)."""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import findings_ledger as fl  # noqa: E402
from app.services.findings_ledger import FindingsLedger, Finding  # noqa: E402


def _report(
    *,
    journey_id: str = "01",
    classification: str = "product_bug",
    evidence: str = "POST /api/orders returned 500",
    kind: str = "api",
    status: str = "failed",
    extra: list | None = None,
) -> dict:
    """Build a minimal report.json-shaped payload."""
    journey = {
        "id": journey_id,
        "status": status,
        "failure": {
            "classification": classification,
            "evidence": evidence,
        },
    }
    journeys = [journey] + (extra or [])
    key = "api_journeys" if kind == "api" else "ui_journeys"
    return {key: journeys}


# ----- schema + extraction -----

def test_fresh_ledger_creates_parent_dirs(tmp_path: Path) -> None:
    ledger = FindingsLedger(tmp_path, "feat_a")
    assert not ledger.path.exists()
    persisted = ledger.append_from_report(
        _report(), run_id="run-1", report_path="trace/r1/acceptance/report.json",
    )
    assert ledger.path.exists()
    assert ledger.path.parent.is_dir()
    assert len(persisted) == 1


def test_append_writes_one_line_per_finding(tmp_path: Path) -> None:
    ledger = FindingsLedger(tmp_path, "feat_a")
    rpt = _report(extra=[
        {"id": "02", "status": "failed",
         "failure": {"classification": "test_bug", "evidence": "expected 200 got 201"}},
    ])
    ledger.append_from_report(rpt, run_id="run-1", report_path="r1.json")
    lines = ledger.path.read_text().strip().splitlines()
    assert len(lines) == 2
    parsed = [json.loads(L) for L in lines]
    cls = {p["classification"] for p in parsed}
    assert cls == {"product_bug", "test_bug"}


def test_rerun_same_failure_upserts(tmp_path: Path) -> None:
    ledger = FindingsLedger(tmp_path, "feat_a")
    rpt = _report()
    ledger.append_from_report(rpt, run_id="run-1", report_path="r1.json")
    persisted = ledger.append_from_report(
        rpt, run_id="run-2", report_path="r2.json",
    )
    lines = ledger.path.read_text().strip().splitlines()
    assert len(lines) == 1, "rerun must upsert, not duplicate"
    f = Finding.from_jsonl(lines[0])
    assert f.seen_count == 2
    assert f.report_path == "r2.json"
    assert f.last_seen_ts >= f.first_seen_ts
    assert persisted[0].seen_count == 2


def test_distinct_evidence_yields_distinct_finding_id(tmp_path: Path) -> None:
    ledger = FindingsLedger(tmp_path, "feat_a")
    ledger.append_from_report(
        _report(evidence="POST /orders 500"),
        run_id="run-1", report_path="r1.json",
    )
    ledger.append_from_report(
        _report(evidence="GET /orders/42 404"),
        run_id="run-1", report_path="r1.json",
    )
    assert len(ledger.list_all()) == 2


def test_set_verdict_marks_finding(tmp_path: Path) -> None:
    ledger = FindingsLedger(tmp_path, "feat_a")
    persisted = ledger.append_from_report(
        _report(), run_id="run-1", report_path="r1.json",
    )
    fid = persisted[0].finding_id
    updated = ledger.set_verdict(fid, "confirmed", note="real bug, fixed in PR #42")
    assert updated.verdict == "confirmed"
    assert updated.verdict_ts is not None
    assert updated.verdict_note == "real bug, fixed in PR #42"
    # And the change survived to disk:
    on_disk = ledger.list_all()[0]
    assert on_disk.verdict == "confirmed"


def test_set_verdict_unknown_id_raises(tmp_path: Path) -> None:
    ledger = FindingsLedger(tmp_path, "feat_a")
    ledger.append_from_report(_report(), run_id="r", report_path="p")
    with pytest.raises(ValueError, match="unknown finding_id"):
        ledger.set_verdict("sha256:" + "0" * 64, "confirmed")


def test_set_verdict_invalid_enum_raises(tmp_path: Path) -> None:
    ledger = FindingsLedger(tmp_path, "feat_a")
    persisted = ledger.append_from_report(_report(), run_id="r", report_path="p")
    fid = persisted[0].finding_id
    with pytest.raises(ValueError, match="invalid verdict"):
        ledger.set_verdict(fid, "wontfix")


def test_list_pending_excludes_verdicted(tmp_path: Path) -> None:
    ledger = FindingsLedger(tmp_path, "feat_a")
    rpt = _report(extra=[
        {"id": "02", "status": "failed",
         "failure": {"classification": "infra_bug", "evidence": "db conn refused"}},
    ])
    persisted = ledger.append_from_report(rpt, run_id="r", report_path="p")
    ledger.set_verdict(persisted[0].finding_id, "refuted")
    pending = ledger.list_pending()
    assert len(pending) == 1
    assert pending[0].classification == "infra_bug"


def test_get_priors_aggregates_correctly(tmp_path: Path) -> None:
    ledger = FindingsLedger(tmp_path, "feat_a")
    # Three product_bug findings, each with distinct evidence so they
    # collapse to distinct finding_ids:
    for n, ev in enumerate(["A", "B", "C"], start=1):
        ledger.append_from_report(
            _report(journey_id=f"0{n}", evidence=ev),
            run_id="r", report_path="p",
        )
    persisted = ledger.list_all()
    ledger.set_verdict(persisted[0].finding_id, "confirmed")
    ledger.set_verdict(persisted[1].finding_id, "refuted")
    # 3rd remains pending
    priors = ledger.get_priors_for_classification("product_bug")
    assert priors["confirmed"] == 1
    assert priors["refuted"] == 1
    assert priors["pending"] == 1
    assert priors["deferred"] == 0
    # An unseen classification returns all-zero (plus the pending bucket):
    other = ledger.get_priors_for_classification("data_bug")
    assert other["confirmed"] == 0 and other["pending"] == 0


def test_concurrent_append_no_torn_lines(tmp_path: Path) -> None:
    """Threaded appends must yield N distinct lines, all parseable."""
    ledger = FindingsLedger(tmp_path, "feat_a")
    N = 12

    def worker(i: int) -> None:
        rpt = _report(journey_id=f"j{i:02d}", evidence=f"failure number {i}")
        ledger.append_from_report(rpt, run_id=f"run-{i}", report_path=f"p{i}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
    for t in threads: t.start()
    for t in threads: t.join()

    all_findings = ledger.list_all()
    assert len(all_findings) == N
    # All lines parseable (no torn writes):
    lines = ledger.path.read_text().strip().splitlines()
    assert len(lines) == N
    for L in lines:
        Finding.from_jsonl(L)


# ----- schema-drift defenses (free coverage; not in the 10 announced) -----

def test_unknown_classification_is_skipped(tmp_path: Path) -> None:
    ledger = FindingsLedger(tmp_path, "feat_a")
    rpt = _report(classification="not_a_real_class")
    persisted = ledger.append_from_report(rpt, run_id="r", report_path="p")
    assert persisted == []
    assert ledger.list_all() == []


def test_passed_journey_yields_no_finding(tmp_path: Path) -> None:
    ledger = FindingsLedger(tmp_path, "feat_a")
    rpt = _report(status="passed")
    assert ledger.append_from_report(rpt, run_id="r", report_path="p") == []


def test_evidence_truncated_in_storage(tmp_path: Path) -> None:
    ledger = FindingsLedger(tmp_path, "feat_a")
    long_ev = "x" * 5000
    persisted = ledger.append_from_report(
        _report(evidence=long_ev), run_id="r", report_path="p",
    )
    stored = persisted[0].evidence_summary
    assert len(stored) <= 500
    assert stored.endswith("…")


def test_finding_id_stable_across_long_evidence_tail(tmp_path: Path) -> None:
    """Trailing churn beyond the hash-prefix window must not change
    the id — that's the upsert guarantee under noisy stack traces."""
    base = "POST /api/orders -> 500\n" + ("frame\n" * 100)
    ledger = FindingsLedger(tmp_path, "feat_a")
    ledger.append_from_report(
        _report(evidence=base + "tail-A"), run_id="r1", report_path="p1",
    )
    ledger.append_from_report(
        _report(evidence=base + "tail-B"), run_id="r2", report_path="p2",
    )
    # Hash prefix is 200 chars; "base" already exceeds it, so the
    # finding_id should be identical and rows collapse to 1.
    assert len(ledger.list_all()) == 1
