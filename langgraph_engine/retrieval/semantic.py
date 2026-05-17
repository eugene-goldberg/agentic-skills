"""Semantic search client.

Wraps the claude-context-core Node library via a thin stdin/stdout subprocess
helper. Each call:
  1. spawns a short-lived Node process
  2. sends a JSON command on stdin (op=index | op=search)
  3. reads the JSON result from stdout

For higher throughput we can later swap this for an HTTP daemon; for now the
per-call cost (~1.5s warm node start) is negligible vs. LLM call latency.

Required env (loaded by orchestrator from .env.*):
  OPENAI_API_KEY      — embedding API key
  MILVUS_ADDRESS      — e.g. localhost:19530
  MILVUS_TOKEN        — empty for local Milvus

Override paths via env if needed:
  CLAUDE_CONTEXT_NODE_DIR  — directory containing node_modules with claude-context-core
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_NODE_DIR = Path(__file__).resolve().parents[2] / ".spike-node"
BRIDGE_SCRIPT_NAME = "bridge.js"
BRIDGE_SCRIPT = """\
import { Context, OpenAIEmbedding, MilvusVectorDatabase, Embedding } from '@zilliz/claude-context-core';
import { AzureOpenAI, OpenAI } from 'openai';

const cmd = JSON.parse(process.argv[2]);

class AzureEmbedding extends Embedding {
  constructor({ apiKey, endpoint, apiVersion, deployment, model, dimension }) {
    super();
    this.maxTokens = 8191;
    this.deployment = deployment;
    this.modelName = model || deployment;
    this.dimension = dimension || 3072;
    // baseURL: null prevents OpenAI SDK from auto-picking OPENAI_BASE_URL
    // (which may be set for a different chat provider like Moonshot).
    this.client = new AzureOpenAI({ apiKey, endpoint, apiVersion, deployment, baseURL: null });
  }
  async detectDimension() { return this.dimension; }
  async embed(text) {
    const t = this.preprocessText(text);
    const r = await this.client.embeddings.create({ model: this.deployment, input: t });
    return { vector: r.data[0].embedding, dimension: r.data[0].embedding.length };
  }
  async embedBatch(texts) {
    const ts = this.preprocessTexts(texts);
    const r = await this.client.embeddings.create({ model: this.deployment, input: ts });
    return r.data.map(d => ({ vector: d.embedding, dimension: d.embedding.length }));
  }
  getDimension() { return this.dimension; }
  getProvider() { return 'AzureOpenAI'; }
}

let embedding;
if (process.env.EMBEDDING_PROVIDER === 'AzureOpenAI') {
  embedding = new AzureEmbedding({
    apiKey: process.env.AZURE_OPENAI_API_KEY,
    endpoint: process.env.AZURE_OPENAI_ENDPOINT,
    apiVersion: process.env.AZURE_OPENAI_API_VERSION || '2024-12-01-preview',
    deployment: process.env.AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
    model: process.env.EMBEDDING_MODEL,
    dimension: parseInt(process.env.EMBEDDING_DIMENSION || '3072', 10),
  });
} else {
  embedding = new OpenAIEmbedding({
    apiKey: process.env.OPENAI_API_KEY,
    model: process.env.EMBEDDING_MODEL || 'text-embedding-3-small',
  });
}

const vectorDatabase = new MilvusVectorDatabase({
  address: process.env.MILVUS_ADDRESS,
  token: process.env.MILVUS_TOKEN || '',
});
const context = new Context({ embedding, vectorDatabase });

try {
  let result;
  if (cmd.op === 'index') {
    result = await context.indexCodebase(cmd.repo, null, cmd.force === true);
  } else if (cmd.op === 'search') {
    result = await context.semanticSearch(cmd.repo, cmd.query, cmd.k || 5);
  } else {
    throw new Error('unknown op: ' + cmd.op);
  }
  process.stdout.write(JSON.stringify({ ok: true, result }));
} catch (e) {
  process.stdout.write(JSON.stringify({ ok: false, error: String(e?.message || e) }));
}
"""


def _ensure_bridge(node_dir: Path) -> Path:
    bridge = node_dir / BRIDGE_SCRIPT_NAME
    if not bridge.exists() or bridge.read_text() != BRIDGE_SCRIPT:
        bridge.write_text(BRIDGE_SCRIPT)
    return bridge


def _run_bridge(node_dir: Path, command: dict) -> dict:
    bridge = _ensure_bridge(node_dir)
    proc = subprocess.run(
        ["node", str(bridge), json.dumps(command)],
        cwd=node_dir,
        capture_output=True,
        text=True,
        timeout=600,
        env={**os.environ},
    )
    out = proc.stdout.strip()
    if not out:
        return {"ok": False, "error": f"empty stdout; stderr={proc.stderr[-400:]}"}
    try:
        return json.loads(out.splitlines()[-1])
    except json.JSONDecodeError:
        return {"ok": False, "error": f"non-json stdout: {out[-400:]}; stderr={proc.stderr[-400:]}"}


class SemanticRegistry:
    """Tracks which repos have been indexed during this run."""

    def __init__(self, node_dir: Path | None = None):
        self.node_dir = node_dir or DEFAULT_NODE_DIR
        self._paths: dict[str, Path] = {}
        self._indexed: set[str] = set()

    def register(self, name: str, repo_root: Path) -> None:
        self._paths[name] = repo_root

    def index(self, name: str, *, force: bool = False) -> dict:
        repo = self._paths[name]
        if name in self._indexed and not force:
            return {"ok": True, "cached": True}
        r = _run_bridge(self.node_dir, {"op": "index", "repo": str(repo), "force": force})
        if r.get("ok"):
            self._indexed.add(name)
        return r

    def search(self, name: str, query: str, k: int = 5) -> dict:
        repo = self._paths[name]
        if name not in self._indexed:
            idx = self.index(name)
            if not idx.get("ok"):
                return idx
        r = _run_bridge(self.node_dir, {"op": "search", "repo": str(repo), "query": query, "k": k})
        return r
