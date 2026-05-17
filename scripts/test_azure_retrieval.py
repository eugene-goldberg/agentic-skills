"""Test retrieval tools with Azure OpenAI embeddings (gpt-5.4 + text-embedding-3-large)."""
import os, sys
from pathlib import Path

env_path = Path(__file__).resolve().parents[1] / ".env.gpt54"
for line in env_path.read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import importlib
retr = importlib.import_module("langgraph_engine.retrieval.tools")

REF = Path(__file__).resolve().parents[1] / "reference-repos" / "fastapi-good-patterns"
LOG = Path("/tmp/azure_retrieval_test.jsonl")
LOG.unlink(missing_ok=True)

tools = retr.make_retrieval_tools(reference_repo=REF, log_path=LOG)
tool_map = {t.name: t for t in tools}
print("tools:", list(tool_map))
print("EMBEDDING_PROVIDER:", os.environ.get("EMBEDDING_PROVIDER"))
print("DEPLOYMENT:", os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT"))

for q in [
    "JWT decode and current user dependency",
    "how to enforce workspace membership before mutating a resource",
    "duplicate-name 409 conflict check on POST endpoint",
]:
    print(f"\n--- semantic_search: {q} ---")
    r = tool_map["semantic_search"].invoke({"query": q, "k": 3, "source": "reference"})
    if not r.get("ok"):
        print("ERROR:", r.get("error"))
    else:
        for h in r.get("hits", []):
            print(f"  {h['file']}:L{h['start_line']}  {h['snippet'][:90]!r}")
