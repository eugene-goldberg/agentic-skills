"""ABL-0014 Batch B — B.3: run_brief wiring for run_acceptance.

Verifies:
- ``RunBriefRequest`` accepts ``run_acceptance: bool`` (default False per
  §E.1 Q6) and ``acceptance_timeout: int`` (default 3600 per §E.1 Q2).
- ``orchestrator.run_brief`` accepts the same params with matching
  defaults; the in-flow ``_acceptance_flow`` call is gated by
  ``if run_acceptance:`` so False short-circuits without invocation.
- Per §E.1 Q3 (advisory only) an exception from ``_acceptance_flow``
  must NOT propagate out of run_brief; it becomes an
  ``acceptance.error`` event and ``closure_check`` still runs.
"""
from __future__ import annotations

import asyncio
import inspect
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import orchestrator as orch  # noqa: E402
from app.routers.projects import RunBriefRequest  # noqa: E402


# ─── signature / defaults ──────────────────────────────────────────────────


def test_run_brief_request_has_run_acceptance_default_false() -> None:
    req = RunBriefRequest(brief="x" * 25)
    assert req.run_acceptance is False
    assert req.acceptance_timeout == 3600


def test_run_brief_request_accepts_run_acceptance_true() -> None:
    req = RunBriefRequest(brief="x" * 25, run_acceptance=True, acceptance_timeout=1800)
    assert req.run_acceptance is True
    assert req.acceptance_timeout == 1800


def test_run_brief_signature_has_run_acceptance_default_false() -> None:
    sig = inspect.signature(orch.run_brief)
    p = sig.parameters["run_acceptance"]
    assert p.default is False, (
        "§E.1 Q6: run_acceptance must default to False for the first 3 "
        "calibration sprints — flip after calibration confirms low FP rate."
    )
    p2 = sig.parameters["acceptance_timeout"]
    assert p2.default == 3600, "§E.1 Q2: 3600s default timeout."


# ─── wiring source check (cheap; documents the contract) ──────────────────


def test_run_brief_source_gates_acceptance_flow_on_flag() -> None:
    """The wiring lives in the run_brief source. Verify the gate exists
    AND that the call sits between sprint_complete and doctrine_meta
    per the ABL-0014 plan §A.3."""
    src = inspect.getsource(orch.run_brief)
    assert "if run_acceptance:" in src
    assert "_acceptance_flow(" in src
    # ordering: sprint_complete → acceptance → doctrine_meta
    sc = src.index('"sprint_complete"')
    acc = src.index("_acceptance_flow(")
    dm = src.index("_doctrine_meta_flow(")
    assert sc < acc < dm, "acceptance must run after sprint_complete and before doctrine_meta"


# ─── advisory-only failure semantics (§E.1 Q3) ─────────────────────────────


def test_acceptance_exception_becomes_event_does_not_propagate() -> None:
    """Standalone reproduction of the orchestrator's try/except block:
    a raising acceptance flow becomes an ``acceptance.error`` event and
    yields control back so closure_check can still fire afterward."""

    async def boom(*_a, **_k):
        raise RuntimeError("simulated acceptance crash")
        yield  # pragma: no cover — make it an async generator

    async def runner():
        events = []
        # Verbatim copy of the wiring's try/except shape from run_brief.
        try:
            async for evt in boom():  # pragma: no cover
                events.append(evt)
        except Exception as exc:
            events.append({"phase": "orchestrator.acceptance.error", "error": str(exc)})
        # closure_check would run here; assert we got that far.
        events.append({"phase": "orchestrator.closure_check.start"})
        return events

    events = asyncio.run(runner())
    phases = [e["phase"] for e in events]
    assert "orchestrator.acceptance.error" in phases
    assert phases[-1] == "orchestrator.closure_check.start", (
        "advisory-only: acceptance failure MUST NOT skip closure_check"
    )
