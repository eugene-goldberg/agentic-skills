"""ABL-0015 Batch C — auto-dispatch selector, section builder, dispatch loop.

Covers the unit-testable surface of the dispatch block:
- ``_select_followup_candidates`` — conservative verdict gate (§9 D1),
  R15 dispatch-at-most-once idempotency, cost cap (§9 D2).
- ``_build_followup_section`` / ``_followup_hypothesis`` — the engineer
  task text fed in place of a BACKLOG entry.
- ``_resolve_engineer_section`` — the override branch in _engineer_flow.
- ``_dispatch_followup_engineers`` — behavioral test with a faked
  ``_engineer_flow`` (no claude/docker), asserting R15 stamping, outcome
  capture, and event emission against a real ledger file.

The full live e2e (real engineer subprocess + gate + merge) on the
Journey 03 finding is Batch E (operator-gated calibration smoke).
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import orchestrator as orch  # noqa: E402
from app.services import findings_ledger as fl  # noqa: E402
from app.services.findings_ledger import Finding, FindingsLedger  # noqa: E402


def _mk_finding(
    *,
    fid: str = "sha256:f1",
    classification: str = "product_bug",
    verdict: str | None = "confirmed",
    dispatch_state: str | None = None,
    journey_id: str = "03",
    evidence: str = "PUT bypasses the transition state machine",
    report_path: str = "/tmp/report.json",
    confidence: float | None = None,
) -> Finding:
    return Finding(
        finding_id=fid,
        run_id="r1",
        feature_slug="feat_a",
        journey_id=journey_id,
        journey_kind="ui",
        classification=classification,
        evidence_summary=evidence,
        report_path=report_path,
        first_seen_ts="2026-06-02T00:00:00Z",
        last_seen_ts="2026-06-02T00:00:00Z",
        seen_count=1,
        verdict=verdict,
        dispatch_state=dispatch_state,
        confidence=confidence,
    )


# ─── selector (§9 D1 conservative gate + R15 + cost cap) ───────────────────


def test_selector_picks_confirmed_product_bug() -> None:
    f = _mk_finding()
    chosen, capped = orch._select_followup_candidates([f])
    assert [c.finding_id for c in chosen] == ["sha256:f1"]
    assert capped == 0


def test_selector_excludes_pending_refuted_deferred() -> None:
    findings = [
        _mk_finding(fid="p", verdict=None),
        _mk_finding(fid="r", verdict="refuted"),
        _mk_finding(fid="d", verdict="deferred"),
    ]
    chosen, capped = orch._select_followup_candidates(findings)
    assert chosen == []
    assert capped == 0


def test_selector_excludes_non_product_bug() -> None:
    findings = [
        _mk_finding(fid="t", classification="test_bug"),
        _mk_finding(fid="i", classification="infra_bug"),
        _mk_finding(fid="u", classification="uncertain"),
    ]
    chosen, _ = orch._select_followup_candidates(findings)
    assert chosen == []


def test_selector_r15_excludes_already_dispatched() -> None:
    """R15: a finding with any dispatch_state is never re-selected."""
    findings = [
        _mk_finding(fid="a", dispatch_state="dispatched"),
        _mk_finding(fid="b", dispatch_state="merged"),
        _mk_finding(fid="c", dispatch_state="not_merged"),
    ]
    chosen, _ = orch._select_followup_candidates(findings)
    assert chosen == []


def test_selector_cost_cap() -> None:
    findings = [_mk_finding(fid=f"f{i}") for i in range(4)]
    chosen, capped = orch._select_followup_candidates(findings, cost_cap=1)
    assert len(chosen) == 1
    assert capped == 3


# ─── A60: confidence-gated auto-confirm (crew resolves, doesn't just flag) ──────

def test_autoconfirm_high_confidence_unverdicted_product_bug() -> None:
    """The Exp-2 case: a product_bug the agent root-caused at 0.97 with
    verdict still null must be dispatched — the crew resolves what it finds."""
    f = _mk_finding(fid="hi", verdict=None, confidence=0.97)
    chosen, _ = orch._select_followup_candidates([f])
    assert [c.finding_id for c in chosen] == ["hi"]
    assert orch._finding_dispatch_eligible(f) is True


def test_autoconfirm_threshold_boundary() -> None:
    assert orch._finding_dispatch_eligible(_mk_finding(verdict=None, confidence=0.90)) is True
    assert orch._finding_dispatch_eligible(_mk_finding(verdict=None, confidence=0.89)) is False
    assert orch._finding_dispatch_eligible(_mk_finding(verdict=None, confidence=None)) is False


def test_autoconfirm_never_overrides_operator_rejection() -> None:
    """An operator who rejected a finding wins even at high confidence —
    auto-confirm only fires when the verdict is still un-adjudicated (None)."""
    for v in ("refuted", "deferred", "rejected", "false_positive"):
        assert orch._finding_dispatch_eligible(
            _mk_finding(verdict=v, confidence=0.99)) is False


def test_autoconfirm_only_product_bugs() -> None:
    for cls in ("test_bug", "infra_bug", "uncertain"):
        assert orch._finding_dispatch_eligible(
            _mk_finding(classification=cls, verdict=None, confidence=0.99)) is False


def test_autoconfirm_respects_r15_dispatch_state() -> None:
    assert orch._finding_dispatch_eligible(
        _mk_finding(verdict=None, confidence=0.99, dispatch_state="merged")) is False


# ─── A61 (Lever A): full-locus deterministic resolution ────────────────────────

def _mk_dossier_finding(**kw) -> Finding:
    base = dict(
        finding_id="sha256:loc", run_id="r1", feature_slug="feat_a", journey_id="01",
        journey_kind="ui", classification="product_bug",
        evidence_summary='{"id":"01","status":"fail"}', report_path="/tmp/report.json",
        first_seen_ts="2026-06-08T00:00:00Z", last_seen_ts="2026-06-08T00:00:00Z",
        seen_count=1,
    )
    base.update(kw)
    return Finding(**base)


def test_followup_section_surfaces_full_dossier_and_mandates_per_surface_tests() -> None:
    """The Exp-2 miss: the fix_locus named TWO surfaces (badge + echart); the
    engineer fixed one. The section must surface the full root_cause/fix_locus
    AND mandate a deterministic test per surface, so the engineer's own gate loop
    can't merge until every named surface is green (deterministic re-verify)."""
    f = _mk_dossier_finding(
        root_cause="badge -> current_streak; echart still -> compose_habit_streaks",
        fix_locus="components.py:849 (badge) AND components.py:964 (echart)",
        source_refs=["beaverhabits/frontend/components.py:964"],
        alternatives_falsified="data_bug ruled out — same records, two functions",
    )
    s = orch._build_followup_section(f)
    # full dossier surfaced (not just the thin status summary)
    assert "components.py:964" in s
    assert "compose_habit_streaks" in s
    assert "components.py:964" in s
    assert "data_bug ruled out" in s
    # full-locus + per-surface-test mandate present
    assert "EVERY surface" in s
    assert "regression test" in s
    # partial fix is explicitly called a failure
    assert "partial fix" in s.lower() or "FAILURE" in s


def test_followup_section_degrades_without_dossier() -> None:
    """Pre-v0.2 findings (no root_cause/fix_locus) still produce a valid section —
    the dossier blocks just omit, the mandate prose remains."""
    f = _mk_dossier_finding()  # no dossier fields
    s = orch._build_followup_section(f)
    assert "Remediation task" in s
    assert "EVERY surface" in s  # the binding instruction is unconditional


def test_cost_cap_default_is_one() -> None:
    assert orch.FOLLOWUP_COST_CAP == 1


# ─── section + hypothesis builders ─────────────────────────────────────────


def test_build_section_contains_scope_and_po_absent_note() -> None:
    f = _mk_finding()
    s = orch._build_followup_section(f, hypothesis="backend/app/.../invoices.py update_invoice")
    assert f.finding_id in s
    assert f.journey_id in s
    assert f.evidence_summary in s
    assert f.report_path in s
    assert "ABSENT" in s  # PO context-absent compensation note
    assert "update_invoice" in s
    assert "eng_patterns.md" in s  # doctrine artifact reminder


def test_build_section_hypothesis_fallback_when_empty() -> None:
    s = orch._build_followup_section(_mk_finding(), hypothesis="")
    assert "none recorded" in s


def test_followup_hypothesis_reads_caveat_from_report(tmp_path: Path) -> None:
    report = {
        "ui_journeys": [
            {"id": "03", "status": "pass_with_caveat",
             "caveat": {"classification": "product_bug",
                        "hypothesis": "backend/app/api/routes/billing/invoices.py update_invoice"}},
        ]
    }
    p = tmp_path / "report.json"
    p.write_text(json.dumps(report), encoding="utf-8")
    f = _mk_finding(report_path=str(p))
    assert orch._followup_hypothesis(f) == \
        "backend/app/api/routes/billing/invoices.py update_invoice"


def test_followup_hypothesis_missing_report_returns_empty() -> None:
    f = _mk_finding(report_path="/nonexistent/report.json")
    assert orch._followup_hypothesis(f) == ""


# ─── _resolve_engineer_section override branch ─────────────────────────────


def test_resolve_section_uses_override_without_backlog(monkeypatch) -> None:
    def _boom(*a, **k):
        raise AssertionError("backlog must NOT be consulted when override set")
    monkeypatch.setattr(orch.backlog_svc, "find_backlog", _boom)
    out = orch._resolve_engineer_section(
        Path("/repo"), "BL-ACCEPT-r1-0", "feat_a", "OVERRIDE TASK TEXT",
    )
    assert out == "OVERRIDE TASK TEXT"


def test_resolve_section_reads_backlog_when_no_override(monkeypatch) -> None:
    class _BF:
        def read_text(self, encoding="utf-8"):
            return "FULL BACKLOG"
    monkeypatch.setattr(orch.backlog_svc, "find_backlog", lambda *a, **k: _BF())
    monkeypatch.setattr(orch.backlog_svc, "extract_section",
                        lambda text, bl_id: f"SECTION[{bl_id}] from {text}")
    out = orch._resolve_engineer_section(Path("/repo"), "BL-0005", "feat_a", None)
    assert out == "SECTION[BL-0005] from FULL BACKLOG"


# ─── dispatch generator (faked engineer, real ledger) ──────────────────────


def _drain(agen):
    async def run():
        return [e async for e in agen]
    return asyncio.run(run())


def test_dispatch_no_candidates_emits_skipped(tmp_path: Path) -> None:
    ledger = FindingsLedger(tmp_path, "feat_a")
    ledger._ensure_parent()
    # one pending (unconfirmed) product_bug — must NOT dispatch
    ledger.path.write_text(_mk_finding(verdict=None).to_jsonl() + "\n", encoding="utf-8")
    events = _drain(orch._dispatch_followup_engineers(
        tmp_path, "repo", "r1", "feat_a", lambda *a, **k: {}, timeout=60,
    ))
    phases = [e.get("phase") for e in events]
    assert "orchestrator.acceptance.followup.skipped" in phases
    assert any(e.get("reason") == "no_confirmed_candidates" for e in events)


def test_dispatch_confirmed_finding_marks_merged(tmp_path: Path, monkeypatch) -> None:
    """End-to-end through the dispatch helper with a faked _engineer_flow:
    confirmed finding -> dispatched stamp -> merged outcome captured ->
    ledger reflects merged + merged_sha; start/done events emitted."""
    ledger = FindingsLedger(tmp_path, "feat_a")
    ledger._ensure_parent()
    ledger.path.write_text(_mk_finding(fid="sha256:c1").to_jsonl() + "\n", encoding="utf-8")

    seen = {}

    async def fake_engineer_flow(repo_dir, repo_name, bl_id, timeout,
                                 rkb, *, run_id=None, feature_slug=None,
                                 section_override=None, task_id=None):
        seen["bl_id"] = bl_id
        seen["section_override"] = section_override
        seen["task_id"] = task_id
        yield {"type": "_meta", "phase": "merge_to_target", "ok": True,
               "merged_sha": "abc1234", "bl_id": bl_id}
        yield {"_orchestrator_outcome": True, "role": "engineer",
               "bl_id": bl_id, "merged": True, "no_op": False}

    monkeypatch.setattr(orch, "_engineer_flow", fake_engineer_flow)
    events = _drain(orch._dispatch_followup_engineers(
        tmp_path, "repo", "run-X", "feat_a", lambda *a, **k: {}, timeout=60,
    ))

    phases = [e.get("phase") for e in events]
    assert "orchestrator.acceptance.followup.start" in phases
    assert "orchestrator.acceptance.followup.done" in phases
    done = next(e for e in events if e.get("phase") == "orchestrator.acceptance.followup.done")
    assert done["outcome"] == "merged"
    assert done["merged_sha"] == "abc1234"
    # synthetic BL id + section override threaded into the engineer
    assert seen["bl_id"] == "BL-ACCEPT-run-X-0"
    assert "Remediation task" in seen["section_override"]
    # ABL-0015 Batch D: scannable run_id-bearing worktree task_id
    assert seen["task_id"] == "followup-run-X-0"
    # ledger now reflects the terminal state
    f = ledger.list_all()[0]
    assert f.dispatch_state == "merged"
    assert f.dispatch_merged_sha == "abc1234"
    assert f.dispatch_bl_id == "BL-ACCEPT-run-X-0"


# ─── A62: self-resolution -> lessons seam closure ──────────────────────────


@pytest.fixture(autouse=True)
def _stub_lesson_writethrough(monkeypatch):
    """ABL-0016 Stage 1.5: stub the vector write-through so dispatch tests stay
    hermetic (no real Ollama/Milvus) and we can assert it fired. Records
    (repo_root, lesson) tuples."""
    calls = []
    def _rec(repo_root, lesson, **kw):
        calls.append((repo_root, lesson))
        return True
    monkeypatch.setattr(orch.lessons_index_svc, "upsert_lesson", _rec)
    return calls


def test_should_self_confirm_helper() -> None:
    """Pure decision: a self-confirmed (verdict=None) finding that merged earns
    a confirmed verdict; an operator-verdicted one or a non-merge does not."""
    assert orch._should_self_confirm(_mk_finding(verdict=None), merged=True) is True
    assert orch._should_self_confirm(_mk_finding(verdict=None), merged=False) is False
    # operator already adjudicated -> never overwrite (their call wins)
    assert orch._should_self_confirm(_mk_finding(verdict="confirmed"), merged=True) is False
    assert orch._should_self_confirm(_mk_finding(verdict="deferred"), merged=True) is False


def _fake_merge_flow(merged: bool):
    async def fake_engineer_flow(repo_dir, repo_name, bl_id, timeout, rkb, *,
                                 run_id=None, feature_slug=None,
                                 section_override=None, task_id=None):
        if merged:
            yield {"type": "_meta", "phase": "merge_to_target", "ok": True,
                   "merged_sha": "def5678", "bl_id": bl_id}
        yield {"_orchestrator_outcome": True, "role": "engineer",
               "bl_id": bl_id, "merged": merged, "no_op": False}
    return fake_engineer_flow


def test_self_confirmed_finding_becomes_lesson_on_merge(tmp_path: Path, monkeypatch) -> None:
    """A62 headline: a high-confidence self-confirmed product_bug (verdict=None)
    whose fix MERGES gets verdict=confirmed written back — so the ABL-0016
    lessons read-path now surfaces it. Closes the cumulative loop end-to-end."""
    from app.services import lessons as lsn
    ledger = FindingsLedger(tmp_path, "feat_a")
    ledger._ensure_parent()
    ledger.path.write_text(
        _mk_finding(fid="sha256:self1", verdict=None, confidence=0.97).to_jsonl() + "\n",
        encoding="utf-8",
    )
    # before: no confirmed lessons (verdict is None -> filtered out)
    assert lsn.list_lessons(tmp_path) == []

    monkeypatch.setattr(orch, "_engineer_flow", _fake_merge_flow(merged=True))
    events = _drain(orch._dispatch_followup_engineers(
        tmp_path, "repo", "run-SC", "feat_a", lambda *a, **k: {}, timeout=60,
    ))

    # verdict written back + provenance marker present
    f = ledger.list_all()[0]
    assert f.verdict == "confirmed"
    assert "self-confirmed by crew" in (f.verdict_note or "")
    assert "def5678" in (f.verdict_note or "")
    # observable: a self_confirmed event was emitted
    assert any(e.get("phase") == "orchestrator.acceptance.followup.self_confirmed"
               for e in events)
    # END-TO-END: the lessons read-path now surfaces this as a durable lesson
    lessons = lsn.list_lessons(tmp_path)
    assert [l.lesson_id for l in lessons] == ["sha256:self1"]
    assert lessons[0].classification == "product_bug"


def test_self_confirm_writes_lesson_through_to_vector_index(tmp_path: Path, monkeypatch, _stub_lesson_writethrough) -> None:
    """A62→Stage1.5: the just-confirmed lesson is indexed into the vector store
    (write-through) so search_lessons can match it by problem statement, and a
    lesson_indexed event is emitted."""
    ledger = FindingsLedger(tmp_path, "feat_a")
    ledger._ensure_parent()
    ledger.path.write_text(
        _mk_finding(fid="sha256:wt", verdict=None, confidence=0.97).to_jsonl() + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(orch, "_engineer_flow", _fake_merge_flow(merged=True))
    events = _drain(orch._dispatch_followup_engineers(
        tmp_path, "repo", "run-WT", "feat_a", lambda *a, **k: {}, timeout=60,
    ))
    # write-through fired with the CONFIRMED lesson
    assert len(_stub_lesson_writethrough) == 1
    repo_root, lesson = _stub_lesson_writethrough[0]
    assert lesson.lesson_id == "sha256:wt"
    assert lesson.verdict == "confirmed"
    assert any(e.get("phase") == "orchestrator.acceptance.followup.lesson_indexed"
               for e in events)


def test_no_writethrough_when_not_merged(tmp_path: Path, monkeypatch, _stub_lesson_writethrough) -> None:
    ledger = FindingsLedger(tmp_path, "feat_a")
    ledger._ensure_parent()
    ledger.path.write_text(
        _mk_finding(fid="sha256:wt2", verdict=None, confidence=0.97).to_jsonl() + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(orch, "_engineer_flow", _fake_merge_flow(merged=False))
    _drain(orch._dispatch_followup_engineers(
        tmp_path, "repo", "run-WT2", "feat_a", lambda *a, **k: {}, timeout=60,
    ))
    assert _stub_lesson_writethrough == []


def test_self_confirm_not_written_when_fix_not_merged(tmp_path: Path, monkeypatch) -> None:
    """A non-merged fix proves nothing — verdict stays None, no lesson, no event."""
    from app.services import lessons as lsn
    ledger = FindingsLedger(tmp_path, "feat_a")
    ledger._ensure_parent()
    ledger.path.write_text(
        _mk_finding(fid="sha256:nm", verdict=None, confidence=0.97).to_jsonl() + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(orch, "_engineer_flow", _fake_merge_flow(merged=False))
    events = _drain(orch._dispatch_followup_engineers(
        tmp_path, "repo", "run-NM", "feat_a", lambda *a, **k: {}, timeout=60,
    ))
    f = ledger.list_all()[0]
    assert f.verdict is None
    assert f.dispatch_state == "not_merged"
    assert lsn.list_lessons(tmp_path) == []
    assert not any(e.get("phase") == "orchestrator.acceptance.followup.self_confirmed"
                   for e in events)


def test_operator_verdict_not_clobbered_by_self_confirm(tmp_path: Path, monkeypatch) -> None:
    """An operator-confirmed finding that merges keeps the operator's verdict +
    note untouched — no self-confirm write, no self_confirmed event."""
    ledger = FindingsLedger(tmp_path, "feat_a")
    ledger._ensure_parent()
    ledger.path.write_text(
        _mk_finding(fid="sha256:op", verdict="confirmed").to_jsonl() + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(orch, "_engineer_flow", _fake_merge_flow(merged=True))
    events = _drain(orch._dispatch_followup_engineers(
        tmp_path, "repo", "run-OP", "feat_a", lambda *a, **k: {}, timeout=60,
    ))
    f = ledger.list_all()[0]
    assert f.verdict == "confirmed"
    assert "self-confirmed by crew" not in (f.verdict_note or "")
    assert not any(e.get("phase") == "orchestrator.acceptance.followup.self_confirmed"
                   for e in events)


def test_dispatch_is_idempotent_on_rerun(tmp_path: Path, monkeypatch) -> None:
    """R15: re-running dispatch after a finding is merged yields no second
    spawn (selector excludes non-null dispatch_state)."""
    ledger = FindingsLedger(tmp_path, "feat_a")
    ledger._ensure_parent()
    ledger.path.write_text(
        _mk_finding(fid="sha256:c2", dispatch_state="merged").to_jsonl() + "\n",
        encoding="utf-8",
    )

    spawns = {"n": 0}

    async def fake_engineer_flow(*a, **k):
        spawns["n"] += 1
        yield {"_orchestrator_outcome": True, "merged": True}

    monkeypatch.setattr(orch, "_engineer_flow", fake_engineer_flow)
    events = _drain(orch._dispatch_followup_engineers(
        tmp_path, "repo", "r2", "feat_a", lambda *a, **k: {}, timeout=60,
    ))
    assert spawns["n"] == 0
    assert any(e.get("reason") == "no_confirmed_candidates" for e in events)
