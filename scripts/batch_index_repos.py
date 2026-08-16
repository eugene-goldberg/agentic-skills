#!/usr/bin/env python3
"""Batch semantic-index a directory of git repos into Milvus.

Drives the same `.spike-node/bridge.js` path the orchestrator uses at
`index_initial` — @zilliz/claude-context-core chunking, bge-m3 embeddings
via local Ollama, hybrid dense+BM25 collections in Milvus. Nothing leaves
the machine.

Resumable by design: the manifest records each repo's indexed HEAD sha, so
a re-run skips repos whose sha is unchanged and picks up where a crash or
Ctrl-C left off. Per-repo failures are isolated (one bad repo never aborts
the batch) and per-repo timeouts prevent a hang from stalling the queue.

Usage:
    python3 scripts/batch_index_repos.py --root ~/dev/ai-projects/ea-repos
    python3 scripts/batch_index_repos.py --root ... --force       # re-index all
    python3 scripts/batch_index_repos.py --root ... --only NAME   # single repo
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

AGENTIC_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_DIR = AGENTIC_ROOT / ".spike-node"
BRIDGE = BRIDGE_DIR / "bridge.js"

# Match the harness's own env contract (webapp/.env).
INDEX_ENV = {
    "EMBEDDING_PROVIDER": os.environ.get("EMBEDDING_PROVIDER", "Ollama"),
    "OLLAMA_HOST": os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
    "EMBEDDING_MODEL": os.environ.get("EMBEDDING_MODEL", "bge-m3"),
    "EMBEDDING_DIMENSION": os.environ.get("EMBEDDING_DIMENSION", "1024"),
    "MILVUS_ADDRESS": os.environ.get("MILVUS_ADDRESS", "localhost:19530"),
}
NODE_BIN_DIRS = [str(Path.home() / ".local" / "node" / "bin"), "/usr/local/bin", "/opt/homebrew/bin"]


def head_sha(repo: Path) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else None
    except (subprocess.SubprocessError, OSError):
        return None


def index_repo(repo: Path, timeout_s: int) -> dict:
    """Run the bridge against one repo. Returns a result record."""
    env = {**os.environ, **INDEX_ENV}
    env["PATH"] = os.pathsep.join(NODE_BIN_DIRS + [env.get("PATH", "")])
    cmd = ["node", str(BRIDGE), json.dumps({"op": "index", "repo": str(repo)})]
    started = time.time()
    try:
        proc = subprocess.run(cmd, cwd=str(BRIDGE_DIR), env=env,
                              capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout after {timeout_s}s",
                "duration_s": round(time.time() - started, 1)}
    except OSError as exc:
        return {"ok": False, "error": f"spawn failed: {exc}",
                "duration_s": round(time.time() - started, 1)}

    duration = round(time.time() - started, 1)
    # The bridge prints progress lines then a final JSON object.
    payload = None
    for line in reversed((proc.stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                payload = json.loads(line)
                break
            except ValueError:
                continue
    if payload is None:
        tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-400:]
        return {"ok": False, "error": f"no JSON result (exit={proc.returncode})",
                "tail": tail, "duration_s": duration}
    if not payload.get("ok"):
        return {"ok": False, "error": str(payload.get("error"))[:400],
                "duration_s": duration}
    res = payload.get("result") or {}
    return {"ok": True, "indexed_files": res.get("indexedFiles"),
            "total_chunks": res.get("totalChunks"),
            "status": res.get("status"), "duration_s": duration}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="directory containing git repos")
    ap.add_argument("--manifest", default=None, help="manifest path (default: <root>/.index-manifest.json)")
    ap.add_argument("--timeout", type=int, default=3600, help="per-repo timeout seconds")
    ap.add_argument("--force", action="store_true", help="re-index even if sha unchanged")
    ap.add_argument("--only", default=None, help="index just this repo name")
    args = ap.parse_args()

    root = Path(os.path.expanduser(args.root)).resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    if not BRIDGE.exists():
        print(f"error: bridge missing at {BRIDGE}", file=sys.stderr)
        return 2

    manifest_path = Path(args.manifest) if args.manifest else root / ".index-manifest.json"
    manifest: dict = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
        except ValueError:
            manifest = {}

    repos = sorted(p for p in root.iterdir() if (p / ".git").exists())
    if args.only:
        repos = [p for p in repos if p.name == args.only]
    if not repos:
        print("no git repos found", file=sys.stderr)
        return 2

    print(f"[batch] {len(repos)} repo(s) under {root}")
    print(f"[batch] provider={INDEX_ENV['EMBEDDING_PROVIDER']} "
          f"model={INDEX_ENV['EMBEDDING_MODEL']} dim={INDEX_ENV['EMBEDDING_DIMENSION']} "
          f"milvus={INDEX_ENV['MILVUS_ADDRESS']}")
    print(f"[batch] manifest={manifest_path}\n")

    t0 = time.time()
    done = skipped = failed = 0
    for i, repo in enumerate(repos, 1):
        sha = head_sha(repo)
        prior = manifest.get(repo.name) or {}
        if (not args.force and prior.get("ok") and sha and prior.get("sha") == sha):
            print(f"[{i}/{len(repos)}] {repo.name}: SKIP (unchanged @ {sha[:8]}, "
                  f"{prior.get('total_chunks')} chunks)")
            skipped += 1
            continue

        print(f"[{i}/{len(repos)}] {repo.name}: indexing @ {(sha or 'nosha')[:8]} ...", flush=True)
        rec = index_repo(repo, args.timeout)
        rec.update({"sha": sha, "at": datetime.now(timezone.utc).isoformat()})
        manifest[repo.name] = rec
        # Persist after EVERY repo so a crash resumes, never restarts.
        try:
            manifest_path.write_text(json.dumps(manifest, indent=2))
        except OSError as exc:
            print(f"    warn: manifest write failed: {exc}", file=sys.stderr)

        if rec["ok"]:
            done += 1
            print(f"    OK {rec['indexed_files']} files, {rec['total_chunks']} chunks "
                  f"in {rec['duration_s']}s")
        else:
            failed += 1
            print(f"    FAIL {rec['error']}")
            if rec.get("tail"):
                print(f"    tail: {rec['tail'][:200]}")

    elapsed = round(time.time() - t0, 1)
    total_chunks = sum((r.get("total_chunks") or 0) for r in manifest.values() if r.get("ok"))
    total_files = sum((r.get("indexed_files") or 0) for r in manifest.values() if r.get("ok"))
    print(f"\n[batch] done={done} skipped={skipped} failed={failed} in {elapsed}s")
    print(f"[batch] corpus: {total_files} files, {total_chunks} chunks across "
          f"{sum(1 for r in manifest.values() if r.get('ok'))} repo(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
