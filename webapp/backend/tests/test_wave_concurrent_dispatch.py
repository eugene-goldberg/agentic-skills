"""Unit tests for the concurrent-wave DISPATCH wiring (wave-concurrency Strategy A).

These tests exercise the deterministic fan-in + barrier-assembly contract that the
``run_brief`` concurrent-wave loop relies on, at the ``_run_wave_concurrent`` seam:

  * with ``wave_concurrency>1`` and 2 ready BLs, BOTH are assembled in BL-id order
    and the (mock) agent_branch advances once per assembled BL;
  * assembly order is independent of which BL finishes first (interleaving-
    independent determinism — no control decision reads the cosmetic interleaving);
  * a BL whose assembly CONFLICTS is surfaced (not silently dropped) and its
    siblings still assemble (no-abort);
  * a not-ready / errored BL is left unassembled with a reason.

They mock at the ``merge_branch_into_target`` boundary via a stateful assembler that
models a single advancing trunk SHA, so "agent_branch advances" is asserted directly.
Fast + deterministic: no real agents, git, or I/O.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.orchestrator import _run_wave_concurrent  # noqa: E402


def _ready_bl(bl_id, events=(), delay=0.0):
    """A factory mimicking ``_one_bl(it, concurrent=True)`` for a green BL: emits
    optional live events then exactly one ready ``_wave_bl_done`` carrying a
    work_branch (the engineer's surviving branch)."""
    async def gen():
        for e in events:
            if delay:
                await asyncio.sleep(delay)
            yield e
        yield {"_wave_bl_done": {"bl_id": bl_id, "work_branch": f"agent/work-{bl_id}",
                                 "outcome": "ready"}}
    return gen


def _unready_bl(bl_id, outcome="engineer_escalated"):
    """A factory for a BL that did NOT reach assembly eligibility (no work_branch)."""
    async def gen():
        yield {"_wave_bl_done": {"bl_id": bl_id, "outcome": outcome}}
    return gen


class _MockTrunk:
    """Models the agent_branch as a single advancing SHA. Each clean assembly of a
    distinct work_branch advances the trunk by one; a conflicting branch does NOT."""

    def __init__(self):
        self.sha = 0
        self.assembled_branches: list[str] = []
        self.conflict_branches: set[str] = set()

    async def assemble(self, bl_id, work_branch):
        if work_branch in self.conflict_branches:
            return {"ok": False, "kind": "conflict",
                    "conflict_files": ["shared/models.py"],
                    "error": f"merge of {work_branch} conflicts"}
        self.sha += 1
        self.assembled_branches.append(work_branch)
        return {"ok": True, "kind": "merged", "merged_sha": f"sha{self.sha:04d}"}


def _drive(bl_specs, assembler, concurrency):
    async def run():
        out = []
        async for tag, bid, payload in _run_wave_concurrent(bl_specs, assembler, concurrency):
            out.append((tag, bid, payload))
        return out
    return asyncio.run(run())


def _assembly_order(out):
    return [bid for tag, bid, _ in out if tag == "assembly"]


def _wave_done(out):
    return [p for tag, _, p in out if tag == "wave_done"][0]


def test_two_ready_bls_both_assembled_in_id_order_trunk_advances():
    """wave_concurrency>1, 2 ready BLs → both assembled in BL-id order; the mock
    agent_branch advances exactly once per BL."""
    trunk = _MockTrunk()
    specs = [
        ("BL-0002", _ready_bl("BL-0002")),
        ("BL-0003", _ready_bl("BL-0003")),
    ]
    out = _drive(specs, trunk.assemble, concurrency=2)
    assert _assembly_order(out) == ["BL-0002", "BL-0003"]
    # trunk advanced twice (once per assembled BL), in BL-id order
    assert trunk.sha == 2
    assert trunk.assembled_branches == ["agent/work-BL-0002", "agent/work-BL-0003"]
    assert all(a["assembled"] for a in _wave_done(out)["assembled"])


def test_assembly_order_independent_of_finish_order():
    """BL-0003's stream finishes FIRST (no delay) while BL-0002 is delayed; the
    barrier MUST still assemble in BL-id (spec) order, not finish order."""
    trunk = _MockTrunk()
    specs = [
        ("BL-0002", _ready_bl("BL-0002", events=[{"phase": "engineer.start"}], delay=0.02)),
        ("BL-0003", _ready_bl("BL-0003", events=[{"phase": "engineer.start"}], delay=0.0)),
    ]
    out = _drive(specs, trunk.assemble, concurrency=2)
    assert _assembly_order(out) == ["BL-0002", "BL-0003"]
    assert trunk.assembled_branches == ["agent/work-BL-0002", "agent/work-BL-0003"]


def test_conflict_bl_surfaced_not_dropped_siblings_assemble():
    """A BL whose assembly conflicts is SURFACED (assembled=False, kind=conflict)
    and does NOT advance the trunk; its sibling still assembles (no-abort)."""
    trunk = _MockTrunk()
    trunk.conflict_branches.add("agent/work-BL-0003")
    specs = [
        ("BL-0002", _ready_bl("BL-0002")),
        ("BL-0003", _ready_bl("BL-0003")),
    ]
    out = _drive(specs, trunk.assemble, concurrency=2)
    by = {a["bl_id"]: a for a in _wave_done(out)["assembled"]}
    assert by["BL-0002"]["assembled"] is True
    assert by["BL-0003"]["assembled"] is False
    assert by["BL-0003"]["kind"] == "conflict"
    assert by["BL-0003"]["conflict_files"] == ["shared/models.py"]
    # the conflicting BL is reported via an assembly event (surfaced, not dropped)
    conflict_events = [(bid, p) for tag, bid, p in out
                       if tag == "assembly" and bid == "BL-0003"]
    assert conflict_events and conflict_events[0][1].get("ok") is False
    # sibling advanced the trunk exactly once; conflict did not
    assert trunk.sha == 1
    assert trunk.assembled_branches == ["agent/work-BL-0002"]


def test_unready_bl_left_unassembled_with_reason():
    """An escalated/not-ready BL (no work_branch) is not assembled; the reason is
    preserved so the caller can route it to the escalation roll-up."""
    trunk = _MockTrunk()
    specs = [
        ("BL-0002", _ready_bl("BL-0002")),
        ("BL-0003", _unready_bl("BL-0003", outcome="engineer_escalated")),
    ]
    out = _drive(specs, trunk.assemble, concurrency=2)
    by = {a["bl_id"]: a for a in _wave_done(out)["assembled"]}
    assert by["BL-0002"]["assembled"] is True
    assert by["BL-0003"]["assembled"] is False
    assert by["BL-0003"]["reason"] == "engineer_escalated"
    # the escalated BL is never handed to the assembler → trunk advances once
    assert trunk.sha == 1


def test_live_events_pass_through_before_assembly():
    """Per-BL live events are yielded as ("event", bl_id, ev) BEFORE any assembly
    event, so the SSE stream stays legible and assembly is a strict barrier."""
    trunk = _MockTrunk()
    specs = [("BL-0002", _ready_bl("BL-0002", events=[{"phase": "qa.start"}]))]
    out = _drive(specs, trunk.assemble, concurrency=1)
    tags = [tag for tag, _, _ in out]
    # all "event" tags precede the first "assembly" tag (barrier semantics)
    first_assembly = tags.index("assembly")
    assert all(t != "assembly" or i >= first_assembly for i, t in enumerate(tags))
    evs = [(bid, p) for tag, bid, p in out if tag == "event"]
    assert any(bid == "BL-0002" and p.get("phase") == "qa.start" for bid, p in evs)
