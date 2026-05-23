"""Graphify graph.json reader and query helpers.

Loads the JSON output of `graphify update <repo>` and exposes structural queries
without shelling out to the CLI. Multiple repos can be loaded under named keys
(e.g. "reference", "target") so a single tool surface can address either.
"""

from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Graph:
    nodes: dict[str, dict] = field(default_factory=dict)
    out_edges: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))
    in_edges: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))

    @classmethod
    def load(cls, graph_json: Path) -> "Graph":
        raw = json.loads(graph_json.read_text())
        g = cls()
        for n in raw.get("nodes", []):
            g.nodes[n["id"]] = n
        for l in raw.get("links", []) + raw.get("edges", []):
            g.out_edges[l["source"]].append(l)
            g.in_edges[l["target"]].append(l)
        return g

    def find(self, label_substring: str, file_hint: str | None = None, limit: int = 10) -> list[dict]:
        q = label_substring.lower()
        hits = []
        for n in self.nodes.values():
            if q not in n.get("label", "").lower():
                continue
            if file_hint and file_hint not in (n.get("source_file") or ""):
                continue
            hits.append(n)
            if len(hits) >= limit:
                break
        return hits

    def neighbors(self, node_id: str, depth: int = 1) -> list[dict]:
        seen = {node_id}
        frontier = [node_id]
        out = []
        for _ in range(depth):
            next_frontier = []
            for nid in frontier:
                for l in self.out_edges.get(nid, []):
                    tgt = l["target"]
                    out.append({
                        "dir": "out",
                        "relation": l.get("relation"),
                        "from": self.nodes.get(nid, {}).get("label", nid),
                        "to": self.nodes.get(tgt, {}).get("label", tgt),
                        "to_id": tgt,
                        "to_file": self.nodes.get(tgt, {}).get("source_file"),
                    })
                    if tgt not in seen:
                        seen.add(tgt)
                        next_frontier.append(tgt)
                for l in self.in_edges.get(nid, []):
                    src = l["source"]
                    out.append({
                        "dir": "in",
                        "relation": l.get("relation"),
                        "from": self.nodes.get(src, {}).get("label", src),
                        "from_id": src,
                        "from_file": self.nodes.get(src, {}).get("source_file"),
                        "to": self.nodes.get(nid, {}).get("label", nid),
                    })
                    if src not in seen:
                        seen.add(src)
                        next_frontier.append(src)
            frontier = next_frontier
        return out

    def file_summary(self, file_path: str) -> list[dict]:
        out = []
        for n in self.nodes.values():
            if n.get("source_file") != file_path:
                continue
            calls = [
                self.nodes.get(l["target"], {}).get("label", l["target"])
                for l in self.out_edges.get(n["id"], [])
                if l.get("relation") == "calls"
            ]
            out.append({
                "label": n.get("label"),
                "id": n["id"],
                "line": n.get("source_location"),
                "calls": calls[:10],
            })
        return out

    def find_similar(self, node_id: str, k: int = 5) -> list[dict]:
        """Similarity = shared outgoing call targets (cheap structural proxy)."""
        if node_id not in self.nodes:
            return []
        my_targets = {l["target"] for l in self.out_edges.get(node_id, []) if l.get("relation") == "calls"}
        if not my_targets:
            return []
        scored = []
        for other_id, other in self.nodes.items():
            if other_id == node_id:
                continue
            other_targets = {l["target"] for l in self.out_edges.get(other_id, []) if l.get("relation") == "calls"}
            if not other_targets:
                continue
            overlap = len(my_targets & other_targets)
            if overlap:
                jaccard = overlap / len(my_targets | other_targets)
                scored.append((jaccard, other))
        scored.sort(key=lambda x: -x[0])
        return [{"score": round(s, 3), "label": n.get("label"), "file": n.get("source_file"), "id": n["id"]} for s, n in scored[:k]]


def _graphify_cache_dir(repo_root: Path) -> Path:
    """B3: shared content-addressed cache outside the worktree.

    Keyed by sha256 of the absolute repo path (first 16 hex chars). Each
    worktree gets its own cache slot — orphan caches from removed worktrees
    accumulate harmlessly under ~/.cache/agentic-skills/graphify/; operator
    can `rm -rf` the dir whenever they want a clean rebuild.
    """
    import hashlib
    key = hashlib.sha256(str(repo_root.resolve()).encode("utf-8")).hexdigest()[:16]
    base = Path.home() / ".cache" / "agentic-skills" / "graphify"
    base.mkdir(parents=True, exist_ok=True)
    cache = base / key
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _ensure_graphify_symlink(repo_root: Path) -> Path:
    """B3: pre-create the shared cache + symlink `<repo>/graphify-out` to it.

    The graphify CLI insists on writing to `<arg>/graphify-out/` (no --out
    flag). Symlinking that path to a shared cache directory:
      1) keeps the worktree's tree clean (just a single symlink, not 178 AST
         cache files that swept into Sprint 2 QA commits via `git add -A`)
      2) preserves graphify's incremental cache (same dir across reindex
         calls on the same worktree)
      3) is gitignore-protected anyway (`graphify-out/` skip in the
         target's .gitignore — belt + suspenders)

    Returns the cache dir.
    """
    cache = _graphify_cache_dir(repo_root)
    out = repo_root / "graphify-out"
    if out.is_symlink():
        # Existing symlink — replace if it points elsewhere.
        if out.resolve() != cache.resolve():
            out.unlink()
            out.symlink_to(cache)
    elif out.exists():
        # Legacy directory from a pre-B3 run; promote its contents into the
        # cache (best-effort), then replace with a symlink.
        import shutil
        for item in out.iterdir():
            dst = cache / item.name
            if dst.exists():
                continue  # cache wins
            shutil.move(str(item), str(dst))
        shutil.rmtree(out, ignore_errors=True)
        out.symlink_to(cache)
    else:
        out.symlink_to(cache)
    return cache


def ensure_indexed(repo_root: Path, *, force: bool = False) -> Path:
    """Run `graphify update` if graph.json is missing/stale. Returns graph.json
    path (canonical cache location, not the symlink).
    """
    cache_dir = _ensure_graphify_symlink(repo_root)
    graph_path = cache_dir / "graph.json"
    if graph_path.exists() and not force:
        return graph_path
    subprocess.run(
        ["graphify", "update", str(repo_root), "--no-cluster"],
        check=True,
        capture_output=True,
        text=True,
    )
    return graph_path


class GraphRegistry:
    """Holds named graphs (e.g., reference, target) loaded on demand."""

    def __init__(self):
        self._graphs: dict[str, Graph] = {}
        self._paths: dict[str, Path] = {}

    def register(self, name: str, repo_root: Path) -> None:
        self._paths[name] = repo_root

    def get(self, name: str) -> Graph:
        if name not in self._graphs:
            if name not in self._paths:
                raise KeyError(f"unknown graph source: {name!r} (known: {list(self._paths)})")
            graph_path = ensure_indexed(self._paths[name])
            self._graphs[name] = Graph.load(graph_path)
        return self._graphs[name]

    def reload(self, name: str) -> None:
        ensure_indexed(self._paths[name], force=True)
        self._graphs.pop(name, None)
