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
