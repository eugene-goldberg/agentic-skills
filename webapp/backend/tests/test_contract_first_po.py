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
