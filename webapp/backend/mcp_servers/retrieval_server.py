"""MCP stdio server exposing the agentic-skills retrieval layer.

Tools:
  semantic_search(query, k=5, source="reference"|"target")
  graph_neighbors(symbol, depth=1, source="reference"|"target")
  graph_find_similar(symbol, k=5, source="reference"|"target")
  graph_summary(path, source="reference"|"target")

Configured via env vars (set by the spawner in claude_agent.py):
  RETRIEVAL_REFERENCE_REPO   absolute path to the reference repo (good patterns)
  RETRIEVAL_TARGET_REPO      absolute path to the target repo (current worktree)
  RETRIEVAL_LOG_PATH         optional path to append per-call JSONL audit log
  RETRIEVAL_TOOL_BUDGET      max calls before budget exhausted (default 30)

Run: `python -m mcp_servers.retrieval_server` from webapp/backend.
"""
# NOTE: deliberately NOT using `from __future__ import annotations`.
# FastMCP (mcp 1.9.x) introspects tool signatures with issubclass(), which
# raises TypeError on the *string* annotations that the future-import
# produces — every @mcp.tool() registration fails and the server never
# starts, which silently strips retrieval from every agent (see A59).
# Python 3.12 evaluates `X | Y` natively, so nothing here needs it.

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]

# Load retrieval modules directly by file path to avoid importing
# `langgraph_engine.__init__`, which pulls in the (heavy) langgraph state-graph
# code we don't need here.
import importlib.util


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_retrieval_dir = REPO_ROOT / "langgraph_engine" / "retrieval"
_graph_mod = _load("_retrieval_graph", _retrieval_dir / "graph.py")
_semantic_mod = _load("_retrieval_semantic", _retrieval_dir / "semantic.py")
GraphRegistry = _graph_mod.GraphRegistry
SemanticRegistry = _semantic_mod.SemanticRegistry

from mcp.server.fastmcp import FastMCP  # noqa: E402

SNIPPET_MAX_CHARS = 800
BUDGET = int(os.getenv("RETRIEVAL_TOOL_BUDGET", "30"))
LOG_PATH = Path(os.environ["RETRIEVAL_LOG_PATH"]) if os.getenv("RETRIEVAL_LOG_PATH") else None

graphs = GraphRegistry()
semantics = SemanticRegistry()
sources: dict[str, Path] = {}


# Cheap heuristic: a "source-bearing" repo has at least one tracked source-ish
# file. Empty / greenfield repos make graphify and the indexer either fail or
# produce zero hits — we short-circuit those so the PO agent gets a clean
# signal instead of a stack trace.
_SOURCE_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".rb", ".kt", ".cs", ".cpp", ".c", ".h", ".swift"}


def _looks_empty(repo_root: Path) -> bool:
    if not repo_root.exists():
        return True
    try:
        for p in repo_root.rglob("*"):
            # skip hidden + node_modules / .venv / __pycache__ / graphify-out
            parts = set(p.relative_to(repo_root).parts)
            if any(s.startswith(".") for s in parts):
                continue
            if parts & {"node_modules", "__pycache__", "graphify-out", ".venv", "venv", "dist", "build"}:
                continue
            if p.is_file() and p.suffix.lower() in _SOURCE_EXTS:
                return False
    except OSError:
        return True
    return True

_ref = os.getenv("RETRIEVAL_REFERENCE_REPO")
_tgt = os.getenv("RETRIEVAL_TARGET_REPO")
if _ref:
    p = Path(_ref).resolve()
    graphs.register("reference", p)
    semantics.register("reference", p)
    sources["reference"] = p
if _tgt:
    p = Path(_tgt).resolve()
    graphs.register("target", p)
    semantics.register("target", p)
    sources["target"] = p

# Cross-repo corpus (optional). RETRIEVAL_CORPUS_ROOT names a directory whose
# git subdirectories were indexed ahead of time (see
# scripts/batch_index_repos.py). RETRIEVAL_CORPUS_REPOS is the explicit
# alternative: an os.pathsep-separated list of repo paths. Unset → the
# corpus tool reports itself unconfigured and is otherwise inert, so this
# changes nothing for a normal per-BL agent spawn.
corpus_repos: list[Path] = []
_corpus_root = os.getenv("RETRIEVAL_CORPUS_ROOT")
_corpus_list = os.getenv("RETRIEVAL_CORPUS_REPOS")
if _corpus_list:
    corpus_repos = [Path(x).resolve() for x in _corpus_list.split(os.pathsep)
                    if x.strip()]
elif _corpus_root:
    root = Path(_corpus_root).expanduser().resolve()
    if root.is_dir():
        corpus_repos = sorted(p.resolve() for p in root.iterdir()
                              if (p / ".git").exists())

_calls = {"n": 0}


def _log(payload: dict) -> None:
    if LOG_PATH is None:
        return
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as f:
        f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), **payload}) + "\n")


def _budget(tool: str) -> dict | None:
    _calls["n"] += 1
    if _calls["n"] > BUDGET:
        msg = f"retrieval tool budget exhausted ({BUDGET}); stop calling retrieval, use what you have"
        _log({"tool": tool, "error": msg})
        return {"ok": False, "error": msg}
    return None


def _check_source(src: str) -> dict | None:
    if src not in sources:
        return {"ok": False, "error": f"unknown source {src!r}; available: {list(sources)}"}
    return None


def _empty_response(tool: str, src: str, **extra) -> dict:
    note = (
        f"source={src!r} appears to have no source files yet (greenfield). "
        "Skip target-repo retrieval and rely on the reference repo and the brief."
    )
    _log({"tool": tool, "source": src, "empty": True})
    payload = {"ok": True, "source": src, "empty": True, "note": note}
    payload.update(extra)
    return payload


mcp = FastMCP("retrieval")


_LANG_BY_EXT = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".go": "go", ".rs": "rust", ".java": "java", ".rb": "ruby",
    ".kt": "kotlin", ".cs": "csharp", ".cpp": "cpp", ".c": "c", ".h": "c",
    ".swift": "swift", ".sql": "sql",
}


def _scan_repo(root: Path, max_files: int = 5000) -> dict:
    """Quick deterministic scan of a repo. <100ms on typical sizes.

    Returns counts + a small sample of source files + language breakdown,
    enough for an agent to classify greenfield-vs-brownfield without any
    embedding / graph / network calls.
    """
    info = {
        "ok": True,
        "exists": root.exists(),
        "kind": "greenfield",
        "source_file_count": 0,
        "total_file_count": 0,
        "top_source_files": [],
        "languages": {},
        "has_tests": False,
        "has_pyproject": False,
        "has_package_json": False,
        "has_requirements_txt": False,
    }
    if not root.exists():
        info["note"] = f"target path does not exist: {root}"
        return info
    seen = 0
    for p in root.rglob("*"):
        if seen >= max_files:
            break
        rel = p.relative_to(root)
        parts = set(rel.parts)
        if any(s.startswith(".") for s in parts):
            continue
        if parts & {"node_modules", "__pycache__", "graphify-out", ".venv", "venv", "dist", "build"}:
            continue
        if not p.is_file():
            continue
        seen += 1
        info["total_file_count"] += 1
        name = p.name.lower()
        if name == "pyproject.toml":
            info["has_pyproject"] = True
        elif name == "package.json":
            info["has_package_json"] = True
        elif name == "requirements.txt":
            info["has_requirements_txt"] = True
        if "test" in parts or name.startswith("test_") or name.endswith("_test.py"):
            info["has_tests"] = True
        ext = p.suffix.lower()
        if ext in _LANG_BY_EXT:
            info["source_file_count"] += 1
            info["languages"][_LANG_BY_EXT[ext]] = info["languages"].get(_LANG_BY_EXT[ext], 0) + 1
            if len(info["top_source_files"]) < 30:
                info["top_source_files"].append(str(rel))
    info["kind"] = "brownfield" if info["source_file_count"] > 0 else "greenfield"
    return info


@mcp.tool()
def target_status() -> dict:
    """Fast (<100ms) classification of the target repo: greenfield or brownfield.

    Returns counts of source files, language breakdown, presence of common
    build manifests (pyproject.toml / package.json / requirements.txt), and
    a sample of source file paths.

    ALWAYS call this first when starting work on a target — it's deterministic,
    requires no embeddings, and tells you whether to bother with
    `semantic_search`/`graph_*` against the target.
    """
    tgt = sources.get("target")
    if tgt is None:
        return {"ok": False, "error": "no target repo registered for this session"}
    info = _scan_repo(tgt)
    info["target_path"] = str(tgt)
    info["reference_available"] = "reference" in sources
    _log({"tool": "target_status", "kind": info.get("kind"), "n_source": info.get("source_file_count")})
    return info


@mcp.tool()
def semantic_search(query: str, k: int = 5, source: str = "reference") -> dict:
    """Hybrid semantic+keyword search over an indexed repo.

    Args:
        query: natural-language description of the pattern you want to find.
        k: number of hits (1-10).
        source: 'reference' for curated good patterns, 'target' for the current target repo.
    """
    if (b := _budget("semantic_search")): return b
    if (e := _check_source(source)): return e
    k = max(1, min(int(k), 10))
    if _looks_empty(sources[source]):
        return _empty_response("semantic_search", source, query=query, hits=[])
    try:
        r = semantics.search(source, query, k=k)
    except Exception as exc:  # noqa: BLE001
        msg = f"{type(exc).__name__}: {exc}"
        _log({"tool": "semantic_search", "query": query, "error": msg})
        return {"ok": False, "source": source, "query": query, "error": msg, "hits": []}
    if not r.get("ok"):
        _log({"tool": "semantic_search", "query": query, "error": r.get("error")})
        return {**r, "hits": []}
    hits = []
    for h in r.get("result", []) or []:
        content = (h.get("content") or "")[:SNIPPET_MAX_CHARS]
        hits.append({
            "file": h.get("relativePath"),
            "start_line": h.get("startLine"),
            "end_line": h.get("endLine"),
            "snippet": content,
        })
    _log({"tool": "semantic_search", "query": query, "source": source, "n_hits": len(hits)})
    return {"ok": True, "source": source, "query": query, "hits": hits}


@mcp.tool()
def semantic_search_corpus(query: str, k: int = 8, max_per_repo: int = 3) -> dict:
    """Hybrid semantic+keyword search ACROSS every repo in the configured
    corpus (e.g. all EA service repos), ranked globally.

    Use this for cross-repo questions — "which service publishes the waste
    shipment event?", "where is the APIM policy for the odata route?" —
    where the answer may live in a repo other than the current target.
    Each hit names the repo it came from. Only pre-indexed repos are
    searched; anything not indexed is reported in `not_searched` so you can
    see what the answer did NOT cover.

    Args:
        query: natural-language description of what you're looking for.
        k: number of hits across the whole corpus (1-20).
        max_per_repo: cap hits from any single repo so one large repo can't
            monopolize the answer (default 3; 0 = uncapped).
    """
    if (b := _budget("semantic_search_corpus")): return b
    if not corpus_repos:
        return {"ok": False, "query": query, "hits": [],
                "error": ("no corpus configured; set RETRIEVAL_CORPUS_ROOT "
                          "(a dir of git repos) or RETRIEVAL_CORPUS_REPOS")}
    k = max(1, min(int(k), 20))
    try:
        r = semantics.search_multi(corpus_repos, query, k=k,
                                   max_per_repo=(int(max_per_repo) or None))
    except Exception as exc:  # noqa: BLE001
        msg = f"{type(exc).__name__}: {exc}"
        _log({"tool": "semantic_search_corpus", "query": query, "error": msg})
        return {"ok": False, "query": query, "error": msg, "hits": []}
    if not r.get("ok"):
        _log({"tool": "semantic_search_corpus", "query": query, "error": r.get("error")})
        return {**r, "hits": []}
    res = r.get("result") or {}
    hits = []
    for h in res.get("hits", []) or []:
        hits.append({
            "repo": h.get("repoName"),
            "file": h.get("relativePath"),
            "start_line": h.get("startLine"),
            "end_line": h.get("endLine"),
            "snippet": (h.get("content") or "")[:SNIPPET_MAX_CHARS],
        })
    not_searched = [s.get("repo", "").rstrip("/").split("/")[-1]
                    for s in (res.get("skipped") or [])]
    _log({"tool": "semantic_search_corpus", "query": query,
          "n_hits": len(hits), "n_searched": res.get("n_searched"),
          "n_skipped": len(not_searched)})
    return {"ok": True, "query": query, "hits": hits,
            "repos_searched": res.get("n_searched"),
            "not_searched": not_searched}


@mcp.tool()
def graph_neighbors(symbol: str, depth: int = 1, source: str = "reference") -> dict:
    """List structural neighbors (callers, callees, contains) of a symbol.

    Args:
        symbol: function/class/file name substring (case-insensitive).
        depth: traversal depth (1 or 2).
        source: 'reference' or 'target'.
    """
    if (b := _budget("graph_neighbors")): return b
    if (e := _check_source(source)): return e
    depth = max(1, min(int(depth), 2))
    if _looks_empty(sources[source]):
        return _empty_response("graph_neighbors", source, symbol=symbol, matches=[], neighbors=[])
    try:
        g = graphs.get(source)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "source": source, "error": f"graph unavailable: {exc}", "matches": [], "neighbors": []}
    matches = g.find(symbol, limit=3)
    if not matches:
        return {"ok": True, "matches": [], "neighbors": []}
    all_neighbors = []
    for m in matches:
        for n in g.neighbors(m["id"], depth=depth):
            all_neighbors.append({**n, "of": m["label"], "in_file": m.get("source_file")})
    _log({"tool": "graph_neighbors", "symbol": symbol, "n": len(all_neighbors)})
    return {
        "ok": True,
        "matches": [{"label": m["label"], "file": m.get("source_file")} for m in matches],
        "neighbors": all_neighbors[:60],
    }


@mcp.tool()
def graph_find_similar(symbol: str, k: int = 5, source: str = "reference") -> dict:
    """Find structurally similar entities (shared call targets, Jaccard similarity).

    Args:
        symbol: function/class name substring.
        k: number of similar entities.
        source: 'reference' or 'target'.
    """
    if (b := _budget("graph_find_similar")): return b
    if (e := _check_source(source)): return e
    k = max(1, min(int(k), 10))
    if _looks_empty(sources[source]):
        return _empty_response("graph_find_similar", source, symbol=symbol, similar=[])
    try:
        g = graphs.get(source)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "source": source, "error": f"graph unavailable: {exc}", "similar": []}
    matches = g.find(symbol, limit=1)
    if not matches:
        return {"ok": True, "similar": []}
    sim = g.find_similar(matches[0]["id"], k=k)
    _log({"tool": "graph_find_similar", "symbol": symbol, "n": len(sim)})
    return {"ok": True, "of": matches[0]["label"], "similar": sim}


@mcp.tool()
def graph_summary(path: str, source: str = "reference") -> dict:
    """Summarize entities and their call targets in a given file.

    Args:
        path: repo-relative file path (e.g., 'app/routers/projects.py').
        source: 'reference' or 'target'.
    """
    if (b := _budget("graph_summary")): return b
    if (e := _check_source(source)): return e
    if _looks_empty(sources[source]):
        return _empty_response("graph_summary", source, path=path, entities=[])
    try:
        g = graphs.get(source)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "source": source, "error": f"graph unavailable: {exc}", "entities": []}
    entities = g.file_summary(path)
    _log({"tool": "graph_summary", "path": path, "n": len(entities)})
    return {"ok": True, "path": path, "entities": entities}


if __name__ == "__main__":
    mcp.run()
