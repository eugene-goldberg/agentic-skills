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


def _graphify_cache_dir(repo_path: Path) -> Path:
    """B3: shared content-addressed cache outside the worktree. Mirror of the
    helper in langgraph_engine/retrieval/graph.py — duplicated rather than
    cross-imported to keep webapp/ standalone (per CLAUDE.md subproject
    boundary)."""
    import hashlib
    key = hashlib.sha256(str(repo_path.resolve()).encode("utf-8")).hexdigest()[:16]
    base = Path.home() / ".cache" / "agentic-skills" / "graphify"
    base.mkdir(parents=True, exist_ok=True)
    cache = base / key
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _ensure_graphify_symlink(repo_path: Path) -> Path:
    """B3: pre-create cache + symlink `<repo>/graphify-out` to it.

    graphify CLI has no --out flag; writes to `<arg>/graphify-out/`. Symlinking
    keeps the worktree clean (one symlink, not 178 AST files) AND preserves
    graphify's incremental cache across reindex calls.
    """
    cache = _graphify_cache_dir(repo_path)
    out = repo_path / "graphify-out"
    if out.is_symlink():
        if out.resolve() != cache.resolve():
            out.unlink()
            out.symlink_to(cache)
    elif out.exists():
        # Legacy dir from pre-B3 run — promote contents into cache, replace
        # with symlink.
        for item in out.iterdir():
            dst = cache / item.name
            if dst.exists():
                continue
            shutil.move(str(item), str(dst))
        shutil.rmtree(out, ignore_errors=True)
        out.symlink_to(cache)
    else:
        out.symlink_to(cache)
    return cache


async def run_graphify_update(repo_path: Path) -> dict:
    """`graphify update <repo> --no-cluster` — fast tree-sitter extraction.

    B3: output is redirected via a `<repo>/graphify-out` symlink to
    `~/.cache/agentic-skills/graphify/<sha256(repo)[:16]>/`. The worktree
    only ever contains a single symlink; the actual cache lives outside
    so `git add -A` in agent flows can no longer sweep AST files into
    QA commits.
    """
    if not shutil.which("graphify"):
        return {"ok": False, "error": "graphify CLI not on PATH (pip install graphifyy)"}
    cache_dir = _ensure_graphify_symlink(repo_path)
    code, stdout, stderr = await _run(
        ["graphify", "update", str(repo_path), "--no-cluster"],
        cwd=repo_path,
    )
    # Canonical read path is the cache dir (the symlink resolves there too,
    # but consumers should not depend on the symlink being present).
    graph_path = cache_dir / "graph.json"
    summary = {"ok": code == 0, "stdout_tail": stdout.strip().splitlines()[-10:], "stderr_tail": stderr.strip().splitlines()[-5:]}
    if graph_path.exists():
        try:
            g = json.loads(graph_path.read_text())
            summary["nodes"] = len(g.get("nodes", []))
            summary["edges"] = len(g.get("links", []) or g.get("edges", []))
            summary["graph_path"] = str(graph_path)
            summary["cache_dir"] = str(cache_dir)
        except Exception as exc:  # noqa: BLE001
            summary["parse_error"] = str(exc)
    if code != 0:
        summary["error"] = f"graphify exit {code}"
    return summary


async def run_claude_context_index(repo_path: Path, op: str = "index") -> dict:
    """Spawn the Node bridge with op=index. Requires env: EMBEDDING_PROVIDER,
    AZURE_OPENAI_*/OPENAI_API_KEY, MILVUS_ADDRESS, MILVUS_TOKEN.
    """
    if not BRIDGE_SCRIPT.exists():
        return {
            "ok": False,
            "error": f"bridge.js not found at {BRIDGE_SCRIPT}. "
                     "Run a semantic_search once via the langgraph harness to regenerate it.",
        }
    cmd = ["node", str(BRIDGE_SCRIPT), json.dumps({"op": op, "repo": str(repo_path)})]
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
