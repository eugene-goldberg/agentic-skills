---
name: arch-ea-destination
description: Operator directive 2026-08-16 — the 21 Sphera ea-repos are the real destination; template is only the proving ground. Readiness = the six-point E-1..E-6 gate in AUTONOMY_HARDENING_PLAN §9c.
metadata:
  type: project
---

Operator directive (2026-08-16): *"let me know when the plan is fully
executed and when we're ready to switch to work with the EA codebase
full time."* The 21 Sphera EA service repos under
`~/dev/ai-projects/ea-repos/` are the destination; the
`full-stack-fastapi-template` target exists only to prove the crew before
it touches corporate code.

**State:** EA involvement is embeddings ONLY — 21 Milvus collections /
53,609 chunks (`scripts/batch_index_repos.py`, manifest at
`ea-repos/.index-manifest.json`). No EA repo is exposed to the webapp, has
`.agentic-skills.json`, or has a gate script; `RETRIEVAL_CORPUS_ROOT` is
unset so agents cannot even read EA code. Verified 2026-08-16.

**Why the gate matters:** the hard blockers are NOT crew competence —
they're (a) a .NET/Azure-shaped regression gate that runs locally (C-0
needed 8 iterations on the stack the harness was *designed* for), (b) the
one-repo-per-sprint architecture vs EA features that span
gateway+service+web-client, and (c) the unsandboxed-Bash security posture
(D4) which is acceptable on a throwaway clone and a different
conversation on Sphera IP.

**How to apply:** do not point the crew at EA until E-1..E-6
(`AUTONOMY_HARDENING_PLAN.md` §9c) all hold. E-2/E-3 (pilot-repo
bootstrap + locally-runnable tests) are the long pole and can be built in
parallel with the C-4 sprint series. The cheap interim win is
`RETRIEVAL_CORPUS_ROOT` — agents ground in real EA conventions while
writing only to a sandbox target; needs one operator decision (whether
corpus hits count toward R5). See [[arch-autonomy-hardening]] for the
ladder and [[arch-active-branch]].
