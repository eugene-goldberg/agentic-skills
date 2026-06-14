"""Live-acceptance convergence loop decision (PROPOSAL_LIVE_ACCEPTANCE_LOOP).

The loop boots the whole app, exercises every AC, dispatches fixes on defects,
and re-boots/re-exercises until acceptance accepts every criterion live — or
escalates honestly. `_acceptance_loop_next` is the pure decision at each round.
"""
from app.services.orchestrator import _acceptance_loop_next as nxt
MAX = 5


def test_accept_when_integrity_ok():
    assert nxt({"integrity_ok": True, "dispatched_count": 0}, 1, MAX) == "accept"
    # integrity_ok wins even if other fields look mid-loop
    assert nxt({"integrity_ok": True, "open_failures": [], "dispatched_count": 3}, 4, MAX) == "accept"


def test_reround_when_progress_and_rounds_remain():
    # not clean, but a fix was dispatched this round and rounds remain → re-verify
    assert nxt({"integrity_ok": False, "dispatched_count": 2}, 1, MAX) == "reround"
    assert nxt({"integrity_ok": False, "dispatched_count": 1}, 4, MAX) == "reround"


def test_escalate_when_no_progress():
    # not clean and nothing was dispatched (unactionable) → escalate, don't spin
    assert nxt({"integrity_ok": False, "dispatched_count": 0,
                "unverified_criteria": ["AC-BL-0001-3"]}, 1, MAX) == "escalate"


def test_escalate_when_rounds_exhausted():
    # progress was made but we're on the last allowed round → escalate, not reround
    assert nxt({"integrity_ok": False, "dispatched_count": 2}, MAX, MAX) == "escalate"


def test_none_round_done_escalates():
    # acceptance produced no terminal verdict (crash/empty) → escalate honestly
    assert nxt(None, 1, MAX) == "escalate"


def test_missing_dispatched_count_treated_as_zero():
    assert nxt({"integrity_ok": False}, 1, MAX) == "escalate"


# -- acceptance-reround worktree-branch collision fix --------------------------
# run-20260614T143621Z-0b7c91: the live-acceptance loop found 2 UI product_bugs,
# dispatched+merged fixes, then the round-2 re-verify died at
# `git worktree add -b agent/accept-<run_id>` because the round-1 branch still
# existed -> acceptance.skipped(worktree_failed) -> escalated integrity_ok=false.
# The worktree task id must be round-unique (round 1 unchanged for back-compat).
from app.services.orchestrator import _accept_worktree_task_id as wtid


def test_accept_worktree_task_id_round1_is_historical():
    assert wtid("run-X", 1) == "accept-run-X"
    assert wtid("run-X", 0) == "accept-run-X"  # defensive: <=1 -> base


def test_accept_worktree_task_id_reround_is_suffixed():
    assert wtid("run-X", 2) == "accept-run-X-r2"
    assert wtid("run-X", 5) == "accept-run-X-r5"


def test_accept_worktree_task_id_all_rounds_distinct():
    names = [wtid("run-20260614T143621Z-0b7c91", r) for r in range(1, MAX + 1)]
    assert len(set(names)) == len(names), names
