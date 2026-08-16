---
name: arch-active-branch
description: Active work branch is autonomy-hardening (Batches 0-7 ALL shipped, 291/291); parent architect-prereqs holds ABL-0015 flag-OFF awaiting Batch E
metadata:
  type: project
---

Active branch: **`autonomy-hardening`** (created 2026-08-15 off
`architect-prereqs` @ `8745331`). Batches 0–4 of
AUTONOMY_HARDENING_PLAN.md shipped (commits 5b3b31f, f333e20, 1868229,
9728f0a, f2ab112, f5ab92c, 9e33cfc, 855f62b — Batches 0–7 ALL
shipped); suite 291/291.

**Why:** the 2026-08-15 audit ([[arch-autonomy-hardening]]) showed the
mission-blockers lived in the harness control flow, not the worker
cell; this branch is the fix line.

**How to apply:** new work lands here. Parent branch architect-prereqs
still carries ABL-0015 auto-dispatch flag-OFF (Batch E live smoke
operator-gated, and its Journey 03 test finding lived on the target
checkout lost in the machine migration — restore first). Environment:
/Users/egoldberg migration left brownfield targets, Milvus, Ollama
missing (tracker 0-3/0-4); venv is uv-managed 3.12 at
webapp/backend/.venv.
