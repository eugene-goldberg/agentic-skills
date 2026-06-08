---
name: arch_self_resolution_arc
description: "A57-A61 (2026-06-08) — the \"crew fully resolves its own issues\" capability arc; general crew improvements shipped during the first real brownfield (beaverhabits) experiment"
metadata: 
  node_type: memory
  type: project
  originSessionId: be51e21b-1239-4b56-b567-6fbcd02be99e
---

Session 2026-06-08 systematically closed the "an agent hits/finds an issue but
doesn't fully RESOLVE it" gaps. All GENERAL crew improvements (not target
accommodations — see [[feedback_improve_crew_not_accommodate]]). Committed +
tested; dev=main at `b7ab0b9`; 351 harness tests pass.

- **A57** (`b9c2aa9`) — regression gate supports multi-token `test_cmd`
  (`uv run pytest`) + per-target `test_env` in `.agentic-skills.json`. Structural
  enabler for ANY real third-party target whose suite isn't bare `pytest`. See
  [[arch_gate_multitoken_testcmd]].
- **A58** (`8e1d0cc`) — engineer-path merge failures route to the Janitor
  (`_engineer_janitor_trigger`); closed the asymmetry vs the QA path (which
  already did). Dossier carries `blocker="merge_error"` + `merge_branch`.
- **A59** (`5d9a9e8`) — the Janitor FULLY resolves a merge failure in-loop:
  `_should_remerge_after_janitor` → after repair, re-attempt `fast_forward_target`;
  on success the BL flows through normal QA/scorer; only genuinely-unrepairable
  escalates. (Auto-rerun-after-repair, formerly "deferred", is now done for the
  merge case.)
- **A60** (`a4e23e8`) — crew auto-resolves high-confidence acceptance
  `product_bug` findings. `_finding_dispatch_eligible`: eligible if operator-
  confirmed OR `verdict is None and confidence >= 0.90` (FOLLOWUP_AUTOCONFIRM_
  CONFIDENCE). Dispatched fix still clears full gate before merge; cost cap 1;
  R15 holds; operator rejection always wins.
- **A61** (`b7ab0b9`) — follow-up fixes resolve the FULL fix-locus.
  `_build_followup_section` now surfaces the verified root_cause/fix_locus dossier
  and binds the engineer to fix EVERY named surface with a deterministic test;
  the engineer's existing no-abort gate loop becomes the re-verify-and-iterate
  mechanism (can't merge until all surfaces green). Lever B (acceptance re-run
  loop) was REJECTED — defeated by the `finding_id` collapse (thin
  evidence_summary → constant id → R15 false-resolved); rationale in
  `PLAN_acceptance_resolve_loop.md`.

**Validated live on the first REAL brownfield target** ([[arch_target_beaverhabits]]):
the crew delivered "Rest Days" (3 BLs merged_full), acceptance caught a half-wired
streak bug, and after A60+A61 the crew autonomously resolved the full locus (badge
+ echart, shared `core.streak` bridge), 99 tests green. Clean A61 attribution.

**Frontier after this arc:** worker-loop + self-resolution are well-built; the
mission's unbuilt majority is the CUMULATIVE property (crew brain) —
[[arch_cumulative_learning]]. Smaller general candidates: A56 warmup non-adaptive
on cold targets; gate diff-on-quiet output.
