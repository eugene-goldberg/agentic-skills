---
name: feedback_remote_first_dev
description: BINDING workflow (operator 2026-06-14) — all crew/harness code is edited + tested on remote 192.168.12.180; synced remote→GitHub→Mac (never Mac→remote for code).
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 154fb558-ad8d-47e9-b9fa-cbac688b2031
---

**Operator directive 2026-06-14 (BINDING).** Reverses the prior Mac-first dev flow.

1. **Edit all crew/harness code directly on the remote `192.168.12.180`** (over SSH),
   NOT on the Mac. Scope = `webapp/`, `langgraph_engine/`, `skills/`, `rubrics/`, tests.
2. **Create + run all crew/harness tests on the remote venv**
   (`cd ~/dev/ai-projects/agentic-skills/webapp/backend && .venv/bin/python -m pytest
   tests/ -p no:cacheprovider`). A change is "tested" only when green ON THE REMOTE — the
   Mac is not an acceptable test host for crew/harness code.
3. **Sync remote → GitHub → Mac** (commit on remote → `git push origin` from remote → Mac
   `git pull`). Mac is a read-only mirror. The old Mac→bundle→remote flow is retired for code.

**Why:** the remote is the host that actually runs the crew; its env (Ubuntu x86_64, **git
2.25.1**, dotnet, Ollama, Milvus, Docker) is ground truth. Mac-first caused "passes here,
breaks there" — concretely surfaced 2026-06-14: ~22 harness tests use `git init -b main`
(needs git ≥2.28) → pass on Mac, FAIL on the remote's git 2.25.1. (My R21/Phase-2 code
itself was clean on both; the failures were purely the fixture-vs-git-version env gap.)

**Enabler (operator-gated):** the remote pushes via a dedicated deploy key
`~/.ssh/id_ed25519_ghdeploy` (repo `core.sshCommand` set, github.com in known_hosts). The
operator must add its PUBLIC half to the GitHub repo Deploy keys with **WRITE** access;
until then rule 3 is blocked and the interim is remote-commit→bundle→Mac-push.

**Tooling note:** the architect's Edit/Write target the Mac FS, so remote edits are applied
over SSH (whole-file for new files; uniqueness-checked python in-place replace for edits —
mirroring Edit's safety). Read remote file first → minimal change → run remote tests.
Documented in CLAUDE.md "Development workflow — REMOTE-FIRST". Relates to
[[arch_inventory_run_and_wave_proposal]], [[feedback_honest_verification]].
