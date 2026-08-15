"""Batch 1 (AUTONOMY_HARDENING_PLAN.md, C1/A34) — run lifecycle endpoints.

The run registry (`app.services.run_registry`) executes sprints as
background tasks and journals every event to
``logs/runs/<run_id>/events.jsonl``. These endpoints are pure consumers:

- ``GET  /api/runs``                  — registry snapshots + orphaned disk
                                        state files (D5: surfaced, never
                                        auto-resumed)
- ``GET  /api/runs/{run_id}``         — status snapshot (registry first,
                                        A7 disk state fallback)
- ``GET  /api/runs/{run_id}/events``  — resumable SSE view: replay from
                                        ``from_index`` (or Last-Event-ID),
                                        then live tail. Disconnect stops
                                        the view, never the run.
- ``POST /api/runs/{run_id}/abort``   — the ONLY cancellation path.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.services import run_registry as run_registry_svc
from app.services import run_state as run_state_svc

router = APIRouter(prefix="/api/runs", tags=["runs"])


def _sse(event: dict, event_id: int | None = None) -> bytes:
    # id: line enables EventSource/Last-Event-ID resume; data: shape is
    # identical to the projects-router SSE frames.
    prefix = f"id: {event_id}\n" if event_id is not None else ""
    return f"{prefix}data: {json.dumps(event, default=str)}\n\n".encode()


@router.get("")
async def list_runs(status: str | None = None):
    """List in-process runs plus orphaned on-disk state files.

    An *orphan* is an A7 active-state file whose run_id has no RUNNING
    entry in this process's registry — i.e. a prior process crashed
    mid-run. Per operator decision D5 these are surfaced only; resume
    stays an explicit `/run-brief {skip_po:true}` re-POST.
    """
    in_process = run_registry_svc.list_all()
    known_ids = {r["run_id"] for r in in_process}
    orphaned = [
        {**st, "orphaned": True}
        for st in run_state_svc.list_active()
        if st.get("run_id") not in known_ids
    ]
    if status == "orphaned":
        return {"runs": orphaned}
    return {"runs": in_process + orphaned}


@router.get("/{run_id}")
async def run_status(run_id: str):
    handle = run_registry_svc.get(run_id)
    if handle is not None:
        return handle.snapshot()
    # Fallback: disk state (active = orphaned candidate, done/ = historical).
    for st in run_state_svc.list_active():
        if st.get("run_id") == run_id:
            return {**st, "orphaned": True}
    done = run_state_svc.read_done(run_id)
    if done is not None:
        return done
    raise HTTPException(status_code=404, detail=f"unknown run_id {run_id!r}")


@router.get("/{run_id}/events")
async def run_events(run_id: str, request: Request, from_index: int = 0):
    """Resumable SSE view of a run's event log.

    Replays ``events.jsonl`` from ``from_index`` (query param; the SSE
    ``Last-Event-ID`` header wins when present — standard EventSource
    reconnect semantics), then tails live while the run is RUNNING.
    Ends cleanly once the run is terminal and the log is drained.
    """
    start = from_index
    last_event_id = request.headers.get("last-event-id")
    if last_event_id is not None:
        try:
            start = int(last_event_id) + 1
        except ValueError:
            pass

    if (run_registry_svc.get(run_id) is None
            and not run_registry_svc.events_path_for(run_id).exists()):
        raise HTTPException(status_code=404, detail=f"no event log for run_id {run_id!r}")

    async def gen():
        async for idx, event in run_registry_svc.subscribe(run_id, from_index=start):
            yield _sse(event, event_id=idx)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{run_id}/abort")
async def abort_run(run_id: str):
    """Cancel a running run. Cancellation propagates into the orchestrator
    generator, so every cleanup finally (worktrees, A7 mark_terminated,
    B15 trace archive) fires — same semantics the legacy inline path had
    on client disconnect, but now an explicit, deliberate act."""
    handle = run_registry_svc.get(run_id)
    if handle is None:
        raise HTTPException(status_code=404, detail=f"unknown run_id {run_id!r}")
    if handle.status != run_registry_svc.RUNNING:
        raise HTTPException(
            status_code=409,
            detail={"error": "run-not-running", "status": handle.status},
        )
    delivered = run_registry_svc.abort(run_id)
    return {"run_id": run_id, "abort_requested": delivered}
