---
name: arch-invariants
description: The seven structural rules every orchestrator component must satisfy; the audit lens for new shortcomings
metadata:
  type: project
---

The agentic-skills orchestrator is governed by seven structural invariants. New shortcomings must classify against one of them before a patch lands.

**Why:** Sprint 4 surfaced A8 (R9 enforcement gap) and an A9 candidate (gate subprocess pgroup leak) — both sibling-class violations of rules we'd already partly addressed for one resource. Naming the rules forces audit-by-class instead of audit-by-instance.

**How to apply:** When a failure surfaces, classify it under one of:
- I-1 Resource lifecycle owned end-to-end (see [[arch-subprocess-lifecycle]])
- I-2 Doctrine is a contract (see [[arch-doctrine-contract]])
- I-3 Closure postconditions asserted (see [[arch-closure-postconditions]])
- I-4 Single source of identity per run (see [[arch-run-identity]])
- I-5 No aggregate label more optimistic than worst component
- I-6 Failure modes have a canonical taxonomy (see [[arch-failure-taxonomy]])
- I-7 The framework hardens itself (see [[arch-self-hardening]])

Then ask: does a SIBLING site violate the same invariant? B1 covered claude-subprocess pgroup; A9 candidate covered gate-subprocess pgroup — same class, different resource. Patches that ignore the structural pattern only fix one instance.

Source: `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/ARCHITECTURE_INVARIANTS.md` (canonical doc; this memory file is a pointer).
