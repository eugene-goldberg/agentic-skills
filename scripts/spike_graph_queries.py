"""Spike: verify the 3 representative graph queries we'll wrap as LangChain tools."""
import json
from pathlib import Path
from collections import defaultdict

GRAPH = Path("/Users/eugenegoldberg/dev/ai-projects/agentic-skills/reference-repos/fastapi-good-patterns/graphify-out/graph.json")
g = json.loads(GRAPH.read_text())
nodes = {n["id"]: n for n in g["nodes"]}
out_edges = defaultdict(list)
in_edges = defaultdict(list)
for l in g["links"]:
    out_edges[l["source"]].append(l)
    in_edges[l["target"]].append(l)


def find_by_label(query):
    q = query.lower()
    return [n for n in nodes.values() if q in n["label"].lower()]


def neighbors(node_id):
    out = []
    for l in out_edges.get(node_id, []):
        tgt = nodes.get(l["target"], {"label": l["target"]})
        out.append({"dir": "out", "relation": l["relation"], "target": tgt["label"]})
    for l in in_edges.get(node_id, []):
        src = nodes.get(l["source"], {"label": l["source"]})
        out.append({"dir": "in", "relation": l["relation"], "source": src["label"]})
    return out


def summarize_file(file_path):
    return [n for n in nodes.values() if n.get("source_file") == file_path]


print("=" * 60)
print("Q1: neighbors of get_current_user")
print("=" * 60)
for c in find_by_label("get_current_user"):
    print(f"\n[{c['id']}]  {c['label']}  ({c['source_file']})")
    for n in neighbors(c["id"]):
        if n["dir"] == "out":
            print(f"  --{n['relation']:14s}--> {n['target']}")
        else:
            print(f"  <--{n['relation']:13s}-- {n['source']}")

print("\n" + "=" * 60)
print("Q2: structural similarity — all 'check_*' guards in routers")
print("=" * 60)
guards = [n for n in nodes.values() if "check_" in n["label"].lower() and "routers" in (n.get("source_file", "") or "")]
for g_ in guards:
    callers = [nodes[l["source"]]["label"] for l in in_edges[g_["id"]] if l["relation"] == "calls"]
    print(f"  {g_['label']:40s} called by {len(callers)} funcs in {g_['source_file']}")

print("\n" + "=" * 60)
print("Q3: graph_summary(path='app/routers/projects.py')")
print("=" * 60)
for e in summarize_file("app/routers/projects.py"):
    out_calls = [nodes.get(l["target"], {"label": l["target"]})["label"] for l in out_edges[e["id"]] if l["relation"] == "calls"]
    print(f"  {e['label']:36s}  -> calls: {out_calls[:3] if out_calls else '(none)'}")

print("\n" + "=" * 60)
print(f"SPIKE OK: graph has {len(nodes)} nodes, {len(g['links'])} edges; 3 query types work")
print("=" * 60)
