"""Batch 1 (AUTONOMY_HARDENING_PLAN.md, C1/A34) — run registry tests.

The batch gate:
- consumer disconnect must NOT stop the run (the A34 inversion)
- abort() must cancel AND fire the orchestrator generator's finallys
- the event log must be complete + replayable on every exit path
- on_finish fires exactly once per run
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import run_registry  # noqa: E402


def _fresh_root(tmp_path, monkeypatch):
    monkeypatch.setattr(run_registry, "RUN_EVENTS_ROOT", tmp_path / "runs")
    run_registry._REGISTRY.clear()


def _read_log(run_id: str) -> list[dict]:
    p = run_registry.events_path_for(run_id)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


async def _wait_terminal(handle, timeout=5.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while handle.status == run_registry.RUNNING:
        if asyncio.get_event_loop().time() > deadline:
            raise AssertionError(f"run did not terminate; status={handle.status}")
        await asyncio.sleep(0.01)
    if handle.task is not None:
        try:
            await asyncio.wait_for(handle.task, timeout=1.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass


# ─── completion + replay ───────────────────────────────────────────────────


def test_run_completes_and_log_replays(tmp_path, monkeypatch) -> None:
    _fresh_root(tmp_path, monkeypatch)

    async def agen():
        for i in range(3):
            yield {"type": "_meta", "phase": f"step{i}"}
            await asyncio.sleep(0)

    async def main():
        finished: list[str] = []
        h = run_registry.start_run(
            "run-t1", "repo", agen(),
            pre_events=[{"type": "_meta", "phase": "pre"}],
            on_finish=finished.append,
        )
        await _wait_terminal(h)
        assert h.status == run_registry.COMPLETED
        assert finished == [run_registry.COMPLETED]

        log = _read_log("run-t1")
        phases = [e.get("phase") for e in log]
        # pre-event first, generator events in order, terminal event last.
        assert phases == ["pre", "step0", "step1", "step2",
                          "orchestrator.run.terminal"]
        assert log[-1]["status"] == run_registry.COMPLETED

        # Full replay after completion (pure file read, handle terminal).
        got = [e async for _i, e in run_registry.subscribe("run-t1")]
        assert [e.get("phase") for e in got] == phases

        # Offset replay honors from_index.
        got2 = [i async for i, _e in run_registry.subscribe("run-t1", from_index=2)]
        assert got2 == [2, 3, 4]

    asyncio.run(main())


# ─── THE A34 inversion: disconnecting a viewer never stops the run ─────────


def test_consumer_disconnect_does_not_stop_run(tmp_path, monkeypatch) -> None:
    _fresh_root(tmp_path, monkeypatch)
    finally_ran: list[bool] = []

    async def agen():
        try:
            for i in range(5):
                yield {"type": "_meta", "phase": f"step{i}"}
                await asyncio.sleep(0.01)
        finally:
            finally_ran.append(True)

    async def main():
        h = run_registry.start_run("run-t2", "repo", agen())
        # Attach a viewer, consume ONE event, then drop the subscription —
        # exactly what a closed laptop / curl timeout does to the SSE view.
        sub = run_registry.subscribe("run-t2")
        first = await asyncio.wait_for(sub.__anext__(), timeout=2.0)
        assert first[1]["phase"] == "step0"
        await sub.aclose()

        await _wait_terminal(h)
        assert h.status == run_registry.COMPLETED, (
            "viewer disconnect must not cancel the run (C1/A34)"
        )
        phases = [e.get("phase") for e in _read_log("run-t2")]
        assert phases[:5] == [f"step{i}" for i in range(5)]
        assert phases[-1] == "orchestrator.run.terminal"
        assert finally_ran == [True]  # generator ran to natural completion

    asyncio.run(main())


# ─── abort: the ONLY cancellation path; generator finallys must fire ───────


def test_abort_cancels_and_generator_finally_fires(tmp_path, monkeypatch) -> None:
    _fresh_root(tmp_path, monkeypatch)
    finally_ran: list[bool] = []
    finished: list[str] = []

    async def agen():
        try:
            yield {"type": "_meta", "phase": "step0"}
            await asyncio.sleep(30)  # long "sprint" — abort lands here
            yield {"type": "_meta", "phase": "never"}
        finally:
            # Stands in for the orchestrator's cleanup finallys (worktree
            # reap, A7 mark_terminated, B15 archive).
            finally_ran.append(True)

    async def main():
        h = run_registry.start_run("run-t3", "repo", agen(), on_finish=finished.append)
        # Let the first event land, then abort.
        while h.event_count < 1:
            await asyncio.sleep(0.01)
        assert run_registry.abort("run-t3") is True
        await _wait_terminal(h)

        assert h.status == run_registry.ABORTED
        assert finally_ran == [True], "generator finallys must fire on abort"
        assert finished == [run_registry.ABORTED]
        log = _read_log("run-t3")
        assert log[-1]["phase"] == "orchestrator.run.terminal"
        assert log[-1]["status"] == run_registry.ABORTED
        # Idempotence: abort on a terminal run is a no-op False.
        assert run_registry.abort("run-t3") is False

    asyncio.run(main())


def test_abort_unknown_run_returns_false(tmp_path, monkeypatch) -> None:
    _fresh_root(tmp_path, monkeypatch)
    assert run_registry.abort("run-nope") is False


# ─── exception mapping preserves legacy event shapes ───────────────────────


def test_generator_exception_maps_to_event(tmp_path, monkeypatch) -> None:
    _fresh_root(tmp_path, monkeypatch)

    class FakeRetrievalUnavailable(RuntimeError):
        pass

    def exception_event(exc: BaseException) -> dict:
        if isinstance(exc, FakeRetrievalUnavailable):
            return {"type": "_meta", "phase": "orchestrator.aborted",
                    "reason": f"retrieval unavailable: {exc}"}
        return {"type": "_error", "error": f"{type(exc).__name__}: {exc}"}

    async def agen():
        yield {"type": "_meta", "phase": "step0"}
        raise FakeRetrievalUnavailable("milvus down")

    async def main():
        h = run_registry.start_run("run-t4", "repo", agen(),
                                   exception_event=exception_event)
        await _wait_terminal(h)
        assert h.status == run_registry.ERROR
        log = _read_log("run-t4")
        phases = [e.get("phase") for e in log]
        assert "orchestrator.aborted" in phases, (
            "RetrievalUnavailable must map to the legacy aborted event"
        )
        assert log[-1]["phase"] == "orchestrator.run.terminal"
        assert log[-1]["status"] == run_registry.ERROR

    asyncio.run(main())


# ─── persist side channel: errors never block the run ──────────────────────


def test_persist_callback_errors_are_swallowed(tmp_path, monkeypatch) -> None:
    _fresh_root(tmp_path, monkeypatch)
    seen: list[str] = []

    def bad_persist(evt: dict) -> None:
        seen.append(evt.get("phase"))
        raise OSError("disk io error in side channel")

    async def agen():
        yield {"type": "_meta", "phase": "step0"}
        yield {"type": "_meta", "phase": "step1"}

    async def main():
        h = run_registry.start_run("run-t5", "repo", agen(), persist=bad_persist)
        await _wait_terminal(h)
        assert h.status == run_registry.COMPLETED
        assert seen[:2] == ["step0", "step1"]
        # Canonical log intact despite the failing side channel.
        assert [e.get("phase") for e in _read_log("run-t5")][:2] == ["step0", "step1"]

    asyncio.run(main())


# ─── concurrent viewers ─────────────────────────────────────────────────────


def test_two_concurrent_subscribers_both_get_all_events(tmp_path, monkeypatch) -> None:
    _fresh_root(tmp_path, monkeypatch)

    async def agen():
        for i in range(4):
            yield {"type": "_meta", "phase": f"step{i}"}
            await asyncio.sleep(0.01)

    async def collect(run_id):
        return [e.get("phase") async for _i, e in run_registry.subscribe(run_id)]

    async def main():
        run_registry.start_run("run-t6", "repo", agen())
        a, b = await asyncio.wait_for(
            asyncio.gather(collect("run-t6"), collect("run-t6")), timeout=5.0
        )
        expect = [f"step{i}" for i in range(4)] + ["orchestrator.run.terminal"]
        assert a == expect
        assert b == expect

    asyncio.run(main())


# ─── duplicate start guard ──────────────────────────────────────────────────


def test_start_run_refuses_duplicate_running_id(tmp_path, monkeypatch) -> None:
    _fresh_root(tmp_path, monkeypatch)

    async def agen():
        yield {"type": "_meta", "phase": "step0"}
        await asyncio.sleep(30)

    async def main():
        h = run_registry.start_run("run-t7", "repo", agen())
        try:
            import pytest
            with pytest.raises(RuntimeError):
                run_registry.start_run("run-t7", "repo", agen())
        finally:
            run_registry.abort("run-t7")
            await _wait_terminal(h)

    asyncio.run(main())
