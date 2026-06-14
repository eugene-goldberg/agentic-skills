"""Unit tests for the concurrent-wave orchestration `_run_wave_concurrent`.

PROPOSAL_WAVE_CONCURRENCY.md Strategy A, step 3b. Drives the fan-in over a wave's
BLs with mock factories + a mock assembler (no real agents/git) and asserts:
deterministic BL-id assembly order (independent of finish order), live events pass
through, and no-abort routing for stream errors / conflicts / not-ready BLs.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.orchestrator import _run_wave_concurrent  # noqa: E402


def _mk(bl_id, outcome="ready", events=(), delay=0.0):
    async def gen():
        for e in events:
            if delay:
                await asyncio.sleep(delay)
            yield e
        wb = f"agentwork/{bl_id}" if outcome == "ready" else None
        yield {"_wave_bl_done": {"bl_id": bl_id, "work_branch": wb, "outcome": outcome}}
    return gen


async def _good_assembler(bid, wb):
    return {"ok": True, "kind": "merged", "merged_sha": "deadbeef"}


def _collect(bl_specs, assembler, concurrency):
    async def run():
        out = []
        async for tag, bid, payload in _run_wave_concurrent(bl_specs, assembler, concurrency):
            out.append((tag, bid, payload))
        return out
    return asyncio.run(run())


def _wave_done(out):
    return [p for tag, _, p in out if tag == "wave_done"][0]


def test_two_ready_assemble_in_order():
    specs = [("BL-0002", _mk("BL-0002")), ("BL-0003", _mk("BL-0003"))]
    out = _collect(specs, _good_assembler, concurrency=2)
    asm = [bid for tag, bid, _ in out if tag == "assembly"]
    assert asm == ["BL-0002", "BL-0003"]
    assert all(a["assembled"] for a in _wave_done(out)["assembled"])


def test_assembly_order_independent_of_finish_order():
    # BL-0003 finishes first (no delay); BL-0002 is delayed — assembly must still
    # follow bl_specs (BL-id) order, not finish order (interleaving-independence).
    specs = [
        ("BL-0002", _mk("BL-0002", events=[{"phase": "x"}], delay=0.02)),
        ("BL-0003", _mk("BL-0003", events=[{"phase": "x"}], delay=0.0)),
    ]
    out = _collect(specs, _good_assembler, concurrency=2)
    asm = [bid for tag, bid, _ in out if tag == "assembly"]
    assert asm == ["BL-0002", "BL-0003"]


def test_live_events_pass_through_tagged():
    specs = [("BL-0002", _mk("BL-0002", events=[{"phase": "engineer.start"}]))]
    out = _collect(specs, _good_assembler, concurrency=1)
    evs = [(bid, p) for tag, bid, p in out if tag == "event"]
    assert any(bid == "BL-0002" and p.get("phase") == "engineer.start" for bid, p in evs)


def test_stream_error_bl_not_assembled_siblings_ok():
    def _bad():
        async def gen():
            yield {"phase": "engineer.start"}
            raise ValueError("boom")
        return gen
    specs = [("BL-0002", _mk("BL-0002")), ("BL-0003", _bad())]
    out = _collect(specs, _good_assembler, concurrency=2)
    by = {a["bl_id"]: a for a in _wave_done(out)["assembled"]}
    assert by["BL-0002"]["assembled"] is True
    assert by["BL-0003"]["assembled"] is False
    assert by["BL-0003"]["reason"] == "stream_error"


def test_conflict_bl_flagged_unassembled():
    async def _conflict_assembler(bid, wb):
        if bid == "BL-0003":
            return {"ok": False, "kind": "conflict", "conflict_files": ["shared.txt"]}
        return {"ok": True, "kind": "merged"}
    specs = [("BL-0002", _mk("BL-0002")), ("BL-0003", _mk("BL-0003"))]
    out = _collect(specs, _conflict_assembler, concurrency=2)
    by = {a["bl_id"]: a for a in _wave_done(out)["assembled"]}
    assert by["BL-0002"]["assembled"] is True
    assert by["BL-0003"]["assembled"] is False and by["BL-0003"]["kind"] == "conflict"


def test_not_ready_bl_skipped_with_reason():
    specs = [("BL-0002", _mk("BL-0002", outcome="escalated"))]
    out = _collect(specs, _good_assembler, concurrency=1)
    a = _wave_done(out)["assembled"][0]
    assert a["assembled"] is False and a["reason"] == "escalated"
