"""Wave-concurrency assembly-eligibility honesty (frontend-concurrency diagnostic,
2026-06-16). Unit truth-table for `_concurrent_assembly_decision`.

Bug: in concurrent wave mode a BL whose engineer passed its green gate but whose
QA added no reinforcement commit (qa_merged=False — the common frontend case, the
engineer already wrote the BL's tests) was labelled `merged_no_qa`, counted in
merged_total, yet NEVER assembled onto the trunk (assembly required qa_merged).
Serial mode keeps that engineer-green code on the trunk; concurrent stranded it.
Fix: eligibility = engineer-green + qa_doctrine_ok (NOT qa_merged); a non-eligible
BL escalates and never carries a merged_* label.
"""
from app.services.orchestrator import _concurrent_assembly_decision as D


def test_full_pass_is_merged_full_eligible():
    assert D(qa_doc_ok=True, qa_merged=True, score_doc_ok=True) == ("merged_full", True)


def test_scorer_doctrine_fail_is_merged_no_score_still_eligible():
    assert D(qa_doc_ok=True, qa_merged=True, score_doc_ok=False) == ("merged_no_score", True)


def test_qa_added_nothing_now_ships_as_merged_no_qa():
    # THE FIX: engineer-green + qa doctrine ok but qa added no reinforcement commit
    # → ships (assembles) as merged_no_qa instead of being stranded off-trunk.
    assert D(qa_doc_ok=True, qa_merged=False, score_doc_ok=True) == ("merged_no_qa", True)
    assert D(qa_doc_ok=True, qa_merged=False, score_doc_ok=False) == ("merged_no_qa", True)


def test_qa_doctrine_fail_escalates_and_never_carries_merged_label():
    label, eligible = D(qa_doc_ok=False, qa_merged=False, score_doc_ok=False)
    assert eligible is False
    assert label == "qa_escalated"
    assert not label.startswith("merged")  # honesty invariant


def test_honesty_invariant_merged_label_iff_eligible():
    # exhaustive 2x2x2 truth table — a merged_* label appears IFF assembly-eligible.
    for q in (True, False):
        for m in (True, False):
            for sc in (True, False):
                label, eligible = D(qa_doc_ok=q, qa_merged=m, score_doc_ok=sc)
                assert label.startswith("merged") == eligible, (q, m, sc, label, eligible)
