---
name: doctrine-validator-pattern
description: Hard pre-merge enforcement — webapp refuses to copy-back or fast-forward when doctrine artifacts are missing
metadata:
  type: project
---

**Rule:** On the brownfield-production branch, every PO / Engineer / QA
agent run is checked by `app/services/doctrine_validator.py` AFTER the
agent's first commit. If any required artifact is missing or under 120
bytes, the webapp:

1. Streams `_meta phase=doctrine_check kind=incomplete` to the UI with
   the missing path list.
2. Re-invokes the same agent in the same worktree with
   `build_fix_prompt(role, validation)` — a delta prompt that enumerates
   the missing paths and orders `git commit --amend --no-edit`.
3. Retries up to **2 times** (`MAX_FIX_RETRIES`).
4. Refuses the copy-back (PO) or fast-forward (Engineer/QA) if validation
   never passes. Surfaces `phase=awaiting_review reason="doctrine incomplete"`.

**Why:** The PO prompt's "Halt conditions" wording isn't self-enforcing —
the model commits anyway if not blocked by tooling. The validator turns
doctrine from aspirational into binding.

**How to apply:** When extending the brownfield skill set to a new role
or adding new artifact requirements, update `doctrine_validator.py`'s
`validate_<role>` to assert the new paths exist. The router code already
calls the validator generically.

**Force-merge override:** For cases where a gate or validator is wrong
about a particular run, `POST /api/projects/<repo>/merge-branch` with
`{"branch":"agent/<id>","skip_gate":true}` performs the FF merge anyway.
Same endpoint with `skip_gate:false` re-runs the gate. UI surfaces these
as "Review & merge (re-run gate)" and "Force merge (skip gate)" buttons
on Engineer/QA done cards when the gate was red.
