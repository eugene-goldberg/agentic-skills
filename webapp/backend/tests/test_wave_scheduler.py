"""Wave-execution Phase 2: the wave scheduler (_dep_waves) + flag plumbing.

Phase 2 groups BLs by the R21 dependency DAG into topological waves and emits
wave.start/done boundaries, running each wave at concurrency=1 (identical per-BL
semantics). These tests cover the scheduling primitive and that the flag threads
through run_brief / RunBriefRequest with a safe default (OFF = today's order).
"""
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import backlog as bl
from app.services import orchestrator as orch


def _backlog(*sections: str) -> list:
    return bl.parse("# Backlog: Test\n\n" + "\n\n".join(sections))


def _bl(num: str, deps: str) -> str:
    return (f"## BL-{num}: Item {num}\n"
            f"**Acceptance:**\n1. a substantive criterion here.\n2. another one here.\n"
            f"**Dependencies:** {deps}\n**Exposes:** none\n**Consumes:** none")


def test_waves_group_by_dag_layer():
    # BL-0001 foundation; 0002/0003/0004 each depend only on 0001 → 2 waves
    items = _backlog(_bl("0001", "none"), _bl("0002", "BL-0001"),
                     _bl("0003", "BL-0001"), _bl("0004", "BL-0001"))
    waves = orch._dep_waves(items)
    assert [it.id for it in waves[0]] == ["BL-0001"]
    assert {it.id for it in waves[1]} == {"BL-0002", "BL-0003", "BL-0004"}


def test_independent_bls_collapse_to_one_wave():
    items = _backlog(_bl("0001", "none"), _bl("0002", "none"), _bl("0003", "none"))
    waves = orch._dep_waves(items)
    assert len(waves) == 1
    assert {it.id for it in waves[0]} == {"BL-0001", "BL-0002", "BL-0003"}


def test_chain_makes_one_bl_per_wave():
    items = _backlog(_bl("0001", "none"), _bl("0002", "BL-0001"), _bl("0003", "BL-0002"))
    waves = orch._dep_waves(items)
    assert [[it.id for it in w] for w in waves] == [["BL-0001"], ["BL-0002"], ["BL-0003"]]


def test_cycle_falls_back_to_single_wave():
    # R21 PO gate rejects cycles; the scheduler degrades safely rather than raising.
    items = _backlog(_bl("0001", "BL-0002"), _bl("0002", "BL-0001"))
    waves = orch._dep_waves(items)
    assert len(waves) == 1
    assert {it.id for it in waves[0]} == {"BL-0001", "BL-0002"}


def test_flattened_wave_order_is_dependency_respecting():
    items = _backlog(_bl("0001", "none"), _bl("0002", "BL-0001"), _bl("0003", "BL-0001"))
    flat = [it.id for w in orch._dep_waves(items) for it in w]
    # every dep precedes its dependent
    assert flat.index("BL-0001") < flat.index("BL-0002")
    assert flat.index("BL-0001") < flat.index("BL-0003")


def test_wave_execution_flag_plumbed():
    # orchestrator.run_brief accepts the flag, default OFF
    sig = inspect.signature(orch.run_brief)
    assert "wave_execution" in sig.parameters
    assert sig.parameters["wave_execution"].default is False
    # RunBriefRequest carries it, default OFF
    from app.routers.projects import RunBriefRequest
    assert RunBriefRequest.model_fields["wave_execution"].default is False
