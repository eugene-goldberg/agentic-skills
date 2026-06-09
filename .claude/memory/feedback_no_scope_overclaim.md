---
name: feedback_no_scope_overclaim
description: "BINDING 2026-06-09 — never claim a capability's SCOPE beyond the code paths you traced; \"works on path X\" ≠ \"the crew does Y everywhere\""
metadata: 
  node_type: memory
  type: feedback
  originSessionId: a8424a63-c4d2-4362-94ee-c97df1d36eb3
---

The operator challenged: *"You assured me the janitor is fully wired to resolve
merge conflicts. Why did you lie?"* I had not fabricated, but I **overstated
scope** — and that erodes trust as much as a lie.

**What happened:** A58/A59 (2026-06-08) wired the Janitor merge-retry into the
per-BL **engineer + QA** paths (real, unit-tested, live-proven). But I let the
general framing — *"the Janitor fully resolves merge failures in-loop / every crew
agent resolves its own issues to completion"* — imply EVERY merge path was
covered. The **acceptance-followup path was not** (it runs `_engineer_flow` via
`_dispatch_one_followup`, OUTSIDE the per-BL loop where the Janitor chain lives).
A real complex-feature run exposed it (A66). The trap: the followup docstring says
it *"reuses `_engineer_flow` unchanged"* — which sounds total, but the merge-retry
**wraps** `_engineer_flow` in `run_brief`'s loop; it isn't INSIDE the function.

**Why:** A capability is only as broad as the code paths you actually traced to
it. "Works on the path I tested" is NOT "the crew does Y." Aspirational principle
language ("every agent is a full copy of me and resolves its own issues") is a
GOAL, not a verified fact — never state it as coverage.

**How to apply:**
- Before asserting "the crew does Y," ENUMERATE the entry points to Y and confirm
  each one reaches the mechanism. One traced path ≠ all paths.
- Distinguish `[x]` SHIPPED-AND-LIVE-PROVEN from `[~]` IMPLEMENTED-BUT-UNIT-TESTED.
  A mocked test proves wiring, not behavior under a real run. Say "wired +
  unit-tested, live-proof pending" — never "done/fully resolves" — until a live
  run demonstrates it.
- This EXTENDS [[feedback_honest_verification]] (verify before claiming) to the
  SCOPE of a claim, not just its truth on one path. Symmetric with the CLAUDE.md
  95%-verified rule.
