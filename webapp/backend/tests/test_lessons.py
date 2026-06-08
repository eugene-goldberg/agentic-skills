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


# ─── A63: render the verified A61 dossier, not the thin status blob ──────────


def _mk_dossier_finding(*, fid: str, root_cause: str = "", fix_locus: str = "",
                        evidence: str = '{"status":"fail"}') -> Finding:
    return Finding(
        finding_id=fid, run_id="r1", feature_slug="feat-a", journey_id="01",
        journey_kind="ui", classification="product_bug", evidence_summary=evidence,
        report_path="/tmp/report.json", first_seen_ts="2026-06-08T00:00:00Z",
        last_seen_ts="2026-06-08T00:00:00Z", seen_count=1, verdict="confirmed",
        root_cause=root_cause, fix_locus=fix_locus,
    )


def test_render_prefers_root_cause_over_evidence_summary(tmp_path: Path) -> None:
    """The live smoke gap: a finding whose evidence_summary is a status blob but
    that carries a verified root_cause must render the root_cause, not the blob."""
    f = _mk_dossier_finding(
        fid="d1",
        root_cause="rest-aware streak consumed by ONE caller (api.py:210); NO frontend module calls it",
        fix_locus="components.py:843 (badge) and components.py:967 (echart)",
        evidence='{"classification":"product_bug","id":"01","status":"fail"}',
    )
    block = lsn.render_lessons_block([lsn.Lesson.from_finding(f)])
    assert "rest-aware streak consumed by ONE caller" in block
    assert "fix locus: components.py:843" in block
    # the useless status blob is NOT what gets surfaced
    assert '{"classification":"product_bug","id":"01","status":"fail"}' not in block


def test_render_falls_back_to_summary_without_dossier(tmp_path: Path) -> None:
    f = _mk_dossier_finding(fid="d2", root_cause="", fix_locus="",
                            evidence="PUT bypasses the state machine")
    block = lsn.render_lessons_block([lsn.Lesson.from_finding(f)])
    assert "PUT bypasses the state machine" in block


def test_render_caps_long_root_cause(tmp_path: Path) -> None:
    f = _mk_dossier_finding(fid="d3", root_cause="x" * 5000)
    block = lsn.render_lessons_block([lsn.Lesson.from_finding(f)])
    assert "…" in block
    # the rendered body is bounded (not the full 5000 chars)
    assert len(block) < 2000


def test_lesson_from_finding_carries_dossier() -> None:
    f = _mk_dossier_finding(fid="d4", root_cause="rc", fix_locus="fl")
    lesson = lsn.Lesson.from_finding(f)
    assert lesson.root_cause == "rc"
    assert lesson.fix_locus == "fl"


# ─── ABL-0016 Batch C — injection provenance ────────────────────────────────


def _read_jsonl(path: Path) -> list[dict]:
    import json
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_record_injection_writes_record(tmp_path: Path) -> None:
    lessons = [lsn.Lesson.from_finding(_mk_finding(fid="a1", feature_slug="feat-a"))]
    path = lsn.record_injection("run-x", "engineer", lessons, bl_id="BL-0007", log_dir=tmp_path)
    assert path is not None
    records = _read_jsonl(path)
    assert len(records) == 1
    r = records[0]
    assert r["run_id"] == "run-x"
    assert r["role"] == "engineer"
    assert r["bl_id"] == "BL-0007"
    assert r["lesson_ids"] == ["a1"]
    assert r["classifications"] == ["product_bug"]
    assert r["feature_slugs"] == ["feat-a"]
    assert r["count"] == 1


def test_record_injection_empty_is_noop(tmp_path: Path) -> None:
    path = lsn.record_injection("run-x", "po", [], log_dir=tmp_path)
    assert path is None
    assert not lsn.injection_log_path("run-x", log_dir=tmp_path).exists()


def test_record_injection_appends_per_run(tmp_path: Path) -> None:
    l1 = [lsn.Lesson.from_finding(_mk_finding(fid="a1", feature_slug="feat-a"))]
    l2 = [lsn.Lesson.from_finding(_mk_finding(fid="a1", feature_slug="feat-a"))]
    lsn.record_injection("run-x", "engineer", l1, bl_id="BL-0007", log_dir=tmp_path)
    lsn.record_injection("run-x", "qa", l2, bl_id="BL-0007", log_dir=tmp_path)
    records = _read_jsonl(lsn.injection_log_path("run-x", log_dir=tmp_path))
    assert [r["role"] for r in records] == ["engineer", "qa"]


def test_injection_log_path_keyed_by_run_id(tmp_path: Path) -> None:
    assert lsn.injection_log_path("run-abc", log_dir=tmp_path).name == "run-abc.jsonl"
