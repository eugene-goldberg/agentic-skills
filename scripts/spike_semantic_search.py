"""Spike: minimal semantic search over the reference repo.

Stand-in for claude-context-mcp (deferred to Phase 1 — needs npm + Milvus).
Validates the tool surface: semantic_search(query, k) -> [{file, snippet, score}].
"""
import os
import json
import re
from pathlib import Path
import numpy as np
from openai import OpenAI

REF = Path("/Users/eugenegoldberg/dev/ai-projects/agentic-skills/reference-repos/fastapi-good-patterns")
CACHE = REF / "graphify-out" / "semantic_cache.json"

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def chunk_file(path: Path, max_lines: int = 30):
    """Naive chunker: split Python files by top-level def/class with surrounding lines."""
    text = path.read_text()
    lines = text.splitlines()
    chunks = []
    cur_start = 0
    for i, line in enumerate(lines):
        if re.match(r"^(def |class |@)", line) and i - cur_start > 1:
            chunks.append((cur_start + 1, "\n".join(lines[cur_start:i])))
            cur_start = i
    chunks.append((cur_start + 1, "\n".join(lines[cur_start:])))
    return [(start, body) for start, body in chunks if body.strip()]


def build_index():
    if CACHE.exists():
        return json.loads(CACHE.read_text())
    items = []
    for py in REF.glob("**/*.py"):
        if ".venv" in py.parts or "__pycache__" in py.parts:
            continue
        rel = str(py.relative_to(REF))
        for start, body in chunk_file(py):
            items.append({"file": rel, "line": start, "text": body[:1500]})
    print(f"embedding {len(items)} chunks ...")
    texts = [it["text"] for it in items]
    r = client.embeddings.create(model="text-embedding-3-small", input=texts)
    for it, e in zip(items, r.data):
        it["vec"] = e.embedding
    CACHE.write_text(json.dumps(items))
    return items


def search(items, query, k=5):
    qvec = np.array(client.embeddings.create(model="text-embedding-3-small", input=[query]).data[0].embedding)
    mat = np.array([it["vec"] for it in items])
    sims = mat @ qvec / (np.linalg.norm(mat, axis=1) * np.linalg.norm(qvec) + 1e-9)
    top = np.argsort(-sims)[:k]
    return [(float(sims[i]), items[i]) for i in top]


if __name__ == "__main__":
    items = build_index()
    print(f"index size: {len(items)} chunks\n")
    for q in [
        "how to enforce workspace membership before mutating a resource",
        "JWT decode and current user dependency",
        "duplicate-name 409 conflict check on POST endpoint",
    ]:
        print("=" * 60)
        print(f"Q: {q}")
        print("=" * 60)
        for score, it in search(items, q, k=3):
            snippet = it["text"][:120].replace("\n", " ")
            print(f"  [{score:.3f}]  {it['file']}:L{it['line']:<3}  {snippet}...")
        print()
