"""R21 (wave-execution Phase 1): PO dependency DAG + interface contracts.

Covers the backlog-layer validation that the PO gate enforces — the structured
``**Dependencies:**`` graph (missing field / dangling ref / self-loop / cycle) and
the ``**Exposes:**``/``**Consumes:**`` contract coverage — plus the topological
wave layering the Phase-2 scheduler will reuse, and the R21 fix prompt.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import backlog as bl
from app.services import doctrine_validator as dv
from app.services import doctrine_spec as ds


def _backlog(*sections: str) -> list:
    return bl.parse("# Backlog: Test\n\n" + "\n\n".join(sections))


_C = ("**Acceptance:**\n1. a criterion long enough to be substantive here.\n"
      "2. another criterion that is also sufficiently long.")


def _bl(num: str, deps: str, exposes: str = "none", consumes: str = "none",
        title: str = "Item") -> str:
    return (f"## BL-{num}: {title}\n{_C}\n"
            f"**Dependencies:** {deps}\n**Exposes:** {exposes}\n**Consumes:** {consumes}")


# ── dependency DAG ────────────────────────────────────────────────────────────

def test_clean_dag_passes():
    items = _backlog(_bl("0001", "none", exposes="ProductReadDto.availableQuantity"),
                     _bl("0002", "BL-0001", consumes="ProductReadDto.availableQuantity"))
    assert bl.dependency_report(items) == {}
    assert bl.contract_report(items) == {}


def test_missing_dependencies_field_flagged():
    # a BL with no **Dependencies:** line at all
    items = _backlog(f"## BL-0001: X\n{_C}\n**Exposes:** none\n**Consumes:** none")
    rep = bl.dependency_report(items)
    assert "BL-0001" in rep and "Dependencies" in rep["BL-0001"]


def test_dangling_reference_flagged():
    items = _backlog(_bl("0001", "none"), _bl("0002", "BL-0099"))
    rep = bl.dependency_report(items)
    assert "BL-0002" in rep and "BL-0099" in rep["BL-0002"]


def test_self_loop_flagged():
    items = _backlog(_bl("0001", "BL-0001"))
    rep = bl.dependency_report(items)
    assert "BL-0001" in rep and "self" in rep["BL-0001"].lower()


def test_cycle_flagged():
    items = _backlog(_bl("0001", "BL-0002"), _bl("0002", "BL-0001"))
    rep = bl.dependency_report(items)
    assert "__cycle__" in rep


# ── topological waves (Phase-2 scheduler primitive) ───────────────────────────

def test_topological_waves_layers():
    # 0001 foundation; 0002/0003/0004 each depend only on 0001 → 2 waves
    items = _backlog(_bl("0001", "none"), _bl("0002", "BL-0001"),
                     _bl("0003", "BL-0001"), _bl("0004", "BL-0001"))
    waves = bl.topological_waves(items)
    assert waves[0] == ["BL-0001"]
    assert set(waves[1]) == {"BL-0002", "BL-0003", "BL-0004"}


def test_topological_waves_raises_on_cycle():
    items = _backlog(_bl("0001", "BL-0002"), _bl("0002", "BL-0001"))
    try:
        bl.topological_waves(items)
        assert False, "expected ValueError on cycle"
    except ValueError as e:
        assert "cycle" in str(e).lower()


# ── interface contracts ───────────────────────────────────────────────────────

def test_consume_with_no_exposer_flagged():
    items = _backlog(_bl("0001", "none"),
                     _bl("0002", "BL-0001", consumes="Nonexistent.Thing"))
    rep = bl.contract_report(items)
    assert "BL-0002" in rep


def test_consume_from_undeclared_dependency_flagged():
    # BL-0003 exposes the contract, but BL-0002 consumes it without declaring BL-0003
    items = _backlog(_bl("0001", "none"),
                     _bl("0002", "BL-0001", consumes="OrderSvc.place"),
                     _bl("0003", "none", exposes="OrderSvc.place"))
    rep = bl.contract_report(items)
    assert "BL-0002" in rep and "BL-0003" in rep["BL-0002"]


def test_contract_signature_normalization_matches():
    # exposed with a full signature, consumed by short name → still matches
    items = _backlog(
        _bl("0001", "none", exposes="IProductRepository.TryDecrementStockAsync(productId, quantity) -> bool"),
        _bl("0002", "BL-0001", consumes="IProductRepository.TryDecrementStockAsync"))
    assert bl.contract_report(items) == {}


def test_no_consumes_never_errors():
    # depends on BL-0001 for ordering only, consumes nothing → no contract error
    items = _backlog(_bl("0001", "none"), _bl("0002", "BL-0001", consumes="none"))
    assert bl.contract_report(items) == {}


# ── fix prompt + registry ─────────────────────────────────────────────────────

def test_fix_prompt_routes_to_r21_on_dep_errors():
    validation = {"missing": [], "empty": [], "thin_criteria": {},
                  "dependency_errors": {"BL-0002": "depends on unknown BL-id(s): BL-0099"},
                  "contract_errors": {}}
    p = dv.build_fix_prompt("po", validation)
    assert "R21" in p and "BL-0002" in p and "**Dependencies:**" in p


def test_r21_registered_and_resolvable():
    rule = ds.by_id("R21")
    assert rule is not None and rule.enforced
    assert "R21" in ds.CANONICAL_RULE_IDS
    # I-2: the check_ref must resolve to a real callable
    assert callable(ds.resolve_check(rule))
