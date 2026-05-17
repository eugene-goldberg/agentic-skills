"""LangChain @tool wrappers for the retrieval layer.

Tool surface (per the implementation plan):
  semantic_search(query, k=5, source="reference"|"target")
  graph_neighbors(symbol, depth=1, source="reference"|"target")
  graph_find_similar(symbol, k=5, source="reference"|"target")
  graph_summary(path, source="reference"|"target")

Activated via `make_retrieval_tools(reference_repo=..., target_repo=...)` and
appended to the agent's existing tool list.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.tools import tool

from .graph import GraphRegistry
from .semantic import SemanticRegistry


SNIPPET_MAX_CHARS = 800
TOOL_CALL_BUDGET_DEFAULT = 30


def make_retrieval_tools(
    *,
    reference_repo: Path | None = None,
    target_repo: Path | None = None,
    log_path: Path | None = None,
) -> list:
    graphs = GraphRegistry()
    semantics = SemanticRegistry()
    sources: dict[str, Path] = {}
    if reference_repo is not None:
        graphs.register("reference", reference_repo)
        semantics.register("reference", reference_repo)
        sources["reference"] = reference_repo
    if target_repo is not None:
        graphs.register("target", target_repo)
        semantics.register("target", target_repo)
        sources["target"] = target_repo

    call_counter = {"n": 0}
    budget = int(os.getenv("RETRIEVAL_TOOL_BUDGET", str(TOOL_CALL_BUDGET_DEFAULT)))

    def _log(payload: dict) -> None:
        if log_path is None:
            return
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a") as f:
            f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), **payload}) + "\n")

    def _check_budget(tool_name: str) -> dict | None:
        call_counter["n"] += 1
        if call_counter["n"] > budget:
            msg = f"retrieval tool budget exhausted ({budget}); stop calling retrieval, use what you have"
            _log({"tool": tool_name, "error": msg})
            return {"ok": False, "error": msg}
        return None

    def _check_source(src: str) -> dict | None:
        if src not in sources:
            return {"ok": False, "error": f"unknown source {src!r}; available: {list(sources)}"}
        return None

    @tool
    def semantic_search(query: str, k: int = 5, source: str = "reference") -> dict:
        """Hybrid semantic+keyword search over an indexed repo.

        Args:
            query: natural-language description of the pattern you want to find.
            k: number of hits (1-10).
            source: 'reference' for curated good patterns, 'target' for the
                    current target repo (after at least one engineering cycle).
        Returns dict with `hits`: [{file, start_line, end_line, content_snippet}].
        """
        if (b := _check_budget("semantic_search")): return b
        if (e := _check_source(source)): return e
        k = max(1, min(k, 10))
        r = semantics.search(source, query, k=k)
        if not r.get("ok"):
            _log({"tool": "semantic_search", "query": query, "error": r.get("error")})
            return r
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

    @tool
    def graph_neighbors(symbol: str, depth: int = 1, source: str = "reference") -> dict:
        """List structural neighbors (callers, callees, contains) of a symbol.

        Args:
            symbol: function/class/file name substring (case-insensitive).
            depth: traversal depth (1 or 2).
            source: 'reference' or 'target'.
        """
        if (b := _check_budget("graph_neighbors")): return b
        if (e := _check_source(source)): return e
        depth = max(1, min(depth, 2))
        g = graphs.get(source)
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

    @tool
    def graph_find_similar(symbol: str, k: int = 5, source: str = "reference") -> dict:
        """Find structurally similar entities (shared call targets, Jaccard).

        Args:
            symbol: function/class name substring.
            k: number of similar entities.
            source: 'reference' or 'target'.
        """
        if (b := _check_budget("graph_find_similar")): return b
        if (e := _check_source(source)): return e
        k = max(1, min(k, 10))
        g = graphs.get(source)
        matches = g.find(symbol, limit=1)
        if not matches:
            return {"ok": True, "similar": []}
        sim = g.find_similar(matches[0]["id"], k=k)
        _log({"tool": "graph_find_similar", "symbol": symbol, "n": len(sim)})
        return {"ok": True, "of": matches[0]["label"], "similar": sim}

    @tool
    def graph_summary(path: str, source: str = "reference") -> dict:
        """Summarize entities and their call targets in a given file.

        Args:
            path: repo-relative file path (e.g., 'app/routers/projects.py').
            source: 'reference' or 'target'.
        """
        if (b := _check_budget("graph_summary")): return b
        if (e := _check_source(source)): return e
        g = graphs.get(source)
        entities = g.file_summary(path)
        _log({"tool": "graph_summary", "path": path, "n": len(entities)})
        return {"ok": True, "path": path, "entities": entities}

    return [semantic_search, graph_neighbors, graph_find_similar, graph_summary]
