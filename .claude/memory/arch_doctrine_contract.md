---
name: arch-doctrine-contract
description: I-2 — every documented R-rule maps to exactly one enforcement point and one test; documentation alone is not enforcement
metadata:
  type: project
---

R-rules and Tiers live in three layers today: prompt text (SKILLS.md), per-event streaming counter (claude_agent.py), post-hoc artifact validator (doctrine_validator.py). The split is fine in principle but undisciplined in practice — A8 surfaced because R9 (≥1 graph_* call) was documented but had NO enforcement code anywhere.

**Why:** "documented" and "enforced" diverged silently. Sprint 4 BL-0006 passed doctrine with zero graph_* calls because no code path checked. The validator returned `complete` and the orchestrator merged. Architect-level fix: a single doctrine-spec data structure mapping each rule to (enforcement_point, callable_check, test). Meta-test asserts no rule has zero enforcement.

**How to apply:**
- When adding a new R-rule, add the spec entry FIRST, the code SECOND. The spec data structure refuses an entry without an enforcement_point.
- Existing rules audit (see ARCHITECTURE_INVARIANTS.md § I-2 table): R9 has the gap (A8). R5b and R7 are validator-checked but untested.
- Enforcement points are exactly: `prompt`, `preflight`, `streaming`, `post_validation`, `gate`. New points need invariant-doc updates first.

The doctrine-meta agent (ABL-0003, this branch's Batch B) uses this spec to classify findings. Proposals that don't fit the spec format get flagged by the framework-reviewer (Batch C).

Source: `ARCHITECTURE_INVARIANTS.md` § I-2. Instance: A8 in DESIGN_SHORTCOMINGS.md (commit 710992b).
