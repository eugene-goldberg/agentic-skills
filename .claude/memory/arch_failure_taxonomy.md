---
name: arch-failure-taxonomy
description: I-6 — every shortcoming is classified into one of 10 classes; class informs fix shape; >3 instances in a class triggers architectural review
metadata:
  type: project
---

Failure classes (initial set, may grow):
- **race** — two concurrent actors mutate shared state (A1, B2, B9)
- **resource-leak** — a resource lives past intended scope (B1, A9-candidate, orphan docker containers)
- **silent-failure** — a step failed but reported success (A2, A5, B12)
- **silent-success** — a step succeeded by accident; system can't tell (A8)
- **consistency-violation** — cross-component invariant broken (I-3 violations, I-4 mismatches)
- **enforcement-gap** — documented rule has no enforcing code (A8)
- **starvation** — process never makes progress (B5)
- **data-loss** — intended-to-persist artifact destroyed (B18, B15)
- **observability-gap** — real event happened but produced no record (A6, B14, B15)
- **scope-creep** — component's responsibility expanded silently (B3, B16)

**Why:** A flat list of 25 shortcomings is hard to triage; a class taxonomy lets the doctrine-meta agent (Batch B) auto-tag findings and lets us see when ONE class has many instances — that's the signal to tighten an invariant, not patch each instance.

**How to apply:**
- Every new DESIGN_SHORTCOMINGS.md entry gets a `class:` field at the top.
- When a class crosses 3 instances, write an architectural pass that tightens the relevant invariant. (Current candidates: resource-leak is at 3+ instances → I-1 needs the `ManagedSubprocess` primitive; silent-failure is at 3+ → I-5 outcomes are now safer post-A5 but watch for new aggregate-label sites.)
- The doctrine-meta agent reads existing classifications to learn patterns; new findings get auto-tagged on first draft.

Source: `ARCHITECTURE_INVARIANTS.md` § I-6.
