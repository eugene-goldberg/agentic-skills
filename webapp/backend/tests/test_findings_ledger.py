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


def test_top_level_classification_skills_md_shape(tmp_path: Path) -> None:
    """SKILLS.md lines 440-462: agent emits classification + evidence +
    hypothesis at the journey top level (not nested under `failure`).
    Our extractor must consume this canonical shape."""
    ledger = FindingsLedger(tmp_path, "feat_a")
    skills_md_shape = {
        "api_journeys": [{
            "id": "api_03",
            "slug": "documents_upload_approval_workflow",
            "backend_bl": "BL-0007",
            "status": "fail",  # NOT "failed" — SKILLS.md uses this
            "classification": "product_bug",  # top-level, not nested
            "hypothesis": "approve endpoint returns 500 when document already in 'approved' state",
            "evidence": "fixtures/api_logs/api_03_requests.jsonl",
        }],
    }
    persisted = ledger.append_from_report(
        skills_md_shape, run_id="run-1", report_path="r1.json",
    )
    assert len(persisted) == 1
    f = persisted[0]
    assert f.classification == "product_bug"
    assert f.journey_kind == "api"
    assert f.journey_id == "api_03"
    # evidence_summary prefers top-level "evidence" over "hypothesis"
    assert f.evidence_summary == "fixtures/api_logs/api_03_requests.jsonl"


def test_top_level_classification_with_hypothesis_only(tmp_path: Path) -> None:
    """When top-level evidence is absent, hypothesis is the next-best
    signal per SKILLS.md (the agent's diagnosis)."""
    ledger = FindingsLedger(tmp_path, "feat_a")
    rpt = {
        "api_journeys": [{
            "id": "api_05", "status": "fail",
            "classification": "uncertain",
            "hypothesis": "request hangs; could be db lock or upstream timeout",
        }],
    }
    persisted = ledger.append_from_report(rpt, run_id="r", report_path="p")
    assert len(persisted) == 1
    assert "db lock" in persisted[0].evidence_summary


def test_mixed_top_level_and_nested_classification(tmp_path: Path) -> None:
    """Validator at acceptance_validator.py:307-309 accepts both shapes
    in the same report. Our extractor must too."""
    ledger = FindingsLedger(tmp_path, "feat_a")
    rpt = {
        "api_journeys": [
            {  # SKILLS.md top-level shape
                "id": "api_01", "status": "fail",
                "classification": "product_bug",
                "evidence": "POST /orders 500",
            },
        ],
        "ui_journeys": [
            {  # Validator's defensive nested shape
                "id": "ui_02", "status": "failed",
                "failure": {
                    "classification": "test_bug",
                    "evidence": "selector .submit-btn not found within 5s",
                },
            },
        ],
    }
    persisted = ledger.append_from_report(rpt, run_id="r", report_path="p")
    assert len(persisted) == 2
    by_kind = {f.journey_kind: f for f in persisted}
    assert by_kind["api"].classification == "product_bug"
    assert by_kind["ui"].classification == "test_bug"
    assert "selector .submit-btn" in by_kind["ui"].evidence_summary


def test_pass_with_caveat_journey_persists_finding(tmp_path: Path) -> None:
    """§I.3 gap fix (2026-06-02): pass_with_caveat journeys carry a
    structured ``caveat`` object that must reach the ledger.

    Real-world shape from financial-management run-20260602T143035Z-c5868e
    Journey 03: the legal draft→sent step passed, but the agent observed
    a cross-BL defect (UI Edit dialog bypasses BL-0005's transition
    state machine). Pre-fix this finding only existed in report.md prose.
    """
    ledger = FindingsLedger(tmp_path, "feat_a")
    rpt = {
        "journeys": [{
            "id": "03",
            "slug": "invoice_lifecycle_status",
            "status": "pass_with_caveat",
            "caveat": {
                "classification": "product_bug",
                "severity": "medium",
                "summary": (
                    "Edit Invoice dialog calls PUT /billing/invoices/{id}, "
                    "bypasses BL-0005's guarded transition state machine."
                ),
                "hypothesis": (
                    "backend/app/api/routes/billing/invoices.py "
                    "update_invoice writes InvoiceUpdate.status directly."
                ),
            },
        }],
    }
    persisted = ledger.append_from_report(rpt, run_id="r1", report_path="r.json")
    assert len(persisted) == 1
    f = persisted[0]
    assert f.classification == "product_bug"
    assert f.journey_id == "03"
    assert "BL-0005" in f.evidence_summary  # summary wins over hypothesis
    assert f.verdict is None


def test_pass_journey_without_caveat_does_not_persist(tmp_path: Path) -> None:
    """A clean pass with no caveat object must NOT produce a finding —
    that would create noise and undermine the verdict-based bounding
    of classifier accuracy."""
    ledger = FindingsLedger(tmp_path, "feat_a")
    rpt = {"journeys": [{
        "id": "01", "status": "pass",
        "slug": "solo_create_invoice",
    }]}
    assert ledger.append_from_report(rpt, run_id="r", report_path="p") == []


def test_pass_with_caveat_but_no_classification_skipped(tmp_path: Path) -> None:
    """Defensive: caveat object present but no classification ->
    don't persist. Matches the failure-path behavior."""
    ledger = FindingsLedger(tmp_path, "feat_a")
    rpt = {"journeys": [{
        "id": "07", "status": "pass_with_caveat",
        "caveat": {"summary": "something interesting", "severity": "low"},
    }]}
    assert ledger.append_from_report(rpt, run_id="r", report_path="p") == []


def test_pass_with_caveat_unknown_classification_skipped(tmp_path: Path) -> None:
    """Defensive: caveat carries an off-taxonomy classification ->
    skip rather than persist a bad row. Mirrors validator-level
    enforcement for failed journeys."""
    ledger = FindingsLedger(tmp_path, "feat_a")
    rpt = {"journeys": [{
        "id": "09", "status": "pass_with_caveat",
        "caveat": {
            "classification": "design_smell",
            "summary": "could be cleaner",
        },
    }]}
    assert ledger.append_from_report(rpt, run_id="r", report_path="p") == []


def test_pass_with_caveat_hypothesis_only(tmp_path: Path) -> None:
    """summary-absent fallback: use hypothesis as evidence."""
    ledger = FindingsLedger(tmp_path, "feat_a")
    rpt = {"journeys": [{
        "id": "11", "status": "pass_with_caveat",
        "caveat": {
            "classification": "infra_bug",
            "hypothesis": "stack_healthy probe times out under load",
        },
    }]}
    persisted = ledger.append_from_report(rpt, run_id="r", report_path="p")
    assert len(persisted) == 1
    assert "stack_healthy probe" in persisted[0].evidence_summary


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
