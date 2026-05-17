"""Repo indexing helpers.

`run_graphify_update`      — shells out to the `graphify` CLI to (re)build
                             `graphify-out/graph.json` for a repo.
`run_claude_context_index` — invokes the shared Node bridge (the one the
                             langgraph_engine retrieval layer uses) to index
                             the repo into Milvus via claude-context-core.

Both return a dict with `ok`, `summary`, and provider-specific fields.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path

# The Node bridge written by langgraph_engine.retrieval.semantic lives at the
# project root. We reuse it here instead of duplicating.
BRIDGE_DIR = Path(__file__).resolve().parents[4] / ".spike-node"
BRIDGE_SCRIPT = BRIDGE_DIR / "bridge.js"


async def _run(cmd: list[str], cwd: Path | None = None, env: dict | None = None, timeout: int = 600) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env or {**os.environ},
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return 124, "", f"timeout after {timeout}s"
    return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")


async def run_graphify_update(repo_path: Path) -> dict:
    """`graphify update <repo> --no-cluster` — fast tree-sitter extraction.

    Produces `<repo>/graphify-out/graph.json`.
    """
    if not shutil.which("graphify"):
        return {"ok": False, "error": "graphify CLI not on PATH (pip install graphifyy)"}
    code, stdout, stderr = await _run(
        ["graphify", "update", str(repo_path), "--no-cluster"],
        cwd=repo_path,
    )
    graph_path = repo_path / "graphify-out" / "graph.json"
    summary = {"ok": code == 0, "stdout_tail": stdout.strip().splitlines()[-10:], "stderr_tail": stderr.strip().splitlines()[-5:]}
    if graph_path.exists():
        try:
            g = json.loads(graph_path.read_text())
            summary["nodes"] = len(g.get("nodes", []))
            summary["edges"] = len(g.get("links", []) or g.get("edges", []))
            summary["graph_path"] = str(graph_path.relative_to(repo_path))
        except Exception as exc:  # noqa: BLE001
            summary["parse_error"] = str(exc)
    if code != 0:
        summary["error"] = f"graphify exit {code}"
    return summary


async def run_claude_context_index(repo_path: Path) -> dict:
    """Spawn the Node bridge with op=index. Requires env: EMBEDDING_PROVIDER,
    AZURE_OPENAI_*/OPENAI_API_KEY, MILVUS_ADDRESS, MILVUS_TOKEN.
    """
    if not BRIDGE_SCRIPT.exists():
        return {
            "ok": False,
            "error": f"bridge.js not found at {BRIDGE_SCRIPT}. "
                     "Run a semantic_search once via the langgraph harness to regenerate it.",
        }
    cmd = ["node", str(BRIDGE_SCRIPT), json.dumps({"op": "index", "repo": str(repo_path)})]
    code, stdout, stderr = await _run(cmd, cwd=BRIDGE_DIR, timeout=900)
    summary: dict = {"ok": code == 0, "exit_code": code}
    last = stdout.strip().splitlines()
    if last:
        try:
            parsed = json.loads(last[-1])
            summary["raw"] = parsed
            if parsed.get("ok") is not None:
                summary["ok"] = bool(parsed["ok"])
            if isinstance(parsed.get("result"), dict):
                stats = parsed["result"]
                summary["indexed_files"] = stats.get("indexedFiles")
                summary["total_chunks"] = stats.get("totalChunks")
                summary["status"] = stats.get("status")
        except json.JSONDecodeError:
            pass
    # Extract human-readable progress crumbs from node logs (printed on stdout
    # before the JSON result).
    progress = [l for l in stdout.splitlines() if "Processed" in l or "indexing completed" in l or "code chunks" in l]
    if progress:
        summary["progress"] = progress[-5:]
    if stderr.strip():
        summary["stderr_tail"] = stderr.strip().splitlines()[-5:]
    if code != 0 and "error" not in summary:
        summary["error"] = f"node exit {code}"
    return summary
