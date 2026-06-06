---
name: feedback-no-abort-persistence
description: "Operator doctrine 2026-06-06 (BINDING, non-negotiable): aborting a sprint = FAILURE and is unacceptable. Every agent (each a full Claude Code subprocess) that detects ANY issue (code/test/infra/data/…) MUST fully investigate → apply the proper fix → re-test, and keep working comprehensively until it is resolved. No shallow give-up, no symptom-chasing, no routine abort."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 48e5d2ed-b267-495f-91d2-00b7a0b8acbb
---

## The doctrine (operator, 2026-06-06 — verbatim intent)

1. **Aborting a sprint means FAILURE. The operator will not accept it.** "Aborted"
   is not an acceptable terminal state for a run.
2. **Whenever any agent detects an issue** (code, test, infrastructure, data,
   anything) it **MUST**: (a) **fully investigate**, (b) **apply the proper
   fix**, (c) **re-test** — and keep iterating until the issue is genuinely
   resolved. Every agent is a sub-process copy of Claude Code, fully capable of
   autonomous investigation and repair of any modern software/code/test issue.
   Each agent must take the time to do the most comprehensive work and keep
   working on an issue until it is resolved.

**Why:** the crew was giving up on *solvable* problems. Evidence: Horizon
BL-0001 ("auth break") and item-comments BL-0001 ("test_delete_comment") were
both read as "capability walls" — but investigation showed item-comments was a
*flaky test on already-green code* (fully fixable) and the harness had aborted
after only ~2 shallow retries while the engineer chased symptom specs instead of
root-causing. The mission is "submit a brief and walk away to clean,
regression-tested commits." A crew that aborts on the first hard thing can never
deliver that. Abort-on-failure is the antithesis of the mission.

## How to apply

- **This binds the AGENTS, not just chat promises.** A doctrine is only "always
  followed" when it is *encoded* — the current harness still aborts
  (`stop_on_failure`, `engineer_unmerged`, `qa_merge_failed` → `orchestrator.aborted`;
  R10/R10.1/R10.2 cap retries at ~2). Making this real requires changing the
  harness: replace abort-as-default with a per-role **investigate → fix →
  re-test loop** that persists until green; deepen/remove the shallow retry
  caps; embed a **root-cause-before-patch** mandate in every role's gate-fix
  prompt (extend the acceptance-v0.2 verified-investigator pattern to engineer,
  QA, scorer — read the actual source, falsify competing causes, fix the cause
  not the symptom, re-test).
- **The only acceptable non-success** is a loud **escalation to the operator with
  a complete, source-grounded dossier** AFTER genuinely exhaustive, senior-level
  effort (many distinct approaches tried, root cause traced or proven
  intractable) — never a routine "aborted." The bar for escalation is "a
  competent senior engineer would also be blocked here," not "2 retries used."
- **Applies to the architect (me) too**, per CLAUDE.md symmetry: when I hit an
  issue I investigate→fix→verify to resolution, I don't hand back a shrug.
- A sane resource backstop (cost/wall-clock) may still exist to prevent infinite
  spend, but it triggers **escalation-with-dossier**, not silent abort, and is a
  rare last resort — confirm exact semantics with operator before relying on it.

Related: [[arch-acceptance-v02]] (the root-cause-investigator pattern to
generalize), [[arch-horizon-run]] / [[arch-harness-hardening]] (the premature-
abort evidence that motivated this), [[arch-active-branch]].
