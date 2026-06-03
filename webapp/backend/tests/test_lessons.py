"""ABL-0016 Batch A — lessons reader + renderer tests.

Covers the target-scoped union, the verdict filter, dedup, ranking, the cap,
and the silent-empty renderer. The headline test is cross-feature memory:
a confirmed finding from feature A must surface when building for feature B
on the same target (that's the whole point of target-scoping — §2.4).

Dormant module; no orchestrator wiring exercised here (that's Batch B).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import lessons as lsn  # noqa: E402
from app.services.findings_ledger import Finding  # noqa: E402


def _mk_finding(
    *,
    fid: str,
    feature_slug: str,
    verdict: str | None = "confirmed",
    classification: str = "product_bug",
    evidence: str = "PUT bypasses the transition state machine",
    seen_count: int = 1,
    last_seen_ts: str = "2026-06-02T00:00:00Z",
) -> Finding:
    return Finding(
        finding_id=fid,
        run_id="r1",
        feature_slug=feature_slug,
        journey_id="03",
        journey_kind="ui",
        classification=classification,
        evidence_summary=evidence,
        report_path="/tmp/report.json",
        first_seen_ts=last_seen_ts,
        last_seen_ts=last_seen_ts,
        seen_count=seen_count,
        verdict=verdict,
    )


def _write_ledger(repo_root: Path, feature_slug: str, findings: list[Finding]) -> None:
    d = repo_root / "_brownfield" / "features" / feature_slug / "acceptance"
    d.mkdir(parents=True, exist_ok=True)
    (d / "findings_log.jsonl").write_text(
        "".join(f.to_jsonl() + "\n" for f in findings), encoding="utf-8"
    )


# ─── empty / absent ─────────────────────────────────────────────────────────


def test_no_brownfield_dir_returns_empty(tmp_path: Path) -> None:
    assert lsn.list_lessons(tmp_path) == []
    assert lsn.render_lessons_block([]) == ""


def test_ledger_with_only_pending_returns_empty(tmp_path: Path) -> None:
    _write_ledger(tmp_path, "feat-a", [_mk_finding(fid="p", feature_slug="feat-a", verdict=None)])
    assert lsn.list_lessons(tmp_path) == []


# ─── verdict filter ─────────────────────────────────────────────────────────


def test_verdict_filter_keeps_confirmed_and_deferred(tmp_path: Path) -> None:
    _write_ledger(tmp_path, "feat-a", [
        _mk_finding(fid="c", feature_slug="feat-a", verdict="confirmed"),
        _mk_finding(fid="d", feature_slug="feat-a", verdict="deferred"),
        _mk_finding(fid="r", feature_slug="feat-a", verdict="refuted"),
        _mk_finding(fid="n", feature_slug="feat-a", verdict=None),
    ])
    ids = {l.lesson_id for l in lsn.list_lessons(tmp_path)}
    assert ids == {"c", "d"}


# ─── cross-feature memory (the headline) ───────────────────────────────────


def test_cross_feature_memory_surfaces_other_features_finding(tmp_path: Path) -> None:
    """A confirmed finding on feature A must surface when building for
    feature B on the same target — the whole point of target-scoping."""
    _write_ledger(tmp_path, "feat-a", [
        _mk_finding(fid="a1", feature_slug="feat-a", verdict="confirmed"),
    ])
    _write_ledger(tmp_path, "feat-b", [])  # B has no findings yet
    lessons = lsn.list_lessons(tmp_path, feature_slug="feat-b")
    assert [l.lesson_id for l in lessons] == ["a1"]
    assert lessons[0].feature_slug == "feat-a"


# ─── dedup ──────────────────────────────────────────────────────────────────


def test_dedup_by_finding_id_keeps_higher_seen_count(tmp_path: Path) -> None:
    # same finding_id present in two ledgers with different seen_count
    _write_ledger(tmp_path, "feat-a", [
        _mk_finding(fid="dup", feature_slug="feat-a", seen_count=1),
    ])
    _write_ledger(tmp_path, "feat-b", [
        _mk_finding(fid="dup", feature_slug="feat-b", seen_count=5),
    ])
    lessons = lsn.list_lessons(tmp_path)
    assert len(lessons) == 1
    assert lessons[0].seen_count == 5


# ─── ranking ────────────────────────────────────────────────────────────────


def test_rank_same_feature_first(tmp_path: Path) -> None:
    _write_ledger(tmp_path, "feat-a", [
        _mk_finding(fid="a1", feature_slug="feat-a", seen_count=1),
    ])
    _write_ledger(tmp_path, "feat-b", [
        _mk_finding(fid="b1", feature_slug="feat-b", seen_count=1),
    ])
    lessons = lsn.list_lessons(tmp_path, feature_slug="feat-b")
    assert lessons[0].lesson_id == "b1"  # same-feature wins despite equal seen_count


def test_rank_seen_count_desc_within_same_feature_class(tmp_path: Path) -> None:
    _write_ledger(tmp_path, "feat-a", [
        _mk_finding(fid="low", feature_slug="feat-a", seen_count=1),
        _mk_finding(fid="high", feature_slug="feat-a", seen_count=9),
    ])
    lessons = lsn.list_lessons(tmp_path)
    assert [l.lesson_id for l in lessons] == ["high", "low"]


# ─── cap ────────────────────────────────────────────────────────────────────


def test_cap_limits_to_top_n(tmp_path: Path) -> None:
    _write_ledger(tmp_path, "feat-a", [
        _mk_finding(fid=f"f{i}", feature_slug="feat-a", seen_count=i)
        for i in range(10)
    ])
    lessons = lsn.list_lessons(tmp_path, cap=3)
    assert len(lessons) == 3
    # top-3 by seen_count desc
    assert [l.lesson_id for l in lessons] == ["f9", "f8", "f7"]


# ─── renderer ───────────────────────────────────────────────────────────────


def test_render_empty_is_silent() -> None:
    assert lsn.render_lessons_block([]) == ""


def test_render_contains_framing_and_lesson_fields(tmp_path: Path) -> None:
    _write_ledger(tmp_path, "feat-a", [
        _mk_finding(fid="a1", feature_slug="feat-a",
                    classification="product_bug",
                    evidence="PUT bypasses the BL-0005 state machine"),
    ])
    block = lsn.render_lessons_block(lsn.list_lessons(tmp_path))
    assert "## Relevant prior lessons (advisory)" in block
    assert "falsification priors" in block          # advisory framing present
    assert "[product_bug]" in block
    assert "feat-a" in block
    assert "PUT bypasses the BL-0005 state machine" in block


def test_render_starts_with_separator(tmp_path: Path) -> None:
    _write_ledger(tmp_path, "feat-a", [_mk_finding(fid="a1", feature_slug="feat-a")])
    block = lsn.render_lessons_block(lsn.list_lessons(tmp_path))
    # leads with a markdown separator so it's visually distinct in the prompt
    assert block.split("\n", 2)[1] == "---"
