"""A56 fix — retrieval readiness gate (warm_retrieval) + PO grounding check.

Part 1: ``retrieval_warmup.warm_retrieval`` spawns a LOCAL probe and blocks
until it reports the backend warm or an overall timeout. It must:
  - return ok=True when the probe exits 0 (``WARM_OK``),
  - return ok=False (never raise) when the probe keeps failing, bounded by timeout,
  - forward ONLY local provider env — NEVER Azure/OpenAI keys (external-free).

Part 2: ``orchestrator._count_po_grounding`` counts grounded retrieval calls in a
PO trace's ``retrieval.jsonl`` so a grounding-blind PO can be surfaced loudly.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import retrieval_warmup as w  # noqa: E402
import app.services.orchestrator as orch  # noqa: E402


# ── external-free guarantee ───────────────────────────────────────────────────

def test_build_local_env_excludes_external_keys(monkeypatch) -> None:
    """The warm-up must never forward Azure/OpenAI credentials — it is local-only
    by construction (operator directive 2026-06-07)."""
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "SECRET")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.azure.com")
    monkeypatch.setenv("OPENAI_API_KEY", "SECRET")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "Ollama")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    monkeypatch.setenv("MILVUS_ADDRESS", "localhost:19530")
    env = w.build_local_env(Path("/tmp/target"))
    assert "AZURE_OPENAI_API_KEY" not in env
    assert "AZURE_OPENAI_ENDPOINT" not in env
    assert "OPENAI_API_KEY" not in env
    # local provider env IS forwarded
    assert env["EMBEDDING_PROVIDER"] == "Ollama"
    assert env["OLLAMA_HOST"] == "http://127.0.0.1:11434"
    assert env["MILVUS_ADDRESS"] == "localhost:19530"
    assert env["RETRIEVAL_TARGET_REPO"] == str(Path("/tmp/target").resolve())
    assert "PYTHONPATH" in env


# ── warm_retrieval behavior (probe mocked via a fake python_bin script) ───────

def _fake_probe(tmp_path: Path, *, exit_code: int, stdout: str) -> str:
    """Write a tiny python script that stands in for `python -m mcp_servers.warm_probe`
    — prints stdout and exits with exit_code. We point warm_retrieval's python_bin
    at a wrapper that runs THIS script regardless of the `-m module` args."""
    probe = tmp_path / "fake_probe.py"
    probe.write_text(
        f"import sys\nprint({stdout!r})\nsys.exit({exit_code})\n", encoding="utf-8")
    # a wrapper 'python' that ignores `-m mcp_servers.warm_probe` and runs probe
    wrapper = tmp_path / "py_wrapper.py"
    wrapper.write_text(
        "import sys, runpy\n"
        f"runpy.run_path({str(probe)!r}, run_name='__main__')\n",
        encoding="utf-8")
    return str(wrapper)


def test_warm_retrieval_ok_when_probe_exits_zero(tmp_path) -> None:
    # Use the real interpreter but force it to run our fake probe via a wrapper.
    # warm_retrieval calls `python_bin -m mcp_servers.warm_probe`; we hijack by
    # making python_bin a script path is not possible (it execs `-m`), so instead
    # mock asyncio.create_subprocess_exec.
    async def _fake_exec(*args, **kwargs):
        return _FakeProc(returncode=0, out=b"WARM_OK\n", err=b"")
    import app.services.retrieval_warmup as mod
    orig = asyncio.create_subprocess_exec
    asyncio.create_subprocess_exec = _fake_exec  # type: ignore
    try:
        res = asyncio.run(w.warm_retrieval(tmp_path, timeout=5, retry_sleep=0))
    finally:
        asyncio.create_subprocess_exec = orig  # type: ignore
    assert res["ok"] is True
    assert res["attempts"] == 1
    assert res["reason"] == "warm"


def test_warm_retrieval_times_out_cleanly_when_probe_fails(tmp_path) -> None:
    calls = {"n": 0}

    async def _fail_exec(*args, **kwargs):
        calls["n"] += 1
        return _FakeProc(returncode=1, out=b"", err=b"WARM_FAIL not ready")
    orig = asyncio.create_subprocess_exec
    asyncio.create_subprocess_exec = _fail_exec  # type: ignore
    try:
        # short overall timeout, no sleep → a few attempts then a clean ok=False
        res = asyncio.run(w.warm_retrieval(tmp_path, timeout=0.3, retry_sleep=0))
    finally:
        asyncio.create_subprocess_exec = orig  # type: ignore
    assert res["ok"] is False           # never raises; degrades cleanly
    assert calls["n"] >= 1
    assert "WARM_FAIL" in res["reason"] or res["reason"] == "timeout"


class _FakeProc:
    def __init__(self, returncode: int, out: bytes, err: bytes) -> None:
        self.returncode = returncode
        self._out = out
        self._err = err

    async def communicate(self):
        return self._out, self._err

    def kill(self):  # noqa: D401
        pass


# ── PO grounding count (A56 part 2) ───────────────────────────────────────────

def test_count_po_grounding_counts_only_grounded_tools(tmp_path) -> None:
    d = tmp_path / "po-trace"
    d.mkdir()
    (d / "retrieval.jsonl").write_text("\n".join([
        json.dumps({"tool": "target_status", "n_source": 35}),       # NOT grounded
        json.dumps({"tool": "semantic_search", "n_hits": 6}),        # grounded
        json.dumps({"tool": "graph_neighbors", "n": 10}),            # grounded
        json.dumps({"tool": "graph_summary", "n": 21}),              # grounded
        "",                                                          # blank ok
        "{ broken json",                                             # ignored
    ]), encoding="utf-8")
    assert orch._count_po_grounding(str(d)) == 3


def test_count_po_grounding_zero_when_blind(tmp_path) -> None:
    d = tmp_path / "po-blind"
    d.mkdir()
    # only target_status (inventory) — the A56 grounding-blind PO signature
    (d / "retrieval.jsonl").write_text(
        json.dumps({"tool": "target_status", "n_source": 35}) + "\n", encoding="utf-8")
    assert orch._count_po_grounding(str(d)) == 0


def test_count_po_grounding_zero_when_missing(tmp_path) -> None:
    assert orch._count_po_grounding(None) == 0
    assert orch._count_po_grounding(str(tmp_path / "does-not-exist")) == 0
