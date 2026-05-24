# Sprint Briefs — TRANSITIONAL LOCATION (will be removed)

> **This directory is the *wrong* location for sprint briefs.** Operator
> flagged the mis-placement 2026-05-24 mid-RBAC-sprint. See A17 in
> [`../DESIGN_SHORTCOMINGS.md`](../DESIGN_SHORTCOMINGS.md) for the full
> correction.

## Canonical location (going forward)

Sprint briefs describe features being added to a **brownfield target
repo**, not to agentic-skills itself. They belong with the target's
other brownfield artifacts (`BACKLOG.md`, per-BL `codebase_context.md`,
etc.):

```
<target-repo>/                          ← e.g. full-stack-fastapi-template
  _brownfield/
    sprint_briefs/                      ← THE canonical location
      <run_id>-<project-slug>.md        ← one file per sprint
    _codebase_context/
      CODEBASE_CONTEXT.md
    BL-XXXX/
      codebase_context.md
      eng_patterns.md
      qa_impact.md
    SPRINT_PLAN_C1.md
```

`agentic-skills` holds doctrine, ledger, invariants, R-rules, and
framework code only. It must not hold target-level feature intent —
that conflates two different governance scopes.

## Files currently in this directory

Two pre-correction backfills remain here as transitional records:

- `run-20260524T014937Z-e74aff-api-keys-feature.md`
- `run-20260524T144409Z-90e234-rbac-feature.md`

These will be migrated to
`<full-stack-fastapi-template>/_brownfield/sprint_briefs/` and this
directory will be deleted **after the currently-running RBAC sprint
(run_id `run-20260524T144409Z-90e234`) completes** — moving target-side
files mid-sprint would force A1 auto-rebase on every running gate and
waste agent budget.

## Implementation reference

Brief-persistence helpers (`_slugify`, `_persist_brief_in_worktree`)
live in `webapp/backend/app/services/orchestrator.py`. They are invoked
from `_po_flow` after worktree creation, before the PO subprocess
spawns. The brief lands in the worktree at
`<wt>/<art>/sprint_briefs/<run_id>-<slug>.md`. The existing PO
copy-back + `git add <art>` flow then carries it onto the target's
`agent_branch`. No code in agentic-skills writes to disk under this
directory anymore.
