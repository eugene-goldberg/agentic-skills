# Sprint pre-flight checklist

> Run this before every `/run-brief` or sprint resume. Drafted
> 2026-06-02 after a session that lost ~2h to skipping these checks
> and trusting "stuff was working last time" assumptions.

Per `CLAUDE.md` Rule 6: **95% verified-tested certainty floor**. Each
check below is a verifiable artifact — not "I assume X is running."

## PF-1 — Docker storage budget

```bash
docker system df
ls -lh ~/Library/Containers/com.docker.docker/Data/vms/0/data/Docker.raw
df -h "$HOME"
```

PASS when:
- `Docker.raw` allocated size noted (default ~60 GB cap; see `arch_disk_leak_fixes.md`)
- Host disk free ≥ A48 floor (default 5 GB + ~1 GB × n_bls)
- `docker system df` images + volumes total NOT close to the cap

If images > 20 GB or build cache > 5 GB and you're about to run a sprint, prune first.

## PF-2 — Milvus stack (3 containers)

```bash
docker ps --filter "name=milvus" --format "{{.Names}}: {{.Status}}"
python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',19530)); print('19530 ok')"
curl -s http://127.0.0.1:9091/healthz
```

PASS when:
- `milvus-standalone` shows `(healthy)`
- `milvus-etcd` shows `(healthy)`
- `milvus-minio` may show `(unhealthy)` — this is a healthcheck-cmd defect, not real (see `local_milvus.md`); verify functional via `curl http://127.0.0.1:9000/minio/health/live` returning `200`
- 19530 socket connects
- 9091 `/healthz` returns `OK`

If down: see `local_milvus.md` "How to bring it back up". **DO NOT use the embedded single-container variant on arm64 — it segfaults.**

## PF-3 — Ollama + bge-m3 + embedding probe

```bash
curl -s http://127.0.0.1:11434/api/tags
curl -s -X POST http://127.0.0.1:11434/api/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model":"bge-m3","prompt":"hello"}'
```

PASS when:
- `/api/tags` lists `bge-m3:latest`
- embedding probe returns a 1024-dim vector

If Ollama down: `brew services start ollama`.

## PF-4 — Uvicorn + all 4 A48 leak-fixes loaded

```bash
ps aux | grep "uvicorn app" | grep -v grep
curl -s http://127.0.0.1:8000/api/health
```

Then verify the four fixes are importable:
```bash
cd webapp/backend && .venv/bin/python -c "
from app.services.git_worktree import _reap_worktree_compose_stacks, remove_worktree
from app.main import _reap_orchestrator_compose_stacks, _ORCHESTRATOR_PROJECT_PATTERNS
from app.services.volume_reaper import _PROJECT_NAME_RE
from app.services import orchestrator as o
import inspect
assert '.lower()' in inspect.getsource(o._acceptance_flow), 'Fix #1 lowercase missing'
print('all 4 A48 fixes loaded:', _ORCHESTRATOR_PROJECT_PATTERNS)
"
```

PASS when uvicorn process is alive AND the import check confirms all four fixes are loaded AND `/api/health` returns `200`.

## PF-5 — claude binary + indexer end-to-end

```bash
which claude && claude --version
cd .spike-node
EMBEDDING_PROVIDER=Ollama OLLAMA_HOST=http://127.0.0.1:11434 \
EMBEDDING_MODEL=bge-m3 EMBEDDING_DIMENSION=1024 \
MILVUS_ADDRESS=localhost:19530 \
  node bridge.js '{"op":"index","repo":"<target_repo_path>"}'
```

PASS when:
- claude binary present and version reports
- bridge.js exits 0 with final JSON `{"ok":true,"result":{...}}`
- Final line includes `indexedFiles` and `totalChunks`

This is the single most-skipped check. If it fails, the orchestrator will run but agents will get empty retrieval → R5 grounding-floor failures.

## PF-6 — Target tree state

```bash
cd <target_repo>
git status -s
git branch --show-current
git rev-parse --short HEAD
```

PASS when:
- working tree clean (no unexpected modified files)
- on the expected `agent_branch` per `.agentic-skills.json`
- HEAD at the expected commit per `CONTINUATION_PROMPT.md`

Untracked `_brownfield/features/*/acceptance/` is normal (acceptance output) — stash if init-feature is needed.

## PF-7 — No leaked worktrees

```bash
git worktree list
```

PASS when ONLY the main checkout remains. Reap stragglers:
```bash
git worktree remove --force .agent-worktrees/<hash>
git worktree remove --force .gate-worktrees/<hash>
git worktree prune
```

## PF-8 — Backend test suite

```bash
cd webapp/backend && .venv/bin/python -m pytest tests/ 2>&1 | tail -3
```

PASS when N/N passes (expect ≥291 as of 2026-08-16).

## PF-9 — Docker leak watch

```bash
docker ps --format "{{.Names}}" | grep -iE "post-|pre-|fastapi|playwright|gate|acceptance|<sprint-task-id>"
```

PASS when **0 leftover gate or acceptance containers** before a fresh sprint launch.

## PF-10 — Sprint-resume prerequisites (if skip_po=True)

```bash
cd <target_repo>
ls _brownfield/features/<slug>/BACKLOG.md _brownfield/features/<slug>/brief.md
ls scripts/regression_gate.sh compose.gate.yml .agentic-skills.json
```

PASS when all four files present. Also verify `scripts/regression_gate.sh`
is the 2026-08-16 re-authored version (health-wait budget + playwright
base-url env + A32 per-test timeout):
```bash
grep -E "seq 1 60|PLAYWRIGHT_BASE_URL|--timeout=120" scripts/regression_gate.sh compose.gate.yml
```
*(Historical note: the pre-migration gate used `PLAYWRIGHT_TEST_BASE_URL`;
the re-authored gate follows the current upstream template's
`PLAYWRIGHT_BASE_URL` via compose.gate.yml.)*

## When PASS

All 10 green = safe to relaunch. Otherwise resolve the specific failure first; **do not rely on "things mostly look OK."**
