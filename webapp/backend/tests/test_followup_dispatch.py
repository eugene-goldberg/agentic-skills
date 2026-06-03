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
