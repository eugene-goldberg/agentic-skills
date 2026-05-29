# Project Evaluation — 2026-05-28

> Architect's objective assessment of agentic-skills against the thesis's
> own definition-of-done. Grounded in primary sources: `THESIS.md` (§3
> done-conditions, §7 success metric), `DESIGN_SHORTCOMINGS.md` (full
> ledger A1–A43), `ARCHITECT_PLAN.md` + `ARCHITECT_TRACKER.md` (Batches
> A–D), `ARCHITECTURE_INVARIANTS.md` (I-1..I-7, the I-2 R-rule table),
> `BACKLOG.md` (13 ABLs), and autonomy evidence across four real sprints
> (documents_1/2/3 + intelligent_kanban).
>
> Method: five parallel read-only investigations, synthesized against the
> thesis bar. Distinguishes "documented as done" from "verified working,"
> and "operator launched then walked away" (thesis-good) from "operator
> rescued mid-sprint" (gap).

---

## Bottom line

**The crew's worker-loop is real and working; the crew's *brain* is mostly
not built yet.** The project's own self-assessment (~40% of thesis
operational) is approximately correct and, if anything, slightly generous.
What exists is solid and the trajectory is genuinely good. But the actual
thesis — point it at a *never-seen* repo, hand it a requirement, walk away,
return to a shipped feature — is **not yet true for a fresh, large
feature**, and the gap is concentrated in exactly the components that
remove the human: Triage, Escalation, cross-project memory, and the
always-on observer.

---

## Scorecard — the four crew properties + the delivery bar

| Property | State | Evidence / Gap |
|---|---|---|
| **Grounded** | ✅ Strong | R5 (≥3 retrieval), R8 (budget ceiling), Tier-1.5 (pre-modification kill) enforced at streaming. Live proof: BL-0003 QA did 4 grounded calls before touching code. **Hole:** R9 (≥1 graph_* call) has enforcement point literally `none` (A8) — graph-grounding is advisory. A36: grounding meets the *count* floor but not *layer coverage*, silently producing gate failures. Grounded-by-count, not yet grounded-by-breadth. |
| **Self-correcting** | ⚠️ Half | Retry loops (R10/R10.1/R10.2) demonstrably work — BL-0005 regressed twice then recovered to green; BL-0003 took one doctrine retry. But this is *hardcoded retry*, not the **Triage agent (ABL-0002)** that decides retry-vs-rewrite-vs-defer-vs-split-vs-escalate. The "an *agent* decides" property holds only for transient/mechanical failures. A BL the retry loop can't resolve still falls to the operator. |
| **Honest** | ⚠️→✅ Medium, improving fastest | Honesty machinery is the most alive part: brownfield rubric forces a Fail on any axis ≤2; operator-gated review caught the meta-agent's false-evidence proposal (A43). But honesty had real bugs at the orchestrator level: A37 (QA-merge failure silently swallowed — sprint reported success while losing QA tests) and A34 (SSE disconnect kills run silently) are I-5/I-3 violations. Both now have fixes shipped. Honesty is enforced where instrumented; the silent-degradation class is being closed. |
| **Cumulative** | 🔴 Weakest — barely operational as a *crew* capability | Cross-project memory (ABL-0007) **not built**. Retrospective agent (ABL-0009) **not built**. The `.claude/memory/` + claude-mem store is the *architect's* session memory, not the *crew's* cross-target learning. The one cumulative mechanism partly built — doctrine-meta proposing rules — is gated and **not yet trustworthy** (A41, A43). "What's learned on one target carries to the next" is currently carried by the architect + the ledger, by hand. |

**Delivery bar (§7: operator-time < 1 hr on a repo the team has never
seen):** ❌ Not met, and not yet measurable. Recent sprints all ran on
`full-stack-fastapi-template` — a repo the crew has now seen repeatedly.
Operator still authors REQUIREMENTS.md, launches `/run-brief`, and approves
doctrine. Wall-clock is 2.5–7h. The "never-seen repo" condition has not
been tested at all.

---

## Capability coverage — the structural truth

### ABLs: ~2.5 of 13 built

| ABL | Sprint | Title | Actual state |
|---|---|---|---|
| ABL-0001 | 2 | Orchestrator | ✅ DONE — runs every sprint |
| ABL-0002 | 2 | **Triage agent** | 🔴 NOT BUILT — biggest autonomy gap |
| ABL-0003 | 2 | Doctrine meta-agent | ✅ DONE, with open honesty gaps (A41, A43) |
| ABL-0004 | 2 | **Escalation Bridge** | 🔴 NOT BUILT |
| ABL-0005 | 2 | Retire chain launchers | ⚠️ Partial |
| ABL-0006 | 3 | Sprint Planner (PO-from-spec) | 🔴 NOT BUILT |
| ABL-0007 | 3 | Cross-project memory layer | 🔴 NOT BUILT |
| ABL-0008 | 3 | Requirements-doc ingester | 🔴 NOT BUILT |
| ABL-0009 | 4 | Retrospective agent | 🔴 NOT BUILT |
| ABL-0010 | 4 | Meta-rubric (scores the process) | 🔴 NOT BUILT |
| ABL-0011 | 5 | Concurrent BL execution | 🔴 NOT BUILT |
| ABL-0012 | 5 | Multi-target operations | 🔴 NOT BUILT |
| ABL-0013 | 5 | Cost + telemetry layer | 🔴 NOT BUILT |

The two most autonomy-critical agents — **Triage (ABL-0002)** and
**Escalation Bridge (ABL-0004)** — are unbuilt. Current "self-correction"
is hardcoded retry, not a judging agent.

### Architect prerequisites: 2 of 4

- **Batch A (memory/invariant artifacts):** ✅ landed + verified (docs-only).
- **Batch B (doctrine-meta-agent / ABL-0003):** ✅ built + smoke-verified
  against one archived sprint, **with open gaps** (A41 prompt-vs-SKILLS
  contradiction + 0-proposals observability; A43 false-evidence). Formal
  Batch-B gate boxes in the tracker remain unticked despite sign-off prose.
- **Batch C (framework-reviewer adversarial role):** 🔴 NOT STARTED.
- **Batch D (scheduled observer):** 🔴 NOT STARTED — and D is precisely the
  component designed to run *between* the architect's per-turn invocations.

The self-hardening loop the plan defines as "done" (propose → adversarially
review → continuously observe) is **open at two of its four stations.**

### Invariants: only 1 of ~13 R-rules fully contract-compliant

Per the I-2 table, only **R13** has rule + enforcement point + callable
test. Every other rule has an enforcement point but no test; **R9 has no
enforcement at all** (A8). The I-2 "contract machinery" (a doctrine-spec
data structure in code + a CI meta-test that fails any rule lacking
enforcement) is mandated but **not built** — so I-2, the invariant meant to
make doctrine self-policing, is itself mostly aspirational.

---

## The genuinely good news — the autonomy trajectory is real

| Sprint | BLs | Operator rescues mid-sprint |
|---|---|---|
| documents_1 | — | 2 (manual rebase + silent abort from A35) |
| documents_2 | 8 | 0 live, but 2 silent QA-merge degradations (A37) |
| documents_3 | 3 | 0 — fully clean, zero R10 retries |
| intelligent_kanban | 7 | 0 so far, 3/7 merged, running ~5h |

Each rescue class got closed *structurally* (A35, A37, A1 auto-rebase). The
per-sprint rescue count fell from 2 → 0. That is the self-hardening loop
working as the thesis wants.

**Caveat:** documents_3 was a 3-BL *validation* sprint run specifically to
confirm those fixes, on the same repo. The crew is clean on failure classes
it has *already hit and patched* — not yet proven on a novel large feature
with no prior coverage.

---

## Architect-obligation findings

1. **I-6 trigger fired and has not been honored.** The I-2
   (doctrine-enforcement-gap) class has **8 instances** (A8, A11, A12, A16,
   A36, A39, A40, A41) — well over the >3 threshold that is supposed to
   force a proposal to *tighten the invariant* rather than another per-site
   patch. The open cluster (R9 enforcement = A8+A11, layer-coverage = A36)
   is still being handled per-site. By project doctrine, the architect
   should propose the I-2 contract machinery (doctrine-spec + CI meta-test)
   as the class fix. This is overdue.

2. **Governance doc-drift.** `ARCHITECTURE_INVARIANTS.md` (stamped
   2026-05-23) is behind the code: it still calls I-3 and I-7
   "missing/aspirational" when `closure_check.py` and the doctrine-meta
   agent both shipped. R14 is absent from the I-2 table entirely. Stale
   doctrine docs are themselves an I-2 violation.

3. **Ledger box lag.** A32, A35, A37, A43 have fixes shipped (per commits)
   but open `[ ]` boxes. Functionally closed, hygiene lagging — makes the
   open-count read worse than reality (~17 genuinely open vs 19 by box).

4. **A documented contradiction in the success metric itself.** `THESIS.md`
   §7 names *operator-time < 1 hr* as THE "Success metric." `CLAUDE.md` +
   `arch_mission_framing.md` explicitly demote that to "a thermometer, not
   the patient." The two governing docs disagree on what "done" *means*.
   This is the operator's call to resolve; it materially changes how this
   evaluation should be scored.

---

## Calibrated verdict

**~40% delivered, and it is the right 40%** — the highest-leverage,
hardest-to-fake part (a grounded, gated, self-correcting worker loop)
genuinely works end-to-end and is getting more reliable sprint over sprint.
But three of the four crew properties have material gaps, the *cumulative*
property is barely operational as a crew capability, and the components
that actually remove the human (Triage, Escalation, cross-project memory,
the always-on observer) are unbuilt.

The crew today is a **very good autonomous worker pool with a hardcoded
conductor**; it is not yet an **autonomous team with judgment.** The
trajectory is sound. The standing risks: the open-shortcoming surface is
climbing faster than it is being closed, and I-2 is being patched per-site
instead of tightened structurally — the exact failure mode the architect
role exists to prevent.

---

## Open decisions for the operator

1. **Resolve the §7-vs-CLAUDE.md metric contradiction** so "done" has one
   definition.
2. **Authorize the I-2 structural tightening** (doctrine-spec data
   structure + CI meta-test closing A8/A11/A36 as a class) — the
   highest-value architect move available, and overdue by project doctrine.

*Evaluation persisted 2026-05-28. Snapshot state: branch `architect-prereqs`
tip `b25cf2b`; live sprint `run-20260528T144444Z-e4ba3d` (intelligent_kanban,
3/7 BLs merged, in flight).*
