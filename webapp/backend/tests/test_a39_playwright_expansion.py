"""Tests for A39: expand the opaque `tests/playwright::e2e_suite` regression
marker into the real per-test Playwright failures.

The gate template (regression_gate.sh) emits a SINGLE synthetic pytest-format
line for the whole Playwright suite (`tests/playwright::e2e_suite FAILED`), so
the parser reports one regression no matter how many E2E tests broke. The
engineer retry prompt then has nothing actionable to fix → it self-runs the
gate to diagnose → the loop that wedged BL-0006 for 8h on 2026-06-04.

`_extract_playwright_failures` parses Playwright's own failure-summary block
out of the gate tail so the orchestrator can hand the engineer real test
names. The sample tails below are verbatim excerpts of the BL-0006 gate run
(run-20260604T145638Z-50c2d9), with ANSI stripped.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.regression_gate import (  # noqa: E402
    PLAYWRIGHT_SUITE_NODEID,
    _extract_playwright_failures,
)


# Verbatim Playwright list-reporter failure summary (the canonical,
# machine-parseable block) from the BL-0006 gate run.
SAMPLE_SUMMARY = (
    "  3 failed\n"
    "    [chromium] › tests/search.spec.ts:11:1 › Search page is accessible and shows correct title ─────\n"
    "    [chromium] › tests/search.spec.ts:24:1 › Smart views and saved searches panel is shown ─────────\n"
    "    [chromium] › tests/search.spec.ts:135:3 › Authenticated search flow › A smart view is runnable from the search UI \n"
    "  7 passed (3.3m)\n"
)

# Verbatim inline numbered-failure form (also present in the same tail).
SAMPLE_INLINE = (
    "·FF\n"
    "  1) [chromium] › tests/search.spec.ts:11:1 › Search page is accessible and shows correct title ────\n"
    "    Error: expect(locator).toBeVisible() failed\n"
    "    Locator: getByRole('heading', { name: 'Search' })\n"
    "  2) [chromium] › tests/search.spec.ts:24:1 › Smart views and saved searches panel is shown ────────\n"
    "    Error: strict mode violation: getByText('Saved searches') resolved to 2 elements:\n"
    "  2 failed\n"
    "    [chromium] › tests/search.spec.ts:11:1 › Search page is accessible and shows correct title ─────\n"
    "    [chromium] › tests/search.spec.ts:24:1 › Smart views and saved searches panel is shown ─────────\n"
    "  1 passed (1.0m)\n"
)


def test_extracts_all_distinct_failures_from_summary() -> None:
    out = _extract_playwright_failures(SAMPLE_SUMMARY)
    locs = [f["location"] for f in out]
    assert locs == [
        "tests/search.spec.ts:11:1",
        "tests/search.spec.ts:24:1",
        "tests/search.spec.ts:135:3",
    ]


def test_nodeids_are_namespaced() -> None:
    out = _extract_playwright_failures(SAMPLE_SUMMARY)
    assert all(f["nodeid"].startswith("tests/playwright::") for f in out)
    assert out[0]["nodeid"] == "tests/playwright::tests/search.spec.ts:11:1"


def test_title_captured_and_dashes_stripped() -> None:
    out = _extract_playwright_failures(SAMPLE_SUMMARY)
    by_loc = {f["location"]: f["title"] for f in out}
    assert by_loc["tests/search.spec.ts:11:1"] == "Search page is accessible and shows correct title"
    # Inner ` › ` in a nested describe-title is preserved.
    assert by_loc["tests/search.spec.ts:135:3"] == (
        "Authenticated search flow › A smart view is runnable from the search UI"
    )
    # No box-drawing fill leaks into any title.
    assert all("─" not in f["title"] for f in out)


def test_dedup_across_repeated_summaries_and_inline() -> None:
    """The summary recurs per retry attempt and inline + summary forms both
    match; the same failing test must appear exactly once."""
    out = _extract_playwright_failures(SAMPLE_INLINE)
    locs = [f["location"] for f in out]
    assert locs == ["tests/search.spec.ts:11:1", "tests/search.spec.ts:24:1"]
    assert len(locs) == len(set(locs))


def test_empty_and_nonmatching_inputs() -> None:
    assert _extract_playwright_failures("") == []
    assert _extract_playwright_failures("nothing playwright here\nall green\n") == []


def test_browser_project_agnostic() -> None:
    """Project label can be firefox/webkit/custom — not just chromium."""
    tail = (
        "  2 failed\n"
        "    [firefox] › tests/a.spec.ts:1:1 › alpha ────\n"
        "    [Mobile Safari] › tests/b.spec.ts:2:2 › beta ────\n"
    )
    out = _extract_playwright_failures(tail)
    assert [f["location"] for f in out] == ["tests/a.spec.ts:1:1", "tests/b.spec.ts:2:2"]


def test_suite_nodeid_constant() -> None:
    assert PLAYWRIGHT_SUITE_NODEID == "tests/playwright::e2e_suite"
