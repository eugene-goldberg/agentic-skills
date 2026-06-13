"""Regression test: SemanticRegistry.search() must short-circuit the blocking
op=index when the Milvus collection already has rows (2026-06-12, remote CPU-only).

Root cause it guards against: on CPU-only bge-m3 a full ``op=index`` of a large
repo exceeds the 900s bridge timeout. The old ``search()`` ran a blocking
``index()`` on the first call per process and returned the index *error* without
ever querying — so *every* agent ``semantic_search`` failed and the crew grounded
blind (observed: PO and engineer both errored
``"node bridge timed out after 900s during op='index'"``).

The fix wires the already-existing ``op=has_index`` bridge op into ``search()``:
when the collection has rows, skip indexing and query what is present.

These tests prove the discrimination by stubbing ``_run_bridge``:
  - collection has rows   -> op=index NOT called, op=search IS called
  - collection empty/none -> op=index called (original behavior preserved)
  - index times out + no rows -> error propagated, op=search NOT reached
"""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SEMANTIC_PY = REPO_ROOT / "langgraph_engine" / "retrieval" / "semantic.py"


def _load_semantic():
    spec = importlib.util.spec_from_file_location("_test_semantic", SEMANTIC_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_registry(mod, monkeypatch, responder):
    """Build a registry with one registered repo and a stubbed _run_bridge.

    `responder(command) -> dict` decides each bridge reply. Every call's op is
    appended to `ops` for assertion.
    """
    ops = []

    def fake_run_bridge(node_dir, command, *, timeout=None):
        ops.append(command["op"])
        return responder(command)

    monkeypatch.setattr(mod, "_run_bridge", fake_run_bridge)
    reg = mod.SemanticRegistry()
    reg.register("target", Path("/some/repo"))
    return reg, ops


def test_has_rows_skips_index_and_searches(monkeypatch):
    mod = _load_semantic()

    def responder(cmd):
        if cmd["op"] == "has_index":
            return {"ok": True, "result": {"exists": True, "has_rows": True}}
        if cmd["op"] == "search":
            return {"ok": True, "result": {"hits": [{"path": "X.cs"}]}}
        raise AssertionError(f"unexpected op {cmd['op']} (index must be skipped)")

    reg, ops = _make_registry(mod, monkeypatch, responder)
    r = reg.search("target", "find product count endpoint")

    assert "index" not in ops, "op=index must be skipped when collection has rows"
    assert ops == ["has_index", "search"]
    assert r["ok"] is True


def test_no_rows_falls_through_to_index(monkeypatch):
    mod = _load_semantic()

    def responder(cmd):
        if cmd["op"] == "has_index":
            return {"ok": True, "result": {"exists": False, "has_rows": False}}
        if cmd["op"] == "index":
            return {"ok": True}
        if cmd["op"] == "search":
            return {"ok": True, "result": {"hits": []}}
        raise AssertionError(f"unexpected op {cmd['op']}")

    reg, ops = _make_registry(mod, monkeypatch, responder)
    r = reg.search("target", "q")

    assert ops == ["has_index", "index", "search"]
    assert r["ok"] is True


def test_index_failure_propagates_when_no_rows(monkeypatch):
    mod = _load_semantic()

    def responder(cmd):
        if cmd["op"] == "has_index":
            return {"ok": True, "result": {"exists": False, "has_rows": False}}
        if cmd["op"] == "index":
            return {"ok": False, "error": "node bridge timed out after 900s during op='index'"}
        raise AssertionError("op=search must not run after a failed index")

    reg, ops = _make_registry(mod, monkeypatch, responder)
    r = reg.search("target", "q")

    assert ops == ["has_index", "index"]
    assert r["ok"] is False
    assert "timed out" in r["error"]


def test_has_index_unavailable_falls_through_to_index(monkeypatch):
    """If the has_index probe itself fails, behave like the old path (index)."""
    mod = _load_semantic()

    def responder(cmd):
        if cmd["op"] == "has_index":
            return {"ok": False, "error": "bridge error"}
        if cmd["op"] == "index":
            return {"ok": True}
        if cmd["op"] == "search":
            return {"ok": True, "result": {"hits": []}}
        raise AssertionError(f"unexpected op {cmd['op']}")

    reg, ops = _make_registry(mod, monkeypatch, responder)
    r = reg.search("target", "q")

    assert ops == ["has_index", "index", "search"]
    assert r["ok"] is True
