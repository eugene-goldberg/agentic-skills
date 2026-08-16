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
    const r = await fetch(`${this.host}/api/embed`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: this.modelName, input: text }),
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
  } else if (cmd.op === 'search') {
    result = await context.semanticSearch(cmd.repo, cmd.query, cmd.k || 5);
  } else if (cmd.op === 'search_multi') {
    // Cross-repo search: fan the same query across N already-indexed
    // collections, tag each hit with its repo, merge and rank globally.
    // Repos with no collection are skipped (reported in `skipped`) rather
    // than failing the call — a partially-indexed corpus still answers.
    // IMPORTANT (ranking correctness): we do NOT reuse
    // context.semanticSearch here. Its hybrid path returns Reciprocal Rank
    // Fusion scores computed INDEPENDENTLY per collection (k=100, so
    // 1/101, 2/101, 1/102...). Those encode rank-within-a-repo, not
    // relevance — merging them globally makes a rank-1 hit in a 6-chunk
    // repo tie a rank-1 hit in a 25k-chunk repo, so tiny repos dominate.
    // Instead: embed the query ONCE and dense-search every collection with
    // the same vector, which yields scores in one comparable space.
    // Trade-off: this arm is dense-only (no BM25 half), so exact-identifier
    // matching is weaker than single-repo semanticSearch. Documented, not
    // accidental.
    const repos = Array.isArray(cmd.repos) ? cmd.repos : [];
    const k = cmd.k || 5;
    const perRepo = cmd.per_repo_k || Math.max(k, 10);
    const hits = [];
    const skipped = [];
    const searched = [];
    const qv = (await embedding.embed(cmd.query)).vector;
    for (const repo of repos) {
      try {
        const collectionName = context.getCollectionName(repo);
        const exists = await vectorDatabase.hasCollection(collectionName);
        if (!exists) { skipped.push({ repo, reason: 'no_collection' }); continue; }
        const rs = await vectorDatabase.search(collectionName, qv, { topK: perRepo });
        searched.push(repo);
        const repoName = repo.split('/').filter(Boolean).pop();
        for (const h of (rs || [])) {
          const d = h.document || h;
          hits.push({
            relativePath: d.relativePath, startLine: d.startLine,
            endLine: d.endLine, content: d.content,
            fileExtension: d.fileExtension,
            score: h.score ?? h.distance ?? 0, repo, repoName,
          });
        }
      } catch (e) {
        skipped.push({ repo, reason: String(e?.message || e).slice(0, 200) });
      }
    }
    hits.sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
    // Diversity cap: without it the largest repo monopolizes the result set
    // (a 25k-chunk web client crowds out the 6-chunk service that actually
    // answers "which service does X?"). Greedy pass in score order keeps the
    // best hit per repo before allowing seconds. max_per_repo unset = no cap.
    let ranked = hits;
    if (cmd.max_per_repo) {
      const perRepoCount = {};
      const primary = [];
      const overflow = [];
      for (const h of hits) {
        const n = (perRepoCount[h.repoName] = (perRepoCount[h.repoName] || 0) + 1);
        (n <= cmd.max_per_repo ? primary : overflow).push(h);
      }
      // Backfill with overflow only if the cap starved us of k results.
      ranked = primary.concat(overflow);
    }
    result = { hits: ranked.slice(0, k), n_searched: searched.length,
               skipped, ranking: 'dense_cosine_shared_query_vector',
               max_per_repo: cmd.max_per_repo || null };
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
            idx = self.index(name)
            if not idx.get("ok"):
                return idx
        r = _run_bridge(self.node_dir, {"op": "search", "repo": str(repo), "query": query, "k": k})
        return r

    def search_multi(self, repos: list[Path], query: str, k: int = 5,
                     *, max_per_repo: int | None = None,
                     timeout: int | None = None) -> dict:
        """Cross-repo search over ALREADY-indexed collections.

        Deliberately does NOT index-on-miss the way `search` does: a
        corpus-wide search must never trigger a multi-hour indexing run as
        a side effect. Un-indexed repos come back in `skipped` so the
        caller can see what wasn't covered — silence about missing
        coverage would be a worse failure than a partial answer (I-5).
        """
        if not repos:
            return {"ok": False, "error": "no repos supplied", "result": {"hits": []}}
        cmd = {"op": "search_multi", "repos": [str(p) for p in repos],
               "query": query, "k": k}
        if max_per_repo:
            cmd["max_per_repo"] = int(max_per_repo)
        return _run_bridge(self.node_dir, cmd, timeout=timeout)
