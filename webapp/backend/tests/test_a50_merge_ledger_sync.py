"""A50: merge-branch → findings-ledger sync.

A follow-up dispatch whose gate did not auto-merge leaves its branch
(``agent/followup-<run_id>-<idx>``) for manual review. When the operator
merges it (UI Review-&-merge or POST /merge-branch), the owning finding's
``dispatch_state`` must flip to ``merged`` so the ledger stays honest.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import findings_ledger as fl  # noqa: E402
from app.services.findings_ledger import FindingsLedger  # noqa: E402


def _report(journey_id="01", classification="product_bug",
            evidence="restore unreachable from UI"):
    return {"ui_journeys": [{
        "id": journey_id, "status": "failed",
        "failure": {"classification": classification, "evidence": evidence},
    }]}


# ----- branch-name parsing -----

@pytest.mark.parametrize("branch,expected", [
    ("agent/followup-manual-dispatch-20260604T035643Z-db2d82-0",
     "manual-dispatch-20260604T035643Z-db2d82"),
    ("agent/followup-run-20260603T171421Z-30c5d9-2", "run-20260603T171421Z-30c5d9"),
    ("followup-abc-0", "abc"),                       # no agent/ prefix
    ("agent/BL-0003", None),                          # not a follow-up branch
    ("agent/followup-noindex", None),                 # missing -<idx>
    ("agent/followup-x-notanumber", None),            # index not numeric
])
def test_followup_run_id_from_branch(branch, expected):
    assert fl.followup_run_id_from_branch(branch) == expected


# ----- end-to-end sync -----

def _seed_not_merged(tmp_path, *, feature="invoice-soft-delete",
                     run_id="manual-dispatch-XYZ-ab"):
    """Append a product_bug, dispatch it, then mark not_merged — the state a
    flaky-gate dispatch leaves behind."""
    led = FindingsLedger(tmp_path, feature)
    persisted = led.append_from_report(_report(), run_id="sprint-1",
                                       report_path="r.json")
    fid = persisted[0].finding_id
    led.set_dispatch_state(fid, "dispatched", bl_id="BL-ACCEPT-x", run_id=run_id)
    led.set_dispatch_state(fid, "not_merged")
    return led, fid


def test_sync_flips_not_merged_to_merged(tmp_path: Path):
    run_id = "manual-dispatch-XYZ-ab"
    led, fid = _seed_not_merged(tmp_path, run_id=run_id)
    branch = f"agent/followup-{run_id}-0"

    res = fl.sync_followup_merge_to_ledger(tmp_path, branch, "deadbeefcafe")

    assert res and res["dispatch_state"] == "merged"
    assert res["finding_id"] == fid
    assert res["feature_slug"] == "invoice-soft-delete"
    # Ledger reflects the merge.
    after = {f.finding_id: f for f in led.list_all()}[fid]
    assert after.dispatch_state == "merged"
    assert after.dispatch_merged_sha == "deadbeefcafe"


def test_resolve_by_run_id_scans_all_features(tmp_path: Path):
    run_id = "manual-dispatch-find-me"
    _seed_not_merged(tmp_path, feature="other-feature", run_id="unrelated")
    led, fid = _seed_not_merged(tmp_path, feature="target-feature", run_id=run_id)
    hit = fl.resolve_finding_by_dispatch_run_id(tmp_path, run_id)
    assert hit is not None
    slug, finding = hit
    assert slug == "target-feature" and finding.finding_id == fid


def test_non_followup_branch_is_noop(tmp_path: Path):
    _seed_not_merged(tmp_path)
    assert fl.sync_followup_merge_to_ledger(tmp_path, "agent/BL-0003", "sha") is None


def test_unknown_run_id_reports_unmatched(tmp_path: Path):
    _seed_not_merged(tmp_path, run_id="manual-dispatch-XYZ-ab")
    res = fl.sync_followup_merge_to_ledger(
        tmp_path, "agent/followup-some-other-run-0", "sha")
    assert res == {"run_id": "some-other-run", "matched": False}


def test_idempotent_when_already_merged(tmp_path: Path):
    run_id = "manual-dispatch-XYZ-ab"
    led, fid = _seed_not_merged(tmp_path, run_id=run_id)
    branch = f"agent/followup-{run_id}-0"
    fl.sync_followup_merge_to_ledger(tmp_path, branch, "sha1")
    res2 = fl.sync_followup_merge_to_ledger(tmp_path, branch, "sha2")
    assert res2 and res2.get("already_merged") is True
    # sha not clobbered on the second call.
    after = {f.finding_id: f for f in led.list_all()}[fid]
    assert after.dispatch_merged_sha == "sha1"


def test_no_features_dir_returns_none(tmp_path: Path):
    assert fl.resolve_finding_by_dispatch_run_id(tmp_path, "any") is None
