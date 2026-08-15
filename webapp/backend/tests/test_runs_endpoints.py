"""Batch 1 (AUTONOMY_HARDENING_PLAN.md, C1/A34) — endpoint-level tests.

Covers:
- POST /run-brief {detached:true} → 202 {run_id, events_url}; run executes
  to completion in the background; B2 lock released by the pump, not the
  response.
- POST /run-brief (default detached:false) → legacy inline SSE view whose
  early disconnect ABORTS the run (pre-Batch-1 contract preserved).
- GET /api/runs/{id}/events replay incl. Last-Event-ID resume.
- GET /api/runs list + orphan surfacing (D5).
- POST /api/runs/{id}/abort 404 / 409 semantics.

Endpoints are invoked as plain coroutines (not via TestClient) so the
test owns the event loop the pump task runs on.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.routers import projects, runs  # noqa: E402
from app.routers.projects import RunBriefRequest  # noqa: E402
from app.services import run_registry  # noqa: E402
from app.services import run_state as run_state_svc  # noqa: E402


class _FakePreflight:
    ok = True

    def to_event(self) -> dict:
        return {"ok": True, "free_gb": 999.0}


def _patch_common(tmp_path, monkeypatch, *, events: list[dict] | None = None,
                  gen_delay: float = 0.0, finally_flag: list | None = None):
    """Stub every heavy dependency of the /run-brief endpoint."""
    monkeypatch.setattr(run_registry, "RUN_EVENTS_ROOT", tmp_path / "runs")
    run_registry._REGISTRY.clear()
    monkeypatch.setattr(projects, "_repo_dir", lambda repo: tmp_path)
    monkeypatch.setattr(projects.disk_preflight_svc, "check",
                        lambda *a, **k: _FakePreflight())
    monkeypatch.setattr(projects.run_state_svc, "find_active",
                        lambda *a, **k: None)

    evts = events if events is not None else [
        {"type": "_meta", "phase": "orchestrator.start"},
        {"type": "_meta", "phase": "orchestrator.sprint_complete"},
    ]

    async def fake_run_brief(**_kwargs):
        try:
            for e in evts:
                yield dict(e)
                if gen_delay:
                    await asyncio.sleep(gen_delay)
        finally:
            if finally_flag is not None:
                finally_flag.append(True)

    monkeypatch.setattr(projects.orchestrator_svc, "run_brief",
                        lambda **kwargs: fake_run_brief(**kwargs))


async def _wait_terminal(run_id: str, timeout=5.0):
    h = run_registry.get(run_id)
    assert h is not None
    deadline = asyncio.get_event_loop().time() + timeout
    while h.status == run_registry.RUNNING:
        assert asyncio.get_event_loop().time() < deadline, "run never terminated"
        await asyncio.sleep(0.01)
    if h.task is not None:
        try:
            await asyncio.wait_for(h.task, timeout=1.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
    return h


# ─── detached mode: 202 now, run completes in background ───────────────────


def test_detached_run_brief_returns_202_and_completes(tmp_path, monkeypatch) -> None:
    _patch_common(tmp_path, monkeypatch)

    async def main():
        resp = await projects.run_brief(
            "repo-detached-t1",
            RunBriefRequest(brief="x" * 25, detached=True),
        )
        assert resp.status_code == 202
        body = json.loads(bytes(resp.body))
        run_id = body["run_id"]
        assert body["events_url"] == f"/api/runs/{run_id}/events"
        assert body["abort_url"] == f"/api/runs/{run_id}/abort"

        h = await _wait_terminal(run_id)
        assert h.status == run_registry.COMPLETED

        # B2 lock is released by the pump's on_finish, not the response.
        assert projects._get_run_lock("repo-detached-t1").locked() is False
        assert "repo-detached-t1" not in projects._RUN_META

        # Event log: pre_flight advisory first, then the run's events,
        # terminal marker last.
        phases = [e async for _i, e in run_registry.subscribe(run_id)]
        got = [e.get("phase") for e in phases]
        assert got[0] == "orchestrator.pre_flight.disk"
        assert "orchestrator.sprint_complete" in got
        assert got[-1] == "orchestrator.run.terminal"

    asyncio.run(main())


# ─── inline mode: legacy frames + disconnect-aborts contract ────────────────


def test_inline_run_brief_streams_legacy_frames(tmp_path, monkeypatch) -> None:
    _patch_common(tmp_path, monkeypatch)

    async def main():
        resp = await projects.run_brief(
            "repo-inline-t2",
            RunBriefRequest(brief="x" * 25),  # detached defaults False
        )
        frames = []
        async for chunk in resp.body_iterator:
            frames.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
        text = "".join(frames)
        # Legacy shape: data:-only SSE frames, no id: lines, no
        # registry-internal terminal event.
        assert "id: " not in text
        assert "orchestrator.run.terminal" not in text
        assert "orchestrator.pre_flight.disk" in text
        assert "orchestrator.sprint_complete" in text
        h = run_registry.get(json.loads(
            text.split("data: ", 1)[1].split("\n", 1)[0])["run_id"])
        assert h is not None and h.status == run_registry.COMPLETED

    asyncio.run(main())


def test_inline_disconnect_aborts_run_legacy_contract(tmp_path, monkeypatch) -> None:
    finally_flag: list = []
    _patch_common(
        tmp_path, monkeypatch,
        events=[{"type": "_meta", "phase": f"step{i}"} for i in range(50)],
        gen_delay=0.05,
        finally_flag=finally_flag,
    )

    async def main():
        resp = await projects.run_brief(
            "repo-inline-t3",
            RunBriefRequest(brief="x" * 25, detached=False),
        )
        it = resp.body_iterator
        first = await asyncio.wait_for(it.__anext__(), timeout=2.0)
        assert b"pre_flight" in (first if isinstance(first, bytes) else first.encode())
        # Simulate client disconnect: Starlette calls aclose() on the
        # response generator. Legacy contract: this ABORTS the run.
        await it.aclose()

        run_id = list(run_registry._REGISTRY)[0]
        h = await _wait_terminal(run_id)
        assert h.status == run_registry.ABORTED, (
            "detached=False must preserve the pre-Batch-1 disconnect-aborts contract"
        )
        assert finally_flag == [True], "orchestrator finallys must fire on abort"
        assert projects._get_run_lock("repo-inline-t3").locked() is False

    asyncio.run(main())


# ─── /api/runs endpoints ────────────────────────────────────────────────────


def _make_request(headers: dict[str, str] | None = None) -> Request:
    hdrs = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "method": "GET", "path": "/",
                    "headers": hdrs, "query_string": b""})


def test_events_endpoint_replays_and_honors_last_event_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(run_registry, "RUN_EVENTS_ROOT", tmp_path / "runs")
    run_registry._REGISTRY.clear()
    # Terminal run known only from its on-disk log (post-restart replay).
    p = run_registry.events_path_for("run-replay")
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = [{"type": "_meta", "phase": f"step{i}"} for i in range(4)]
    p.write_text("".join(json.dumps(e) + "\n" for e in lines))

    async def main():
        resp = await runs.run_events("run-replay", _make_request())
        chunks = [c async for c in resp.body_iterator]
        text = b"".join(c if isinstance(c, bytes) else c.encode() for c in chunks).decode()
        assert text.count("data: ") == 4
        assert "id: 0\n" in text and "id: 3\n" in text

        # Last-Event-ID resume: client saw idx 1, gets 2..3 only.
        resp2 = await runs.run_events(
            "run-replay", _make_request({"Last-Event-ID": "1"}))
        chunks2 = [c async for c in resp2.body_iterator]
        text2 = b"".join(c if isinstance(c, bytes) else c.encode() for c in chunks2).decode()
        assert text2.count("data: ") == 2
        assert "step2" in text2 and "step3" in text2 and "step0" not in text2

    asyncio.run(main())


def test_events_endpoint_404_on_unknown_run(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(run_registry, "RUN_EVENTS_ROOT", tmp_path / "runs")
    run_registry._REGISTRY.clear()

    async def main():
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await runs.run_events("run-unknown", _make_request())
        assert exc.value.status_code == 404

    asyncio.run(main())


def test_abort_endpoint_404_and_409(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(run_registry, "RUN_EVENTS_ROOT", tmp_path / "runs")
    run_registry._REGISTRY.clear()

    async def main():
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await runs.abort_run("run-unknown")
        assert exc.value.status_code == 404

        # Terminal run → 409, not a second cancel.
        h = run_registry.RunHandle(
            run_id="run-done", repo="r",
            events_path=run_registry.events_path_for("run-done"),
            started_at="2026-08-15T00:00:00+00:00",
            status=run_registry.COMPLETED,
        )
        run_registry._REGISTRY["run-done"] = h
        with pytest.raises(HTTPException) as exc2:
            await runs.abort_run("run-done")
        assert exc2.value.status_code == 409

    asyncio.run(main())


def test_list_runs_surfaces_orphans_without_resuming(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(run_registry, "RUN_EVENTS_ROOT", tmp_path / "runs")
    run_registry._REGISTRY.clear()
    orphan_state = {
        "run_id": "run-orphan", "repo": "somerepo", "status": "active",
        "current_bl": "BL-0003", "updated_at": "2026-08-15T00:00:00+00:00",
    }
    monkeypatch.setattr(run_state_svc, "list_active", lambda: [orphan_state])
    # runs.py imported the module, not the function — patch there too.
    monkeypatch.setattr(runs.run_state_svc, "list_active", lambda: [orphan_state])

    async def main():
        out = await runs.list_runs(status="orphaned")
        assert out["runs"] == [{**orphan_state, "orphaned": True}]
        all_out = await runs.list_runs()
        assert any(r.get("run_id") == "run-orphan" for r in all_out["runs"])

    asyncio.run(main())
