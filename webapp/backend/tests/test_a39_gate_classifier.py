"""Batch 2-1 (AUTONOMY_HARDENING_PLAN.md, C4 / A39a+b + A40) — gate
classification tests against the three real-incident shapes:

- documents_2 BL-0008: frontend build failed → parser reported
  "161 regression(s)" (every baseline test counted as regressed).
- time-tracking BL-0012: biome lint failure burned a retry on a
  one-character auto-fixable problem.
- time-tracking BL-0014: gate said "2 new failure(s)" with an empty
  regressions[] — no identities reached the fix prompt.

Plus the A39b parser invariant: kind=="regressed" ⟹ non-empty
regressions ∪ new_failures.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.regression_gate import (  # noqa: E402
    TestSet,
    classify_gate_outcome,
    _is_build_sentinel,
)
from app.services.doctrine_validator import build_gate_fix_prompt  # noqa: E402

CMD = ["bash", "scripts/regression_gate.sh"]


def _ts(passed=(), failed=(), exit_code=0, tail="") -> TestSet:
    return TestSet(passed=set(passed), failed=set(failed),
                   raw_exit=exit_code, raw_tail=tail)


BASELINE = [f"tests/e2e/spec_{i}.py::test_{i}" for i in range(161)]


# ─── A39a: build failure must not read as mass regression ──────────────────


def test_build_failure_is_not_161_regressions() -> None:
    """documents_2 BL-0008 shape: frontend build fails (stale
    routeTree.gen.ts), no downstream test runs."""
    tail = (
        "src/routeTree.gen.ts(12,3): error TS2305: Module has no exported member 'FolderRoute'.\n"
        "error during build\n"
        "tests/gate::build FAILED\n"
        "... 5KB of container orchestration noise ...\n"
    )
    pre = _ts(passed=BASELINE)
    post = _ts(failed=["tests/gate::build"], exit_code=1, tail=tail)
    out = classify_gate_outcome(pre, post, test_cmd=CMD)

    assert out["kind"] == "build_fail"
    assert out["ok"] is False
    assert out["gate_failure_class"] == "build"
    assert out["regressions"] == [], "baseline tests must NOT be counted as regressions"
    assert out["build_sentinels"] == ["tests/gate::build"]
    assert "downstream tests not run" in out["reason"]
    # The compiler error (before the sentinel), not the container noise
    # (after it), is the extracted block.
    assert "error TS2305" in out["build_error"]
    assert "container orchestration noise" not in out["build_error"]


def test_lint_failure_classifies_as_lint() -> None:
    """time-tracking BL-0012 / A40 shape: biome import-sort failure."""
    tail = (
        "src/routes/_layout/documents/folder.$id.tsx:3:1 ✗ Sort the imported names\n"
        "i Safe fix: Organize imports and exports (Biome)\n"
        "tests/frontend::lint_typecheck_build FAILED\n"
    )
    pre = _ts(passed=BASELINE)
    post = _ts(failed=["tests/frontend::lint_typecheck_build"], exit_code=1, tail=tail)
    out = classify_gate_outcome(pre, post, test_cmd=CMD)

    assert out["kind"] == "build_fail"
    assert out["gate_failure_class"] == "lint"
    assert out["regressions"] == []
    assert "Safe fix" in out["build_error"]


def test_build_fail_fix_prompt_carries_error_not_test_names() -> None:
    """The retry prompt must switch on the failure class: compiler block +
    A40 auto-fix directive, zero test-name noise."""
    tail = "error TS2305: Module has no exported member.\ntests/gate::build FAILED\n"
    pre = _ts(passed=BASELINE)
    post = _ts(failed=["tests/gate::build"], exit_code=1, tail=tail)
    out = classify_gate_outcome(pre, post, test_cmd=CMD)
    prompt = build_gate_fix_prompt("engineer", out, bl_id="BL-0008",
                                   attempt=1, max_attempts=2)
    assert "BUILD step failed" in prompt
    assert "NO tests ran" in prompt
    assert "error TS2305" in prompt
    assert "Safe fix" in prompt or "auto-fix" in prompt  # A40 directive
    assert "spec_42" not in prompt, "no fake regression test names in the prompt"


# ─── A39b: regressed always carries identities ──────────────────────────────


def test_new_failures_reach_the_result_with_identities() -> None:
    """time-tracking BL-0014 shape: real new failures, none shared with pre.
    The result must carry their identities (the incident's empty
    regressions[] left the engineer blind)."""
    pre = _ts(passed=["tests/api/test_a.py::test_x"])
    post = _ts(
        passed=["tests/api/test_a.py::test_x"],
        failed=["tests/api/routes/test_time_settings.py::test_policy_allows_compliant_entry_and_rounds",
                "tests/api/routes/test_time_entries.py::test_assertion"],
        exit_code=1,
        tail="FAILED tests/api/routes/test_time_settings.py::test_policy...\n",
    )
    out = classify_gate_outcome(pre, post, test_cmd=CMD)
    assert out["kind"] == "regressed"
    assert len(out["new_failures"]) == 2
    prompt = build_gate_fix_prompt("engineer", out, bl_id="BL-0014",
                                   attempt=1, max_attempts=2)
    assert "test_policy_allows_compliant_entry_and_rounds" in prompt, (
        "fix prompt must name the failing tests (A39b)"
    )


def test_regressed_invariant_holds_across_shapes() -> None:
    """Property: kind=='regressed' ⟹ regressions ∪ new_failures ≠ ∅."""
    shapes = [
        _ts(passed=["t::a", "t::b"], exit_code=0),
        _ts(passed=["t::a"], failed=["t::b"], exit_code=1),
        _ts(exit_code=1),
        _ts(exit_code=0),
        _ts(passed=["t::a", "t::b"], exit_code=1),
        _ts(failed=["tests/gate::build"], exit_code=1, tail="tests/gate::build FAILED"),
    ]
    pre = _ts(passed=["t::a", "t::b"])
    for post in shapes:
        out = classify_gate_outcome(pre, post, test_cmd=CMD)
        if out["kind"] == "regressed":
            assert out["regressions"] or out["new_failures"], (
                f"A39b violated for post={post.to_dict()}"
            )


def test_exit_nonzero_nothing_parsed_is_inconclusive() -> None:
    pre = _ts(passed=["t::a"])
    post = _ts(exit_code=1, tail="import error before any test ran")
    out = classify_gate_outcome(pre, post, test_cmd=CMD)
    assert out["kind"] == "inconclusive"
    assert out["gate_failure_class"] == "test"


def test_green_pathway_unchanged() -> None:
    pre = _ts(passed=["t::a", "t::b"])
    post = _ts(passed=["t::a", "t::b", "t::c"], exit_code=0)
    out = classify_gate_outcome(pre, post, test_cmd=CMD)
    assert out["ok"] is True and out["kind"] == "green"
    assert out["gate_failure_class"] is None


# ─── precedence: infra beats build beats test ───────────────────────────────


def test_infra_marker_wins_over_build_sentinel() -> None:
    """A48/A25b precedence preserved: ENOSPC under the build step is an
    infra failure (operator action), not a build failure (agent action)."""
    tail = (
        "psycopg.errors.DiskFull: could not extend file \"base/16384/16505\": "
        "No space left on device\n"
        "tests/gate::build FAILED\n"
    )
    pre = _ts(passed=BASELINE)
    post = _ts(failed=["tests/gate::build"], exit_code=1, tail=tail)
    out = classify_gate_outcome(pre, post, test_cmd=CMD)
    assert out["kind"] == "infra_fail"
    assert out["gate_failure_class"] == "infra"
    assert out["infra_fail_reason"] == "host_disk_full"


# ─── sentinel matcher precision ─────────────────────────────────────────────


def test_sentinel_matcher_precision() -> None:
    assert _is_build_sentinel("tests/gate::build")
    assert _is_build_sentinel("tests/frontend::lint_typecheck_build")
    assert not _is_build_sentinel("tests/api/test_builder.py::test_build_invoice"), (
        "a real test about 'building' invoices is not a sentinel"
    )
    assert not _is_build_sentinel("tests/gate/test_real.py::test_x")
    assert not _is_build_sentinel("plainstring")
