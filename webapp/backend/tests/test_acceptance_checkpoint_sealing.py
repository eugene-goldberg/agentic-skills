"""A64 — seal the acceptance flow's enforcement events (the full-suite
``regression_checkpoint`` + acceptance lifecycle) into a co-located
``phase_events.jsonl`` so the ABL-0017 doctrine-efficacy aggregator can see the
ONE integration checkpoint that protects pre-existing behavior.

Background: A13 sealed the engineer / QA / janitor flows + streaming kills, but
its scope excluded the acceptance flow — so ``regression_checkpoint`` (per A55
"the single place collateral regressions to pre-existing functionality are
caught") contributed zero rows to the efficacy report. The crew's own
doctrine-meta agent surfaced this gap from sealed evidence
(run-20260608T212413Z-9b397a). A64 closes it.

Two halves are pinned here:
  1. READ side — ``doctrine_efficacy.extract_firings`` counts a sealed
     ``regression_checkpoint`` (green→clean, regressed→caught), tolerating the
     ``orchestrator.``-prefixed phase name that ``_evt`` produces, and ignores
     the acceptance lifecycle markers.
  2. WRITE side — a source pin that ``_acceptance_flow`` takes a ``trace`` and
     the sprint runner seals the ``regression_checkpoint`` event, so a future
     edit can't silently re-open the blind spot.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import doctrine_efficacy as eff  # noqa: E402

ORCH = ROOT / "app" / "services" / "orchestrator.py"


def _write_acceptance_trace(archive: Path, run_id: str, events: list[dict]) -> None:
    """Lay down a per-run archive with one acceptance trace dir whose
    phase_events.jsonl holds the given events (schema header first)."""
    d = archive / run_id / f"20260101T000000Z-acceptance-{run_id}"
    d.mkdir(parents=True)
    lines = [json.dumps({"_schema_version": 1})]
    lines += [json.dumps(e) for e in events]
    (d / "phase_events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_regression_checkpoint_green_counts_as_clean(tmp_path: Path) -> None:
    archive = tmp_path / "traces_archive"
    run = "run-a64-green"
    _write_acceptance_trace(archive, run, [
        # _evt prefixes the phase with "orchestrator." — the aggregator must
        # normalize it.
        {"type": "_meta", "phase": "orchestrator.regression_checkpoint", "kind": "green"},
        {"type": "_meta", "phase": "orchestrator.acceptance.start"},
        {"type": "_meta", "phase": "orchestrator.acceptance.done", "validator_ok": True},
    ])
    firings = eff.extract_firings(run, archive_root=archive)
    rc = [f for f in firings if f.rule_id == "regression_checkpoint"]
    assert len(rc) == 1, f"expected exactly one regression_checkpoint firing, got {firings}"
    assert rc[0].caught is False, "a green checkpoint ran clean (no regression caught)"
    # lifecycle markers must NOT register as firings
    assert all(f.rule_id != "acceptance.start" for f in firings)
    assert all(f.rule_id != "acceptance.done" for f in firings)


def test_regression_checkpoint_regressed_counts_as_caught(tmp_path: Path) -> None:
    archive = tmp_path / "traces_archive"
    run = "run-a64-red"
    _write_acceptance_trace(archive, run, [
        {"type": "_meta", "phase": "orchestrator.regression_checkpoint",
         "kind": "regressed", "failing_tests": ["t1"]},
    ])
    firings = eff.extract_firings(run, archive_root=archive)
    rc = [f for f in firings if f.rule_id == "regression_checkpoint"]
    assert len(rc) == 1
    assert rc[0].caught is True, "a regressed checkpoint CAUGHT a collateral regression"


def test_efficacy_report_surfaces_regression_checkpoint(tmp_path: Path) -> None:
    """End-to-end through run_efficacy: the by_rule block gains a
    regression_checkpoint row (previously absent — the whole point of A64)."""
    archive = tmp_path / "traces_archive"
    run = "run-a64-report"
    _write_acceptance_trace(archive, run, [
        {"type": "_meta", "phase": "orchestrator.regression_checkpoint", "kind": "green"},
    ])
    report = eff.run_efficacy(run, archive_root=archive, state_root=tmp_path / "nostate")
    assert "regression_checkpoint" in report["by_rule"], report["by_rule"]
    assert report["by_rule"]["regression_checkpoint"] == {"caught": 0, "clean": 1}


def test_un_prefixed_engineer_events_still_parse(tmp_path: Path) -> None:
    """The prefix-strip must be a no-op for the existing un-prefixed _ptag
    events (bl_tests etc.) — A64 must not regress A13 reading."""
    archive = tmp_path / "traces_archive"
    run = "run-a64-noprefix"
    d = archive / run / "20260101T000000Z-engineer-BL-0001-deadbeef"
    d.mkdir(parents=True)
    (d / "phase_events.jsonl").write_text(
        json.dumps({"_schema_version": 1}) + "\n"
        + json.dumps({"type": "_meta", "phase": "bl_tests", "kind": "green"}) + "\n",
        encoding="utf-8",
    )
    firings = eff.extract_firings(run, archive_root=archive)
    assert any(f.rule_id == "R10" and not f.caught for f in firings), firings


# ── WRITE-side source pins (can't be silently removed) ────────────────────────

def test_acceptance_flow_accepts_trace_param() -> None:
    tree = ast.parse(ORCH.read_text(encoding="utf-8"))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.AsyncFunctionDef) and n.name == "_acceptance_flow"), None)
    assert fn is not None, "_acceptance_flow not found"
    arg_names = {a.arg for a in fn.args.args} | {a.arg for a in fn.args.kwonlyargs}
    assert "trace" in arg_names, "_acceptance_flow must accept a `trace` param (A64)"


def test_sprint_runner_seals_regression_checkpoint() -> None:
    """The sprint runner must build the regression_checkpoint event and seal it
    via write_phase_event before yielding — pin against accidental removal."""
    src = ORCH.read_text(encoding="utf-8")
    assert 'rc_evt = _evt("regression_checkpoint"' in src, \
        "regression_checkpoint must be built into a named event for sealing (A64)"
    assert "acceptance_trace.write_phase_event(rc_evt)" in src, \
        "the regression_checkpoint event must be sealed into the acceptance trace (A64)"
    assert "trace=acceptance_trace" in src, \
        "the acceptance flow must reuse the checkpoint's trace (A64)"
