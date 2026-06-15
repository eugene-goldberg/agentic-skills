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
import { Context, OpenAIEmbedding, MilvusVectorDatabase, Embedding, FileSynchronizer } from '@zilliz/claude-context-core';
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

class OllamaEmbedding extends Embedding {
  constructor({ host, model, dimension }) {
    super();
    this.host = (host || 'http://localhost:11434').replace(/\/+$/, '');
    this.modelName = model || 'bge-m3';
    this.dimension = dimension || 1024;
    this.maxTokens = 8192;
  }
  async detectDimension() { return this.dimension; }
  getDimension() { return this.dimension; }
  getProvider() { return 'Ollama'; }
  async _embedOne(text) {
    // input MUST be an array: Ollama's /api/embed HANGS on a bare-string input
    // (observed on Ollama 0.24.0 — single-string request never returns, which
    // wedged every semantic_search query embed → the crew grounded blind). The
    // array form returns normally. AbortSignal is defense-in-depth so a future
    // server stall can never again hang an agent indefinitely.
    const r = await fetch(`${this.host}/api/embed`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: this.modelName, input: [text] }),
      signal: AbortSignal.timeout(60000),
    });
    if (!r.ok) throw new Error(`Ollama /api/embed HTTP ${r.status}`);
    const j = await r.json();
    const v = (j.embeddings && j.embeddings[0]) || j.embedding;
    if (!v) throw new Error(`Ollama returned no embedding: ${JSON.stringify(j).slice(0,200)}`);
    return { vector: v, dimension: v.length };
  }
  async embed(text) {
    const t = this.preprocessText(text);
    return this._embedOne(t);
  }
  async embedBatch(texts) {
    const ts = this.preprocessTexts(texts);
    // Ollama /api/embed accepts an array via "input"
    const r = await fetch(`${this.host}/api/embed`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: this.modelName, input: ts }),
      signal: AbortSignal.timeout(120000),
    });
    if (!r.ok) throw new Error(`Ollama /api/embed HTTP ${r.status}`);
    const j = await r.json();
    const arr = j.embeddings || [];
    if (!arr.length) throw new Error(`Ollama returned no embeddings`);
    return arr.map(v => ({ vector: v, dimension: v.length }));
  }
}

let embedding;
const provider = (process.env.EMBEDDING_PROVIDER || '').toLowerCase();
if (provider === 'ollama') {
  embedding = new OllamaEmbedding({
    host: process.env.OLLAMA_HOST,
    model: process.env.EMBEDDING_MODEL || 'bge-m3',
    dimension: parseInt(process.env.EMBEDDING_DIMENSION || '1024', 10),
  });
} else if (provider === 'azureopenai') {
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
  } else if (cmd.op === 'index_baseline') {
    // Establish the merkle snapshot baseline FIRST (fast - hashing only, embeds
    // nothing) so a timeout during the subsequent full embed can NEVER lose it;
    // THEN full-embed the baseline. The indexer runs under a wall-clock timeout, so
    // doing the snapshot LAST (post-embed) silently dropped it whenever the embed
    // hit the cap, leaving op=reindex to see 0 changes and skip the wave's files
    // (observed live: run-...132221Z-e5aa54). Snapshot-first makes the wave delta
    // reliably indexed even when the baseline embed is truncated by the timeout
    // (baseline completeness under the cap is a separate, pre-existing concern).
    let snap = 'established_pre_embed';
    try {
      await FileSynchronizer.deleteSnapshot(cmd.repo);
      await context.reindexByChange(cmd.repo);
    } catch (e) { snap = 'snapshot_error: ' + String(e?.message || e); }
    result = await context.indexCodebase(cmd.repo, null, cmd.force === true);
    result = Object.assign({}, result, { snapshot: snap });
  } else if (cmd.op === 'reindex') {
    // Incremental: embed ONLY files changed since the snapshot baseline. Safety
    // fallback to a full index + baseline when the collection does not exist yet
    // (e.g. index_initial skipped/failed) so the index is never silently empty.
    const collectionName = context.getCollectionName(cmd.repo);
    let exists = false;
    try { exists = await vectorDatabase.hasCollection(collectionName); } catch (_) { exists = false; }
    if (!exists) {
      result = await context.indexCodebase(cmd.repo, null, false);
      try { await FileSynchronizer.deleteSnapshot(cmd.repo); await context.reindexByChange(cmd.repo); } catch (_) {}
      result = Object.assign({}, result, { fallback: 'full_index_no_collection' });
    } else {
      result = await context.reindexByChange(cmd.repo);
    }
  } else if (cmd.op === 'search') {
    result = await context.semanticSearch(cmd.repo, cmd.query, cmd.k || 5);
  } else if (cmd.op === 'has_index') {
    // Fast check: does the Milvus collection for this repo already have
    // rows? Used by SemanticRegistry to skip re-indexing across MCP-server
    // restarts when the index is already populated. Avoids the 120s
    // indexCodebase no-op penalty.
    const collectionName = context.getCollectionName(cmd.repo);
    let count = 0;
    let exists = false;
    try {
      exists = await vectorDatabase.hasCollection(collectionName);
      if (exists) {
        try {
          count = await vectorDatabase.query(collectionName, '', ['id'], 1).then(r => (r && r.length) ? 1 : 0);
        } catch (_) { count = exists ? 1 : 0; }
      }
    } catch (_) {
      exists = false;
    }
    result = { collection: collectionName, exists, has_rows: count > 0 };
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


def _run_bridge(node_dir: Path, command: dict, *, timeout: int | None = None) -> dict:
    """Spawn the Node bridge synchronously, with a hard wall-clock timeout.

    Defaults match the `webapp` branch baseline that the operator confirmed
    works reliably for indexing + search. Azure embedding latency varies a
    lot (~5s when warm, ~30s after a sustained burst); the subprocess
    timeout has to exceed the OpenAI SDK's internal request timeout (which
    claude-context-core wraps as 'Request timed out.') AND leave headroom
    for Node startup. Tight per-op timeouts would convert slow-but-working
    Azure responses into hard failures, which is what we saw on this branch
    before this fix.
    """
    bridge = _ensure_bridge(node_dir)
    if timeout is None:
        timeout = 900 if command.get("op") == "index" else 600
    try:
        proc = subprocess.run(
            ["node", str(bridge), json.dumps(command)],
            cwd=node_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ},
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "error": f"node bridge timed out after {timeout}s during op={command.get('op')!r}",
            "timeout": True,
            "stderr": (exc.stderr or b"").decode(errors="replace")[-400:] if isinstance(exc.stderr, (bytes, bytearray)) else (exc.stderr or "")[-400:],
        }
    out = proc.stdout.strip()
    if not out:
        return {"ok": False, "error": f"empty stdout; stderr={proc.stderr[-400:]}"}
    try:
        return json.loads(out.splitlines()[-1])
    except json.JSONDecodeError:
        return {"ok": False, "error": f"non-json stdout: {out[-400:]}; stderr={proc.stderr[-400:]}"}


class SemanticRegistry:
    """Tracks which repos have been indexed during this run.

    Records failed-index attempts too — so a slow first index does not put us
    in a loop of re-indexing on every subsequent search call.
    """

    def __init__(self, node_dir: Path | None = None):
        self.node_dir = node_dir or DEFAULT_NODE_DIR
        self._paths: dict[str, Path] = {}
        self._indexed: set[str] = set()
        self._index_failed: dict[str, dict] = {}

    def register(self, name: str, repo_root: Path) -> None:
        self._paths[name] = repo_root

    def index(self, name: str, *, force: bool = False) -> dict:
        repo = self._paths[name]
        if name in self._indexed and not force:
            return {"ok": True, "cached": True}
        if name in self._index_failed and not force:
            return {**self._index_failed[name], "cached_failure": True}
        r = _run_bridge(self.node_dir, {"op": "index", "repo": str(repo), "force": force})
        if r.get("ok"):
            self._indexed.add(name)
            self._index_failed.pop(name, None)
        else:
            self._index_failed[name] = r
        return r

    def search(self, name: str, query: str, k: int = 5) -> dict:
        """Search the indexed collection. Falls back to indexing if needed.

        Restores the `webapp` branch behavior: on first call for a given
        name in this process, attempt an `op=index` (force=false). If the
        collection already exists in Milvus, `indexCodebase` is a quick
        manifest-load no-op; if it doesn't, we trigger a full indexing run.
        Either way, the search that follows is against a populated
        collection. Subsequent calls in the same process skip this thanks
        to the `_indexed` cache.
        """
        repo = self._paths[name]
        if name not in self._indexed:
            # Short-circuit: if the Milvus collection for this repo already has
            # rows (built by index_initial or a prior run), skip the blocking
            # op=index. A full re-index of a large repo on CPU-only embeddings
            # can exceed the 900s op=index timeout, which would make *every*
            # search fail (the search wrapper returns the index error without
            # ever querying). Query what is already indexed instead. The
            # `has_index` bridge op exists for exactly this; previously it was
            # never wired into the Python search path.
            hi = _run_bridge(self.node_dir, {"op": "has_index", "repo": str(repo)})
            if hi.get("ok") and hi.get("result", {}).get("has_rows"):
                self._indexed.add(name)
            else:
                idx = self.index(name)
                if not idx.get("ok"):
                    return idx
        r = _run_bridge(self.node_dir, {"op": "search", "repo": str(repo), "query": query, "k": k})
        return r
