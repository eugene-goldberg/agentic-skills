---
name: arch-active-branch
description: Active work location as of 2026-05-28 midday — branch architect-prereqs at b25cf2b (A43 shipped). Live sprint intelligent_kanban run-20260528T144444Z-e4ba3d in flight on target branch intelligent_kanban (forked from documents_3). 3 of 7 BLs merged_full at 4h28m; BL-0003 engineer running.
metadata: 
  node_type: memory
  type: project
  originSessionId: 5df1d1a7-9c81-4cf8-a966-3c2c4dc1a653
---

Active work branch: **`architect-prereqs`** tip **`b25cf2b`** (A43 Layer-1 commit on top of `05e8451`). **Public GitHub:** https://github.com/eugene-goldberg/agentic-skills.

## What landed earlier this session (2026-05-27 PM → 2026-05-28 morning)

Framework hardening — 11 commits closing A35 fix #2, A36 (4-part), A37, A40. A38 withdrawn. 23 unit tests added. doctrine_meta + closure_check confirmed operational. See `arch_intelligent_kanban_sprint.md` for live sprint detail.

## What landed late-morning 2026-05-28 (post-handoff)

| Commit | Item |
|---|---|
| `b25cf2b` | fix(A43): meta-agent verify-before-claim discipline (Layer 1) |

A43 filed in `DESIGN_SHORTCOMINGS.md` (priority medium, status: Layer 1 shipped). Meta-agent's first novel proposal (`graph-retrieval-payload-gap.md`) moved to `.planning/doctrine_proposals/rejected/` after architect verification found its central absence-claim contradicted by 100% of 19 graph_* retrieval.jsonl records. Layer 1 fix tightens `## Evidence Discipline` in `skills/brownfield/brownfield-production-incremental-doctrine-meta/SKILLS.md` with:
- schema-uniformity-assumption rule (forbidden generalization across tools)
- worked failure example (this exact proposal + contradicting lines)
- citation-shape-matches-claim-shape principle
- pre-emit self-check for absence-claims (≥3 per-tool per-record citations required)

Layer 2 (mechanical claim-checker) explicitly rejected — accepted-proposal citation formats too variable for regex; existing Evidence Discipline worked at reviewer boundary; revisit only on a second false-evidence proposal.

## Target repo state (full-stack-fastapi-template)

- `agentic-skills-work` (documents_1 era) — preserved
- `agentic-skills-work-documents_2` — 8 BLs landed
- `agentic-skills-work-documents_3` — 3 BLs landed
- **`intelligent_kanban`** — NEW branch this session, forked from documents_3 HEAD `b0f0b7e`, bootstrap commit `0e9753b` (sets `.agentic-skills.json agent_branch=intelligent_kanban` + commits `_brownfield/features/intelligent-kanban/REQUIREMENTS.md`). Live sprint writing to this branch right now.

## Open ledger items (DESIGN_SHORTCOMINGS.md)

| ID | Status | Notes |
|---|---|---|
| A8 / A9 / A11 | open (carry-forward) | R9 post-validator gaps; gate pgroup leak |
| A27 / A28 / A29 / A30 / A31 | open (carry-forward) | branch isolation; gate throughput |
| A32 | CLOSED 2026-05-25 | test hang via R14 + pytest timeout |
| A33 | minor open | `.latest` symlink |
| **A35** | fix #2 CLOSED 2026-05-28 | graphify-out pre-merge cleanup |
| **A36** | CLOSED 2026-05-28 | Three-layer defense (PO grounding + engineer prompt + pre-merge validator) |
| **A37** | CLOSED 2026-05-28 | qa_merge_failed handler symmetric with engineer-merge path |
| A38 | withdrawn | subsumed by A36 fix #2 |
| A39 | open | regression_gate parser conflates build-failure with all-tests-regressed |
| **A40** | CLOSED 2026-05-28 | Engineer prompt directs use of formatter --apply/--fix |
| A41 | open | meta-agent prompt git contradiction + 0-proposals observability gap |
| **A43** | **CLOSED 2026-05-28 (Layer 1)** | meta-agent verify-before-claim discipline; SKILLS.md tightened with schema-uniformity rule + worked example. Layer 2 explicitly deferred. |

## Process state (2026-05-28 midday)

| Process | State |
|---|---|
| uvicorn (port 8000) | UP (PID 69911, started 14:44 UTC for live sprint) |
| milvus-standalone | UP ~26h |
| Active sprint | **YES — intelligent_kanban `run-20260528T144444Z-e4ba3d`** at 4h28m elapsed |
| `.orchestrator-state/live/` | (single run state file for the live run) |
| SSE submit | PID 77298 alive, streaming to `/tmp/intelligent-kanban-sse.log` |
| Background tail monitor | Bash task `bj9ykkrri` watching phase transitions |

## Pending for next session (after sprint closes)

1. **Watch sprint close** — `intelligent_kanban` sprint will complete or abort within ~3h of the 4h28m mark. Read final outcome + doctrine_meta output.
2. **Verify closure_check docker scope** — latent I-3 bug; documents_2 ended with 8 stale per-BL containers but closure_check reported 0 violations. ~15 min.
3. **A39** — `regression_gate.py` parser fix.
4. **A41** — meta-agent SKILLS.md prompt contradiction fix.
5. **Move 3** (ManagedSubprocess for A9) — structural close of pgroup leak class.
6. **Batches C + D** of ARCHITECT_PLAN — framework-reviewer + scheduled observer.

Source: commit log on `architect-prereqs`, `DESIGN_SHORTCOMINGS.md`, `/tmp/intelligent-kanban-sse.log`.
