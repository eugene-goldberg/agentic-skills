"""R18 — PO acceptance-criteria as the unit of truth (chain component 1).

Covers:
- backlog.extract_criteria parses the numbered `**Acceptance:**` block into
  stable `AC-<BL>-<n>` IDs, tolerating multi-line criteria + trailing meta.
- backlog.thin_criteria_report flags BLs with missing/thin criteria.
- doctrine_validator.validate_po fails (not ok) when a BL has thin criteria, and
  build_fix_prompt routes to the criteria-specific (BACKLOG-editing) prompt.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import backlog as backlog_svc  # noqa: E402
from app.services import doctrine_validator as dv  # noqa: E402


_GOOD_BL = """## BL-0003: Submit a review (write)
**Type:** Feature · **Priority:** CRITICAL
**Story:** As a signed-in user, I want to submit a review.
**REQ mapping:** REQ-B4
**Impacted Components:** ReviewController.cs
**Risk Level:** Medium
**Spike Tasks:** none
**Acceptance:**
1. A signed-in user submits (rating 1-5, text) for an existing product and it is
   persisted, then re-reading the product returns the new review.
2. Rating outside 1-5 returns HTTP 400 and persists nothing.
3. A second submit by the same user for the same product never creates a duplicate.
**Effort:** 3 · **Dependencies:** none · **Status:** Ready
"""

_THIN_BL = """## BL-0007: Reviews UI (write)
**Type:** Feature · **Priority:** CRITICAL
**Story:** As a shopper I want a reviews section.
**REQ mapping:** REQ-C7
**Risk Level:** Medium
**Acceptance:**
1. It works.
**Effort:** 4 · **Dependencies:** none · **Status:** Ready
"""

_NO_AC_BL = """## BL-0009: Card badge
**Type:** Feature · **Priority:** HIGH
**Story:** As a shopper I want a badge.
**REQ mapping:** REQ-C9
**Effort:** 2 · **Dependencies:** none · **Status:** Ready
"""


def test_extract_criteria_stable_ids_and_text() -> None:
    item = backlog_svc.parse(_GOOD_BL)[0]
    crits = backlog_svc.extract_criteria(item)
    assert [c.id for c in crits] == ["AC-BL-0003-1", "AC-BL-0003-2", "AC-BL-0003-3"]
    # multi-line criterion is whitespace-normalised, trailing **Effort:** excluded
    assert crits[0].text.startswith("A signed-in user submits")
    assert "Effort" not in crits[0].text
    assert crits[1].text == "Rating outside 1-5 returns HTTP 400 and persists nothing."


def test_thin_criteria_report_flags_thin_and_missing() -> None:
    items = backlog_svc.parse(_GOOD_BL + "\n" + _THIN_BL + "\n" + _NO_AC_BL)
    report = backlog_svc.thin_criteria_report(items)
    assert "BL-0003" not in report          # comprehensive → passes
    assert "BL-0007" in report              # one trivial criterion → thin
    assert "BL-0009" in report              # no acceptance block → flagged


def test_validate_po_fails_on_thin_criteria(tmp_path: Path) -> None:
    # Build a minimal feature artifact tree the validator expects, with a
    # BACKLOG whose single BL has thin criteria.
    slug = "feat_x"
    art = tmp_path / "_brownfield" / "features" / slug
    (art / "_codebase_context").mkdir(parents=True)
    (art / "_codebase_context" / "CODEBASE_CONTEXT.md").write_text("x" * 200)
    (art / "SPRINT_PLAN_C1.md").write_text("x" * 200)
    # BL-0001 thin; give it the per-BL context file so ONLY criteria fail.
    (art / "BL-0001").mkdir()
    (art / "BL-0001" / "codebase_context.md").write_text("x" * 200)
    backlog = _THIN_BL.replace("BL-0007", "BL-0001")
    (art / "BACKLOG.md").write_text(backlog)

    res = dv.validate_po(tmp_path, feature_slug=slug)
    assert res["ok"] is False
    assert res["thin_criteria"], "expected thin_criteria to be populated"
    assert "BL-0001" in res["thin_criteria"]
    # the fix prompt must be the criteria-editing variant (allows BACKLOG edits)
    prompt = dv.build_fix_prompt("po", res)
    assert "Acceptance criteria are the contract" in prompt or "R18" in prompt
    assert "edit its `**Acceptance:**` block" in prompt or "BACKLOG.md" in prompt


def test_validate_po_passes_with_comprehensive_criteria(tmp_path: Path) -> None:
    slug = "feat_ok"
    art = tmp_path / "_brownfield" / "features" / slug
    (art / "_codebase_context").mkdir(parents=True)
    (art / "_codebase_context" / "CODEBASE_CONTEXT.md").write_text("x" * 200)
    (art / "SPRINT_PLAN_C1.md").write_text("x" * 200)
    (art / "BL-0001").mkdir()
    (art / "BL-0001" / "codebase_context.md").write_text("x" * 200)
    (art / "BACKLOG.md").write_text(_GOOD_BL.replace("BL-0003", "BL-0001"))

    res = dv.validate_po(tmp_path, feature_slug=slug)
    assert res["ok"] is True, res["summary"]
    assert not res["thin_criteria"]
