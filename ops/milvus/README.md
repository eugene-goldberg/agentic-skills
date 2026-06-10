# Local Milvus deployment (hardened)

The canonical, **persistent** copy of the local Milvus stack used for all retrieval
(claude-context semantic index + lessons/patterns collections). Previously this
lived only in volatile `/tmp/milvus`, whose `docker-compose.yml` got cleared mid-
session (the `volumes/` survived but the spec did not) — keep this repo copy as the
source of truth and re-seed `/tmp/milvus` from it.

## What's here
- `docker-compose.yml` — official Milvus **standalone** 3-container stack (etcd +
  minio + milvus-standalone, image `milvusdb/milvus:v2.5.26`), plus two A68
  hardening additions:
  - `restart: unless-stopped` on all three services (Docker auto-revives Milvus if
    it self-exits — complements the harness A68 restart in `projects.py`).
  - a `user.yaml` bind-mount into `/milvus/configs/user.yaml` on the standalone.
- `user.yaml` — Milvus config overlay that hardens it against **etcd session-lease
  loss under host resource contention** (the A68 root cause, run-…-27d128):
  `common.session.ttl 30→180`, `retryTimes 30→60`, `etcd.requestTimeout 10000→30000`.

## Bring it up (from this persistent copy)
```bash
mkdir -p /tmp/milvus
cp ops/milvus/docker-compose.yml ops/milvus/user.yaml /tmp/milvus/
cd /tmp/milvus && DOCKER_VOLUME_DIRECTORY=/tmp/milvus docker compose -p milvus up -d --pull never
# wait ~20s; verify:
curl -s http://127.0.0.1:9091/healthz   # → OK
```
`--pull never` matters: this Mac has hit Docker Hub-unreachable windows; all three
images are already local. If an image is genuinely missing, pull it when the hub is
reachable, then retry.

## Host sizing note (16 GB Mac)
Docker Desktop memory was reduced 12 GB → **8 GB** (`settings.json` `memoryMiB`) so
the host retains ~8 GB for the harness + `claude` subprocesses + Ollama + `dotnet`
builds. Over-allocating Docker on a 16 GB host caused the swap pressure that stalled
Milvus's etcd keepalive. The Milvus stack fits comfortably in 8 GB.

See `DESIGN_SHORTCOMINGS.md` A68.
