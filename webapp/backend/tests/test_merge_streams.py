"""Unit tests for the wave-concurrency fan-in primitive `_merge_streams`.

PROPOSAL_WAVE_CONCURRENCY.md step 2. Verifies the async fan-in: merges N event
streams into one, caps concurrent drains at `concurrency`, isolates a failing
stream (no-abort), preserves per-stream order, and handles the empty case.
Uses `asyncio.run` directly (backend test env has anyio, not pytest-asyncio).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.orchestrator import _merge_streams  # noqa: E402


def _collect(factories, concurrency):
    async def run():
        out = []
        async for idx, ev in _merge_streams(factories, concurrency):
            out.append((idx, ev))
        return out
    return asyncio.run(run())


def test_merges_all_events_and_tags():
    async def gen(idx, n):
        for i in range(n):
            yield {"idx": idx, "i": i}
    facts = [lambda: gen(0, 2), lambda: gen(1, 3), lambda: gen(2, 1)]
    out = _collect(facts, concurrency=2)
    assert len(out) == 6
    by: dict = {}
    for idx, ev in out:
        by.setdefault(idx, []).append(ev["i"])
    assert by[0] == [0, 1] and by[1] == [0, 1, 2] and by[2] == [0]


def test_concurrency_cap_respected():
    state = {"active": 0, "max": 0}

    async def gen(idx):
        state["active"] += 1
        state["max"] = max(state["max"], state["active"])
        try:
            for i in range(3):
                await asyncio.sleep(0.005)
                yield {"idx": idx, "i": i}
        finally:
            state["active"] -= 1

    facts = [lambda i=i: gen(i) for i in range(5)]
    out = _collect(facts, concurrency=2)
    assert state["max"] <= 2, state["max"]
    assert len(out) == 15


def test_isolates_failing_stream_no_abort():
    async def good(idx):
        for i in range(3):
            yield {"idx": idx, "i": i}

    async def bad(idx):
        yield {"idx": idx, "i": 0}
        raise ValueError("boom")

    facts = [lambda: good(0), lambda: bad(1), lambda: good(2)]
    out = _collect(facts, concurrency=3)
    errs = [ev for _, ev in out if isinstance(ev, dict) and "_stream_error" in ev]
    assert len(errs) == 1 and "boom" in errs[0]["_stream_error"]
    # siblings complete fully despite the failure
    assert len([ev for idx, ev in out if idx == 0]) == 3
    assert len([ev for idx, ev in out if idx == 2]) == 3
    # the failing stream yielded its pre-failure event + the error marker
    assert len([ev for idx, ev in out if idx == 1 and "_stream_error" not in ev]) == 1


def test_per_stream_order_preserved():
    async def gen(idx):
        for i in range(5):
            await asyncio.sleep(0.001)
            yield {"idx": idx, "i": i}
    facts = [lambda i=i: gen(i) for i in range(3)]
    out = _collect(facts, concurrency=3)
    for k in range(3):
        seq = [ev["i"] for idx, ev in out if idx == k]
        assert seq == [0, 1, 2, 3, 4], (k, seq)


def test_empty_factories():
    assert _collect([], concurrency=4) == []


def test_concurrency_one_is_serial_equivalent():
    # concurrency=1 must still surface every event (the byte-identical scaffolding case)
    async def gen(idx, n):
        for i in range(n):
            yield {"idx": idx, "i": i}
    facts = [lambda: gen(0, 3), lambda: gen(1, 2)]
    out = _collect(facts, concurrency=1)
    assert len(out) == 5
