---
name: arch-active-branch
description: Active work location as of 2026-05-28 morning — branch architect-prereqs at 05e8451. A36 (4-part), A35 fix #2, A37, A40 all shipped + validated against documents_2 (full 8-BL sprint) and documents_3 (clean 3-BL validation). doctrine_meta + closure_check confirmed operational. 1 meta-agent proposal pending rejection (R9 graph-payload — evidence contradicted by citations).
metadata:
  type: project
---

Active work branch: **`architect-prereqs`** (off `sprint-2-orchestrator@710992b`). Tip: **`05e8451`**, in sync with origin. **Public GitHub:** https://github.com/eugene-goldberg/agentic-skills.

## What landed this session (2026-05-27 PM → 2026-05-28 morning)

### Framework hardening — 11 commits on architect-prereqs

| Commit | Item | Effect |
|---|---|---|
| `911d099` | docs: RUNBOOK_clean_brownfield_reset.md | Procedural map for fresh-fork brownfield runs |
| `a093109` | docs(runbook): Step 1.5 harness cherry-pick + conditional push | Captures real gaps hit during documents_2 reset |
| `116cce4` | ledger(A36) | PO retrieval-coverage gap forensic |
| `bd00b34` | ledger(A37-A41) | 4 findings + A38 withdrawal |
| `16d148c` | docs(CLAUDE.md) | Correct doctrine_meta + closure_check claims (both operational, not pending) |
| `6f0551c` | fix(A36.2) | PO prompt layer-coverage requirement |
| `1167300` | fix(A36.3 + A40) | Engineer prompt tablename rule + auto-fix tooling |
| `660efd0` | fix(A36.4) | Pre-merge SQLModel/migration tablename validator + 14 tests |
| `0cddb43` | fix(A35.2) | fast_forward_target pre-merge graphify-out cleanup + 3 tests |
| `7faaf37` | fix(A37) | qa_merge_failed handler in run_brief + 3 tests |
| `05e8451` | docs(runbook) | Step 1.5 graphify-out gitignore belt-and-suspenders |

**23 unit tests added across the session.** All pass.

### Target repo state

- `agentic-skills-work` (documents_1 era) — preserved
- `agentic-skills-work-documents_2` — 8 BLs landed (1 silent QA-merge incident on BL-0002/BL-0007 → root-caused as A35+A37 → fixed)
- `agentic-skills-work-documents_3` — 3 BLs landed clean (validation sprint, zero R10 retries)

## Sprints run this session

| Sprint | Run ID | Outcome |
|---|---|---|
| documents_2 | `run-20260527T160519Z-9811fa` | 8/8 BLs merged, ~7h wall, 1 silent QA-merge degradation (BL-0002/BL-0007) → A35/A37 root cause |
| documents_3 | `run-20260528T013535Z-ed1a60` | 3/3 BLs merged clean, ~2.5h wall, zero R10 retries; engineer pre-emptively wrote A36-compliant migration guards (prompt-layer awareness reached subprocess); doctrine_meta produced 1 novel proposal (rejected on operator review) |

### documents_3 validation results (all four A-fix checkpoints passed)

1. **PO layer-coverage:** 6/6 layer citations per BL × 3 BLs
2. **graphify-out merge errors:** 0
3. **qa_merge_failed events:** 0
4. **Tablename validator triggers:** 0 needed (engineer prevented the bug proactively)

## Open ledger items (DESIGN_SHORTCOMINGS.md)

| ID | Status | Notes |
|---|---|---|
| A8 / A9 / A11 | open (carry-forward) | R9 post-validator gaps; gate pgroup leak |
| A27 / A28 / A29 / A30 / A31 | open (carry-forward) | branch isolation; gate throughput tier |
| A32 | CLOSED 2026-05-25 | test hang via R14 + pytest timeout |
| A33 | minor open | `.latest` symlink |
| **A35** | **fix #2 CLOSED 2026-05-28** | graphify-out pre-merge cleanup in fast_forward_target |
| **A36** | **CLOSED 2026-05-28** | Three-layer defense: PO grounding + engineer prompt + pre-merge validator |
| **A37** | **CLOSED 2026-05-28** | qa_merge_failed handler symmetric with engineer-merge path |
| A38 | withdrawn | subsumed by A36 fix #2 (route layer covered) |
| **A39** | new this session, open | regression_gate parser conflates build-failure with all-tests-regressed |
| **A40** | **CLOSED 2026-05-28** | Engineer prompt directs use of formatter --apply/--fix |
| **A41** | new this session, open | meta-agent prompt git contradiction + 0-proposals observability gap |
| **A43 candidate** | new this session, not yet filed | meta-agent verify-before-claim discipline (R9 proposal evidence contradicted by citations) |

## What's operational (corrected this session)

- ✅ **doctrine_meta** — `webapp/backend/app/services/orchestrator.py::_doctrine_meta_flow` + `skills/brownfield/brownfield-production-incremental-doctrine-meta/SKILLS.md`. Confirmed running after every `sprint_complete` event when `run_doctrine_meta=True` (default).
- ✅ **closure_check** — `webapp/backend/app/services/closure_check.py`. Fires after doctrine_meta; emits `orchestrator.closure_check.{start,done}` with `violation_count` + `by_kind`. Verified 0 violations across both sprints this session. **Note:** docker container scope unverified — documents_2 ended with 8 stale per-BL containers but closure_check reported 0 violations. Either it doesn't scan docker or its pattern misses per-BL naming. Latent I-3 bug worth confirming next session.

## Process state at handoff (2026-05-28 morning)

| Process | State |
|---|---|
| uvicorn (port 8000) | **STOPPED** (PID 78696 killed during handoff cleanup) |
| milvus-standalone | UP ~23h (infra service, leave running) |
| docker stale stacks | cleared (6 per-BL containers + 2 app-db volumes purged) |
| Active sprint | none |
| `.orchestrator-state/live/` | empty |
| Worktrees on target | main checkout only on `agentic-skills-work-documents_3` |
| Free disk | (not measured this handoff; was ~50 GB at prior) |

## Pending for next session (priority order)

1. **Decide R9 proposal disposition** — reject (recommended; see CONTINUATION_PROMPT.md §7) + file A43 + Layer-1 fix to meta-agent SKILLS.md.
2. **Verify closure_check docker scope** — read closure_check.py + replay against documents_2 trace archive. ~15 min.
3. **A39** — `regression_gate.py` parser fix (build-failure → suppress downstream-test "regression" entries).
4. **A41** — meta-agent SKILLS.md prompt contradiction fix.
5. **Extend documents_3 to all 8 BLs** to validate full pipeline at scale (not urgent; 3-BL pass already validated changed paths).
6. **Move 3** (ManagedSubprocess for A9) — structural close of subprocess pgroup leak class.
7. **Batches C + D** of ARCHITECT_PLAN — framework-reviewer + scheduled observer.

Source: commit log on `architect-prereqs`, `DESIGN_SHORTCOMINGS.md`, events.jsonl for both sprints, `.planning/doctrine_proposals/`.
