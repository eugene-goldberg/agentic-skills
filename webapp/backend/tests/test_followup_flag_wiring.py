"""ABL-0015 Batch B — flag plumbing for run_acceptance_followup.

Verifies the auto-dispatch flag and the retrieval_kwargs_builder needed
to spawn a follow-up engineer are threaded end-to-end:

- ``RunBriefRequest`` accepts ``run_acceptance_followup: bool`` and it
  defaults False (the framework's highest-risk action stays OFF until a
  live calibration smoke — ABL-0015_AUTO_DISPATCH_DESIGN.md §11 Batch E).
- ``orchestrator.run_brief`` accepts the same param with matching default.
- ``orchestrator._acceptance_flow`` accepts both ``run_acceptance_followup``
  (default False) and ``retrieval_kwargs_builder`` (default None — Batch B
  threads it so Batch C's dispatch block can invoke ``_engineer_flow``).
- The run_brief wiring passes BOTH through to the ``_acceptance_flow``
  call so Batch C has them in scope at the hook point.

Batch B is plumbing only: no dispatch logic exists yet, so "flag off
yields zero spawns" is asserted at the source/signature level here and
behaviorally in Batch C's e2e test.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import orchestrator as orch  # noqa: E402
from app.routers.projects import RunBriefRequest  # noqa: E402


# ─── request model ─────────────────────────────────────────────────────────


def test_request_has_followup_default_false() -> None:
    req = RunBriefRequest(brief="x" * 25)
    assert req.run_acceptance_followup is False


def test_request_accepts_followup_true() -> None:
    req = RunBriefRequest(brief="x" * 25, run_acceptance_followup=True)
    assert req.run_acceptance_followup is True


# ─── orchestrator signatures ───────────────────────────────────────────────


def test_run_brief_signature_has_followup_default_false() -> None:
    sig = inspect.signature(orch.run_brief)
    p = sig.parameters["run_acceptance_followup"]
    assert p.default is False, (
        "ABL-0015: auto-dispatch defaults OFF until calibrated"
    )


def test_acceptance_flow_signature_has_followup_and_builder() -> None:
    sig = inspect.signature(orch._acceptance_flow)
    assert sig.parameters["run_acceptance_followup"].default is False
    # retrieval_kwargs_builder defaults None so the standalone
    # /run-acceptance endpoint (which omits it) keeps working.
    assert sig.parameters["retrieval_kwargs_builder"].default is None


# ─── wiring source check ───────────────────────────────────────────────────


def test_run_brief_threads_followup_and_builder_to_acceptance_flow() -> None:
    """Both the flag and the retrieval builder must reach the
    _acceptance_flow call so Batch C's dispatch block can use them."""
    src = inspect.getsource(orch.run_brief)
    call = src[src.index("_acceptance_flow("):]
    call = call[: call.index("):") + 2]
    assert "run_acceptance_followup=run_acceptance_followup" in call
    assert "retrieval_kwargs_builder=retrieval_kwargs_builder" in call
