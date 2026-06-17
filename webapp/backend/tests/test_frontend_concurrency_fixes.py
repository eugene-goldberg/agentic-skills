"""G2 (concurrent-wave PO file-disjoint doctrine) + Fix A (frontend-aware gate)
unit tests. Frontend-concurrency diagnostic follow-ups, 2026-06-16."""
import os
import tempfile
from pathlib import Path

import pytest

from app.services import prompts as prompts_svc
from app.services import prompts_brownfield as bf
from app.services import regression_gate as rg


# ───────────────────────── G2: PO concurrent-wave doctrine ─────────────────
def test_wave_disjoint_instruction_text():
    t = bf.po_wave_disjoint_instruction()
    assert "FILE-DISJOINT" in t
    assert "same wave" in t.lower()
    assert "Dependencies:" in t  # the serialize-via-dependency fallback
    assert "App.tsx" in t or "Home.tsx" in t  # shared-parent example


def _po(tmp, *, wave_concurrent, contract_first=False):
    # brownfield family resolves to build_po_prompt_brownfield
    return prompts_svc.build_po("brownfield", "add three small UI widgets to the storefront",
                                "diag", Path(tmp), wave_concurrent=wave_concurrent,
                                contract_first=contract_first)


def test_po_prompt_includes_wave_doctrine_only_when_concurrent(tmp_path):
    on = _po(tmp_path, wave_concurrent=True)
    off = _po(tmp_path, wave_concurrent=False)
    assert "PARALLEL WAVE EXECUTION" in on
    assert "FILE-DISJOINT" in on
    assert "PARALLEL WAVE EXECUTION" not in off  # byte-identical to pre-G2 when off


def test_po_wave_doctrine_suppressed_under_contract_first(tmp_path):
    # contract_first owns its own (C#/binder) disjointness doctrine; the wave block
    # (serialize-via-Dependency, no binder) must NOT also be appended.
    both = _po(tmp_path, wave_concurrent=True, contract_first=True)
    assert "PARALLEL WAVE EXECUTION" not in both


# ───────────────────────── Fix A: frontend-aware gate helpers ──────────────
def test_is_frontend_test():
    assert rg._is_frontend_test("frontend/src/components/BackToTop.test.tsx")
    assert rg._is_frontend_test("src/foo.test.ts")
    assert rg._is_frontend_test("a/b.test.jsx")
    assert not rg._is_frontend_test("backend/tests/FooTests.cs")
    assert not rg._is_frontend_test("backend/tests/test_foo.py")
    assert not rg._is_frontend_test("src/Button.tsx")  # not a test file


class _Cfg:
    def __init__(self, app_boot):
        self.app_boot = app_boot


def test_frontend_dir_from_app_boot():
    assert rg._frontend_dir(_Cfg({"frontend": {"dir": "frontend"}})) == "frontend"
    assert rg._frontend_dir(_Cfg({"frontend": {"cmd": ["x"]}})) is None  # no dir
    assert rg._frontend_dir(_Cfg({})) is None
    assert rg._frontend_dir(_Cfg(None)) is None
    assert rg._frontend_dir(object()) is None  # no app_boot attr is tolerated...


def test_repo_config_parses_frontend_test_cmd(tmp_path):
    import json
    from app.services import repo_config as rc
    (tmp_path / rc.CONFIG_FILENAME).write_text(json.dumps({
        "agent_branch": "integration", "main_ref": "main",
        "test_cmd": ["dotnet", "test"],
        "frontend_test_cmd": ["npm", "run", "test", "--"],
        "app_boot": {"port": 5096, "cmd": ["x"], "frontend": {"dir": "frontend", "cmd": ["y"]}},
    }))
    cfg = rc.load(tmp_path)
    assert cfg.frontend_test_cmd == ["npm", "run", "test", "--"]
    # absent -> None (backward compatible)
    (tmp_path / rc.CONFIG_FILENAME).write_text(json.dumps({
        "agent_branch": "integration", "main_ref": "main", "test_cmd": ["pytest"]}))
    assert rc.load(tmp_path).frontend_test_cmd is None
