---
name: arch_evaluation_2026-05-28
description: "2026-05-28 objective project evaluation vs thesis; verdict, autonomy gaps, and the proposed Batch E/G work awaiting operator authorization"
metadata: 
  node_type: memory
  type: project
  originSessionId: de82aa1b-10ab-4ed6-99fa-147b99d3e7ab
---

Objective architect evaluation of agentic-skills against the thesis's own
definition-of-done, persisted to `EVALUATION_2026-05-28.md` (repo root).

**Verdict:** ~40% of thesis operational — "the right 40%": the grounded,
gated, self-correcting *worker loop* genuinely works end-to-end and is
getting more reliable sprint-over-sprint (rescue count documents_1=2 →
documents_3=0). But the crew's *brain* is mostly unbuilt.

**Four-property scorecard:** Grounded ✅ (R5/R8/Tier-1.5 enforced; R9
graph-floor still advisory = A8). Self-correcting ⚠️ half (hardcoded retry,
no Triage agent ABL-0002). Honest ⚠️→✅ improving (rubric Fail-floor works;
A37/A34 silent-degradation bugs now fixed). Cumulative 🔴 weakest
(cross-project memory ABL-0007 unbuilt; learning carried by architect+ledger
by hand).

**Structural truth:** ~2.5 of 13 ABLs built (orchestrator ✅, doctrine-meta
✅-with-gaps, partial launcher). Architect prereqs 2 of 4 (A+B done; C
framework-reviewer + D scheduled observer NOT started — the two stations
that close the self-hardening loop and remove the per-turn bottleneck).
Only R13 is a fully I-2-compliant rule (rule+enforcement+test).

**Findings folded into `ARCHITECT_PLAN.md` §9 (and tracker rows), all
PROPOSED/awaiting operator authorization — not in the 2026-05-23 auth:**
- **Batch E (I-2 structural tightening)** — the overdue I-6 response: I-2
  enforcement-gap class has 8 instances (>3 threshold) still patched
  per-site. E-1 `doctrine_spec.py` + E-2 CI meta-test + E-3 close R9
  (A8/A11) + E-4 backfill R14/layer-coverage (A36). Highest-value architect
  move available.
- **Batch G (governance hygiene)** — G-1 sync stale `ARCHITECTURE_INVARIANTS.md`
  (I-3/I-7 shipped but doc says "missing"; R14 absent from I-2 table); G-2
  reconcile ledger boxes (A32/A35/A37/A43 shipped, boxes open); G-3 Batch-B
  gate boxes vs sign-off; G-4 close A41/A43 observability.

**Operator decisions pending:** (1) resolve the success-metric
contradiction — THESIS §7 says operator-time<1hr is THE metric;
CLAUDE.md/[[arch_mission_framing]] demotes it to "thermometer not patient."
(2) Authorize Batch E/G. (3) Confirm whether to finish self-hardening loop
(Batch C/D) first or pivot to autonomy agents (ABL-0002 Triage / ABL-0004
Escalation).

Related: [[arch_active_branch]], [[arch_failure_taxonomy]] (I-6 trigger),
[[arch_self_hardening]] (I-7), [[arch_intelligent_kanban_sprint]].
