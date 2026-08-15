"""Batch 1 (AUTONOMY_HARDENING_PLAN.md) — detached run execution.

Closes C1/A34: the sprint no longer lives inside an HTTP response
generator. `start_run` wraps the orchestrator's async generator in an
`asyncio.Task` (the *pump*); every event is appended to a durable
per-run event log at ``logs/runs/<run_id>/events.jsonl``. SSE endpoints
become *consumers*: `subscribe()` replays the file from any offset and
tails live via an `asyncio.Condition`. Client disconnect stops the
view, never the run; `abort()` is the only way to cancel.

Invariants honored:
- I-1: exactly one execution path — the inline (legacy) response mode
  also runs through this registry; there is no second consumer of the
  orchestrator generator.
- I-3: the pump writes a terminal ``orchestrator.run.terminal`` event
  on every exit path (completed / aborted / error), so the event log is
  self-closing even though PEP 525 forbids the orchestrator generator
  from yielding out of its own finally.
- I-4: the event log is keyed by run_id (`logs/runs/<run_id>/`),
  joining the A7 state file and B15 trace archive on the same key.

Cancellation semantics: `abort()` cancels the pump task; the
CancelledError propagates into the orchestrator generator at its
suspension point, so all of its `finally` blocks (worktree reaping, A7
`mark_terminated`, B15 trace archive) fire exactly as they do today on
SSE disconnect.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, Callable

BACKEND_DIR = Path(__file__).resolve().parents[2]  # webapp/backend/
# Tests monkeypatch this module attribute; not read from env at call time.
RUN_EVENTS_ROOT = BACKEND_DIR / "logs" / "runs"

# Statuses: running → completed | aborted | error
RUNNING = "running"
COMPLETED = "completed"
ABORTED = "aborted"
ERROR = "error"
TERMINAL = (COMPLETED, ABORTED, ERROR)


@dataclass
class RunHandle:
    run_id: str
    repo: str
    events_path: Path
    started_at: str
    status: str = RUNNING
    event_count: int = 0
    error: str | None = None
    task: asyncio.Task | None = None
    # Set once the pump's finally has run (used by the never-started
    # done-callback guard to avoid double-finalizing).
    finalized: bool = False

    def snapshot(self) -> dict:
        return {
            "run_id": self.run_id,
            "repo": self.repo,
            "status": self.status,
            "started_at": self.started_at,
            "event_count": self.event_count,
            "error": self.error,
            "events_path": str(self.events_path),
        }


_REGISTRY: dict[str, RunHandle] = {}


def get(run_id: str) -> RunHandle | None:
    return _REGISTRY.get(run_id)


def list_all() -> list[dict]:
    return [h.snapshot() for h in _REGISTRY.values()]


def events_path_for(run_id: str) -> Path:
    """Canonical event-log path for a run_id (exists only if a run with
    that id ever pumped in this or a prior process)."""
    return RUN_EVENTS_ROOT / run_id / "events.jsonl"


def start_run(
    run_id: str,
    repo: str,
    agen: AsyncIterator[dict],
    *,
    pre_events: list[dict] | None = None,
    persist: Callable[[dict], None] | None = None,
    exception_event: Callable[[BaseException], dict] | None = None,
    on_finish: Callable[[str], None] | None = None,
) -> RunHandle:
    """Begin executing `agen` in a background task. Returns immediately.

    - `pre_events`: synthetic events written before the generator's own
      (e.g. the A48 pre_flight.disk advisory the router used to yield
      first).
    - `persist(evt)`: extra per-event side channel (the A18 per-feature
      events.jsonl appender + _RUN_META current_bl tracking). Errors are
      swallowed — the canonical log is the registry's own file.
    - `exception_event(exc)`: maps a generator exception to the event
      the legacy inline path would have emitted (RetrievalUnavailable →
      orchestrator.aborted; anything else → _error).
    - `on_finish(status)`: fires exactly once on every exit path, after
      the terminal event is written (release the B2 lock, close file
      handles, pop _RUN_META).
    """
    if run_id in _REGISTRY and _REGISTRY[run_id].status == RUNNING:
        raise RuntimeError(f"run {run_id} already running")
    events_path = events_path_for(run_id)
    events_path.parent.mkdir(parents=True, exist_ok=True)
    # Create the log synchronously so a subscriber attached immediately
    # after start_run (before the pump's first scheduler step) sees the
    # file and waits, rather than concluding the run has no log.
    events_path.touch(exist_ok=True)
    handle = RunHandle(
        run_id=run_id,
        repo=repo,
        events_path=events_path,
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    _REGISTRY[run_id] = handle
    handle.task = asyncio.create_task(
        _pump(handle, agen,
              pre_events=list(pre_events or []),
              persist=persist,
              exception_event=exception_event,
              on_finish=on_finish),
        name=f"run-pump-{run_id}",
    )

    def _finalize_if_never_started(task: asyncio.Task) -> None:
        # A task cancelled before its first scheduler step never executes
        # the pump body at all — no finally, no terminal status. Detect
        # that here so the handle can't stay RUNNING forever and the B2
        # lock still gets released.
        if handle.finalized or handle.status != RUNNING:
            return
        handle.status = ABORTED if task.cancelled() else ERROR
        if not task.cancelled() and task.exception() is not None:
            handle.error = str(task.exception())
        handle.finalized = True
        if on_finish is not None:
            try:
                on_finish(handle.status)
            except Exception:  # noqa: BLE001
                pass

    handle.task.add_done_callback(_finalize_if_never_started)
    return handle


def abort(run_id: str) -> bool:
    """Request cancellation of a running run. Returns True if a cancel
    was delivered; False if the run is unknown or already terminal."""
    handle = _REGISTRY.get(run_id)
    if handle is None or handle.status != RUNNING or handle.task is None:
        return False
    handle.task.cancel()
    return True


async def _pump(
    handle: RunHandle,
    agen: AsyncIterator[dict],
    *,
    pre_events: list[dict],
    persist: Callable[[dict], None] | None,
    exception_event: Callable[[BaseException], dict] | None,
    on_finish: Callable[[str], None] | None,
) -> None:
    fh = handle.events_path.open("a", encoding="utf-8")

    async def _emit(evt: dict) -> None:
        try:
            fh.write(json.dumps(evt, default=str) + "\n")
            fh.flush()
        except (OSError, ValueError, TypeError):
            pass
        if persist is not None:
            try:
                persist(evt)
            except Exception:  # noqa: BLE001 — side channel never blocks
                pass
        handle.event_count += 1

    try:
        for evt in pre_events:
            await _emit(evt)
        try:
            async for evt in agen:
                await _emit(evt)
            handle.status = COMPLETED
        except asyncio.CancelledError:
            # abort(): cancellation already propagated through the
            # orchestrator generator (its finallys ran). Swallowing the
            # CancelledError here is deliberate — the pump's job now is
            # to close the log honestly rather than die mid-write.
            handle.status = ABORTED
        except Exception as exc:  # noqa: BLE001 — map to legacy event shape
            handle.status = ERROR
            handle.error = f"{type(exc).__name__}: {exc}"
            if exception_event is not None:
                try:
                    await _emit(exception_event(exc))
                except Exception:  # noqa: BLE001
                    pass
            else:
                await _emit({"type": "_error", "error": handle.error})
        finally:
            # Belt-and-suspenders: ensure the generator is closed even if
            # _emit itself raised. aclose() on an exhausted/closed
            # generator is a no-op.
            aclose = getattr(agen, "aclose", None)
            if aclose is not None:
                try:
                    await asyncio.shield(aclose())
                except (Exception, asyncio.CancelledError):  # noqa: BLE001
                    pass
        # I-3: self-closing log — one terminal event on every path.
        await _emit({
            "type": "_meta",
            "phase": "orchestrator.run.terminal",
            "run_id": handle.run_id,
            "status": handle.status,
            "error": handle.error,
        })
    finally:
        if handle.status == RUNNING:  # crashed before status assignment
            handle.status = ERROR
        handle.finalized = True
        try:
            fh.close()
        except OSError:
            pass
        if on_finish is not None:
            try:
                on_finish(handle.status)
            except Exception:  # noqa: BLE001
                pass


async def subscribe(run_id: str, from_index: int = 0) -> AsyncIterator[tuple[int, dict]]:
    """Yield `(index, event)` pairs: replay from the durable log starting
    at `from_index`, then tail live until the run reaches a terminal
    status and the log is fully drained.

    Works for terminal runs too (pure replay). Multiple concurrent
    subscribers are independent — each holds its own file handle, so a
    slow consumer never applies backpressure to the run.
    """
    handle = _REGISTRY.get(run_id)
    path = handle.events_path if handle is not None else events_path_for(run_id)
    if not path.exists():
        return
    idx = 0
    with path.open("r", encoding="utf-8") as fh:
        while True:
            pos = fh.tell()
            line = fh.readline()
            if line.endswith("\n"):
                if idx >= from_index:
                    try:
                        evt = json.loads(line)
                    except ValueError:
                        evt = {"type": "_raw", "text": line.rstrip("\n")}
                    yield idx, evt
                idx += 1
                continue
            # Empty read or partial line (pump mid-write): rewind, then
            # either finish (terminal + drained) or poll again shortly.
            # Deliberately lock-free: a viewer that dies mid-wait (SSE
            # disconnect → GeneratorExit) can never wedge the pump, and
            # a slow viewer never applies backpressure to the run.
            fh.seek(pos)
            if handle is None or handle.status in TERMINAL:
                if handle is None or idx >= handle.event_count:
                    return
                continue  # terminal but not yet drained — keep reading
            await asyncio.sleep(0.05)
