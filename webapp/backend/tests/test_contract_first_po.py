"""Contract-First Phase B: the PO contract instruction must teach contract-first
PARALLEL decomposition (vertical slices; Dependencies: none unless ordering)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import prompts_brownfield as pb


def test_contract_instruction_teaches_parallel_decomposition():
    low = pb.po_contract_instruction().lower()
    assert "parallel" in low
    assert "vertical slice" in low
    assert "dependencies: none" in low   # the keystone: do not add a dep just to consume
    assert "fan" in low                  # the DAG should fan out


def test_contract_instruction_still_requires_openapi():
    block = pb.po_contract_instruction()
    assert "openapi" in block.lower() and "3.1" in block


# ── Contract-First Phase C: per-BL engineer builds against stubs + mocks ──

from app.services import prompts as _prompts


def test_engineer_prompt_contract_first_injects_stub_mock_guidance():
    on = pb.build_engineer_prompt_brownfield("BL-0002", "## BL-0002: X", contract_first=True)
    off = pb.build_engineer_prompt_brownfield("BL-0002", "## BL-0002: X", contract_first=False)
    assert "CONTRACT-FIRST SLICE" in on
    low = on.lower()
    assert "mock" in low and "stub" in low and "file-disjoint" in low
    assert "contract/openapi.yaml" in on
    # flag-off path carries no contract block (byte-identical to today)
    assert "CONTRACT-FIRST SLICE" not in off


def test_build_engineer_dispatcher_threads_contract_first(tmp_path):
    on = _prompts.build_engineer("brownfield", "BL-0001", "## BL-0001: X", tmp_path,
                                 contract_first=True)
    off = _prompts.build_engineer("brownfield", "BL-0001", "## BL-0001: X", tmp_path,
                                  contract_first=False)
    assert "CONTRACT-FIRST SLICE" in on
    assert "CONTRACT-FIRST SLICE" not in off


# ── Contract-First Phase D: materializer + engineer emit the DI module convention ──

def test_materializer_emits_module_and_aggregator_convention():
    p = pb.build_stub_materializer_prompt_brownfield("openapi: 3.1.0\ninfo:\n  title: X")
    assert "@contract-module" in p
    assert "@contract-aggregator:begin" in p
    assert "kind=stub" in p
    assert "AddFeatureModules" in p


def test_engineer_block_emits_real_module_convention():
    blk = pb._engineer_contract_block()
    assert "@contract-module" in blk and "kind=real" in blk
    assert "IServiceCollection" in blk and "Module" in blk


# ── Convention tightening (proof-2 finding): slices must not touch the composition root ──

def test_engineer_block_forbids_composition_root_edits():
    blk = pb._engineer_contract_block()
    assert "MUST NOT edit" in blk and "Program.cs" in blk
    assert "FeatureModules.cs" in blk          # aggregator named as off-limits
    assert "OVERWRITE THAT SAME FILE" in blk   # overwrite-in-place model
    # the old loophole phrasing must be gone
    assert "beyond the single registration of your own real impl" not in blk


def test_materializer_single_program_cs_touch():
    p = pb.build_stub_materializer_prompt_brownfield("openapi: 3.1.0\ninfo:\n  title: X")
    assert "ONE and ONLY edit to Program.cs" in p


def test_po_doctrine_no_shared_composition_root():
    po = pb.po_contract_instruction()
    assert "No shared composition root" in po
    assert "Program.cs" in po
