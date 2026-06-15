"""wave-concurrency follow-up #2: unit test for _reconcile_unassembled_outcome.

Locks the I-5 truthful-aggregation fix surfaced live by run-20260615T024030Z-bcef22:
a concurrent BL labelled merged_full from work_branch readiness, then conflicting at
the assembly barrier, must NOT remain merged_full in the persisted roll-up.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.orchestrator import _reconcile_unassembled_outcome  # noqa: E402


def test_conflict_rewrites_merged_full_to_escalated_assembly():
    outcomes = [
        {"bl_id": "BL-0001", "outcome": "merged_full"},
        {"bl_id": "BL-0002", "outcome": "merged_full"},
    ]
    changed = _reconcile_unassembled_outcome(outcomes, "BL-0002", "conflict")
    assert changed is True
    # BL-0002 corrected; BL-0001 (assembled clean) untouched.
    assert outcomes[0] == {"bl_id": "BL-0001", "outcome": "merged_full"}
    assert outcomes[1] == {"bl_id": "BL-0002", "outcome": "escalated_assembly_conflict"}


def test_error_kind_label():
    outcomes = [{"bl_id": "BL-0003", "outcome": "merged_no_qa"}]
    assert _reconcile_unassembled_outcome(outcomes, "BL-0003", "error") is True
    assert outcomes[0]["outcome"] == "escalated_assembly_error"


def test_missing_kind_falls_back_to_fail():
    outcomes = [{"bl_id": "BL-0004", "outcome": "merged_full"}]
    assert _reconcile_unassembled_outcome(outcomes, "BL-0004", None) is True
    assert outcomes[0]["outcome"] == "escalated_assembly_fail"


def test_unknown_bl_id_is_noop():
    outcomes = [{"bl_id": "BL-0001", "outcome": "merged_full"}]
    assert _reconcile_unassembled_outcome(outcomes, "BL-9999", "conflict") is False
    assert outcomes[0]["outcome"] == "merged_full"
