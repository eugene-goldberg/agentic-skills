"""End-to-end test of the retrieval tool surface."""
import os
import json
from pathlib import Path

# Load env from .env.openai for OPENAI_API_KEY
env_path = Path(__file__).resolve().parents[1] / ".env.openai"
for line in env_path.read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()
os.environ.setdefault("MILVUS_ADDRESS", "localhost:19530")
os.environ.setdefault("MILVUS_TOKEN", "")
os.environ.setdefault("EMBEDDING_MODEL", "text-embedding-3-small")

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Avoid pulling langgraph by importing retrieval module directly.
import importlib
retrieval = importlib.import_module("langgraph_engine.retrieval.tools")
make_retrieval_tools = retrieval.make_retrieval_tools  # noqa: E402

REF = Path(__file__).resolve().parents[1] / "reference-repos" / "fastapi-good-patterns"
LOG = Path("/tmp/retrieval_test.jsonl")
LOG.unlink(missing_ok=True)

tools = make_retrieval_tools(reference_repo=REF, log_path=LOG)
tool_map = {t.name: t for t in tools}
print("tools:", list(tool_map))

print("\n--- semantic_search ---")
r = tool_map["semantic_search"].invoke({"query": "JWT decode and current user dependency", "k": 3, "source": "reference"})
for h in r.get("hits", []):
    print(f"  {h['file']}:L{h['start_line']}  {h['snippet'][:90]!r}")

print("\n--- graph_neighbors ---")
r = tool_map["graph_neighbors"].invoke({"symbol": "get_current_user", "depth": 1, "source": "reference"})
print(json.dumps(r, indent=2)[:800])

print("\n--- graph_find_similar ---")
r = tool_map["graph_find_similar"].invoke({"symbol": "create_project", "k": 3, "source": "reference"})
print(json.dumps(r, indent=2)[:600])

print("\n--- graph_summary ---")
r = tool_map["graph_summary"].invoke({"path": "app/routers/projects.py", "source": "reference"})
print(json.dumps(r, indent=2)[:1000])

print("\n--- log ---")
print(LOG.read_text())
