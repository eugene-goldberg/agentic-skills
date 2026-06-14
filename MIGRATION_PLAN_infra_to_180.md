# Migration Plan — local infra → 192.168.12.180

> Goal: stand up the crew's Docker-backed retrieval/infra stack on the remote host
> **with all data** (vector store, graph store, target DB). Written 2026-06-12 from
> verified discovery on both hosts. **Plan + prep only — not yet executed.**

## Verified discovery

### Remote (192.168.12.180) — ready
- **x86_64**, Ubuntu 20.04.5, **Docker 20.10.23 + Compose v2.15.1**, `docker` usable
  **without sudo** (user in `docker` group). 12 CPU / 62 GiB RAM (58 free) / **717 GB
  free disk**. Passwordless SSH as `user@` via `~/.ssh/id_ed25519_18012` is LIVE.
- **Ollama + `bge-m3:latest` ALREADY installed** (same model id `790764642607`) →
  **embeddings need NO migration.**

### Local stores to migrate
| Store | What it is | Location | Size | Notes |
|---|---|---|---|---|
| Milvus vector store | 160 collections (`hybrid_code_chunks_<hash>` per-target semantic indexes + `lessons_*`/`patterns_*`) | **bind-mounts** `/tmp/milvus/volumes/{etcd,minio,milvus}` | **2.5 GB** | `/tmp` is EPHEMERAL — at risk locally |
| Milvus config | `user.yaml` | `/tmp/milvus/user.yaml` | tiny | |
| Target DB | ecommerce Postgres | docker volume `ecommerce-pg-data` | 49 MB | `postgres:16` |
| Graph store | graphify AST caches (per-target `graph.json` etc.) | `~/.cache/agentic-skills/graphify/` | **682 MB** | native files, not Docker |
| Embeddings | Ollama `bge-m3` | `~/.ollama` | 1.2 GB | **SKIP — already on remote** |

### Images (the architecture constraint)
- Local is **arm64**, remote is **x86_64** → Docker **images cannot be copied across
  arch**. All three Milvus images (`milvusdb/milvus:v2.5.26`, `quay.io/coreos/etcd:v3.5.18`,
  `minio/minio:RELEASE.2024-05-28T17-19-04Z`) and `postgres:16` are **multi-arch** on
  the registry → the remote simply `docker pull`s the x86_64 variants (compose does this
  automatically). **Only DATA migrates.** Milvus/etcd/minio/pg on-disk formats are
  arch-agnostic → they restore cleanly on x86_64.

## What moves, how
| Component | Method | Downtime |
|---|---|---|
| Milvus images ×3 | `docker compose pull` on remote (auto) | none |
| **Milvus data (2.5 GB)** | **COLD copy**: stop local Milvus → `tar` the 3 bind-mount dirs → `scp` → untar on remote → start remote Milvus | local Milvus down during copy (~few min) |
| postgres:16 image | `docker pull` on remote | none |
| ecommerce-pg data (49 MB) | `pg_dump` local → `psql` restore remote (arch-clean; preferred over volume tar) | none (online dump) |
| graphify (682 MB) | `tar` → `scp` → untar to same `~/.cache/...` path on remote | none |
| Ollama/bge-m3 | **none** — present on remote | none |

## Procedure (cold, consistency-safe)
1. **Remote prep:** choose a **persistent** home (NOT `/tmp`) — recommend
   `~/agentic-infra/` (or `/opt/agentic-infra`). `mkdir -p`. Copy `ops/milvus/`
   (`docker-compose.yml` + `user.yaml`) there; set `DOCKER_VOLUME_DIRECTORY` to it.
2. **Quiesce:** ensure no live sprint is using local Milvus (⚠ the live-prove sprint
   `run-20260612T125029Z-99666a` is mid-run — see Timing). Stop local Milvus:
   `docker compose -f ops/milvus/docker-compose.yml down` (**no `-v`** — keep local data).
3. **Tar Milvus data:** `tar czf /tmp/milvus-data.tgz -C /tmp/milvus volumes user.yaml`.
4. **Transfer:** `scp /tmp/milvus-data.tgz user@192.168.12.180:~/agentic-infra/`.
5. **Restore + start remote:** untar so dirs land at `~/agentic-infra/volumes/{etcd,minio,milvus}`;
   `DOCKER_VOLUME_DIRECTORY=~/agentic-infra docker compose up -d`; wait `healthz` green.
6. **Restart local Milvus** (migration is a COPY, local stays intact for rollback).
7. **Postgres:** `pg_dump` from local `ecommerce-pg` → restore into a `postgres:16`
   container on remote (compose-managed); verify table row counts.
8. **graphify:** `tar` `~/.cache/agentic-skills/graphify` → `scp` → untar to the same
   path on remote (only required if the harness will RUN on the remote — see topology).
9. **Verify:** remote `pymilvus list_collections()` == **160**; spot-check a few collection
   `num_entities`; pg counts; graphify file count + a `graph.json` opens.
10. **Repoint** (topology-dependent — see Open Decisions).

## Open decisions (BLOCK execution — need operator)
1. **Topology / end-state — what runs where?**
   - **(A) Remote = infra only; harness stays local**, pointed at remote via
     `MILVUS_ADDRESS=192.168.12.180:19530` in `webapp/.env`. Then graphify does NOT move
     (harness reads it locally), Ollama stays local-or-remote. Smallest change. **But**
     minio/etcd are internal to Milvus — only `:19530` (+ maybe `:9091`) need exposing;
     remote firewall must allow the Mac to reach `:19530`.
   - **(B) Remote = full host; harness RUNS on remote too.** Then graphify moves, the
     repo + `.venv` + `webapp/.env` (with `OLLAMA_HOST=127.0.0.1:11434` → remote's own
     Ollama, `MILVUS_ADDRESS=localhost:19530`) deploy to remote, and the crew runs there.
     Bigger move; clean separation; remote's 12-core/62 GB is stronger than the Mac for
     concurrent agents.
2. **Timing vs the live-prove sprint.** The reviews chain live-prove is mid-run on **local**
   Milvus (already retrieval-degraded). Step 2 stops Milvus → kills/abandons that run.
   Options: (i) migrate AFTER the sprint finishes; (ii) accept ending it now.
3. **Persistent home confirmation:** `~/agentic-infra` on remote (vs `/opt`)? And FYI the
   **local** Milvus data being under `/tmp` is fragile — worth relocating locally too.

## Rollback
Migration is **additive** (copy, not move): local stack stays fully intact (no `-v`).
Revert = repoint `.env` back to local Milvus. No destructive step on the source.
