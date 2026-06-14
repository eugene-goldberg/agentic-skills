---
name: feedback_baseline_auth_inscope
description: "Operator decision 2026-06-13 — a feature crew MAY surgically fix a genuine blocking baseline defect (incl. baseline auth) that makes the feature undeliverable, even when the brief said \"do not touch X\"."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 154fb558-ad8d-47e9-b9fa-cbac688b2031
---

**Operator decision 2026-06-13 (BINDING).** During the ecommerce-reviews
live-acceptance convergence proof, the crew's fixer modified BASELINE auth
(`Program.cs` + new `JwtBearerConfiguration.cs`) to assign the missing JWT
`ValidAudience` — even though the brief explicitly said "do NOT modify auth."
The baseline app had `ValidateAudience=true` with no `ValidAudience` → IDX10208
→ 401 on every authenticated request → the feature's core (authed review submit)
was impossible to deliver. Asked whether to approve or require escalation, the
operator chose: **"Approve as in-scope."**

**Why:** "preserve the baseline exactly" and "deliver the feature" genuinely
conflict when the baseline is broken in a way that BLOCKS the feature. A feature
crew repairing a genuine, blocking baseline defect with a minimal, surgical,
behavior-preserving fix is acceptable — preferred over escalating and stalling
the whole feature. The bar: the defect must actually block the feature, the fix
must be minimal/surgical (here: assign one missing field, sourced from the same
`Jwt:Audience` login already mints with), and it must be honestly surfaced (it
was — flagged as the open scope item; the operator approved explicitly).

**How to apply:** when a crew fix touches a "do-not-touch" baseline area,
(1) verify the change is a genuine blocking defect, not a convenience or a
refactor; (2) confirm it's minimal and behavior-preserving; (3) SURFACE it to
the operator as an explicit scope decision (never self-approve, never bury it) —
this is the architect's "propose; operator approves" boundary. Do not over-rotate
into "baseline auth is always off-limits": the answer here was approve, not
reject. Relates to [[arch_live_acceptance_loop]], [[feedback_no_abort_persistence]]
(don't stall the feature), and the zero-false-merge discipline of
[[arch_zero_escape_chain]] (the fix still cleared the full doctrine+gate+merge bar).
