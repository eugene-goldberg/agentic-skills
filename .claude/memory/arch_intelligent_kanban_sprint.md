---
name: arch-intelligent-kanban-sprint
description: "First non-Documents brownfield feature sprint — Kanban board UI added to full-stack-fastapi-template. Run-20260528T144444Z-e4ba3d on branch intelligent_kanban (forked from documents_3). 4h28m elapsed snapshot — 3 of 7 BLs merged_full, BL-0003 engineer running. First sprint with A35+A36+A37+A40+A43 doctrine all loaded."
metadata: 
  node_type: memory
  type: project
  originSessionId: 5df1d1a7-9c81-4cf8-a966-3c2c4dc1a653
---

## Identity

- **Run ID:** `run-20260528T144444Z-e4ba3d`
- **Started:** 14:44:44 UTC 2026-05-28
- **Target repo:** `~/dev/ai-projects/brownfield-targets/full-stack-fastapi-template/`
- **Agent branch:** `intelligent_kanban` (NEW; forked from `agentic-skills-work-documents_3` HEAD `b0f0b7e`)
- **Operator-owned requirements:** `_brownfield/features/intelligent-kanban/REQUIREMENTS.md` (committed in bootstrap `0e9753b`)
- **Submission:** Python urllib script (`/tmp/submit_intelligent_kanban.py`, no read timeout) PID 77298
- **SSE log:** `/tmp/intelligent-kanban-sse.log`
- **Submit params:** `stop_on_failure=true`, `stop_on_qa_doctrine_failure=true`, `run_doctrine_meta=true`, **no `max_bls` cap**

## Brief framing decisions (operator-driven, 2026-05-28 morning)

The original `intelligent_kanban.md` brief assumed `Tasks`, `Comments`, `Notifications`, document-versioning existed on the target — verified state shows only `User`, `Item`, `Workspace`, `WorkspaceMember`, `Project`, `Folder` are present. Architect rewrote the brief to:

- Map Kanban cards to existing **Item** entity (forbid inventing Task)
- Strip Comments / Notifications / Doc-versioning dependencies
- Replace external notification with in-table `BoardEvent` audit row
- Defer AI layer (REQ-0305) and WebSocket transport to follow-up sprints
- Tag each FR with A36 layer-coverage hints (model/migration/route/test/frontend/dependency)
- Bind success criteria to brownfield rubric axes (1-5)
- Dir renamed `Intelligent_Kanban` → `intelligent-kanban` to match `_slugify("Intelligent Kanban")`
- File named `REQUIREMENTS.md` (operator-owned; framework's `brief.md` snapshot is separate)

## PO decomposition (7 BLs)

PO restructured dep order intelligently — BL-0005 (WorkflowRule + BoardEvent) lifted ahead of BL-0003 (BoardCard) because BoardCard mutations emit BoardEvent rows.

| Position | BL | Title |
|---|---|---|
| 1 | BL-0001 | Board entity + CRUD router |
| 2 | BL-0002 | BoardColumn + WIP limits |
| 3 | BL-0005 | WorkflowRule + BoardEvent + sync rule engine |
| 4 | BL-0003 | BoardCard model + add/move/remove + concurrency |
| 5 | BL-0004 | Permission gating + 404-privacy invariants |
| 6 | BL-0006 | Frontend Kanban (dnd-kit + TanStack polling) |
| 7 | BL-0007 | Invariant / characterization / regression test hardening |

## Progress at 4h28m snapshot

| BL | Status | Detail |
|---|---|---|
| BL-0001 | merged_full | 1 doctrine retry (engineer), 1 doctrine retry (scorer), gates clean, ~50 min |
| BL-0002 | merged_full | zero retries, ~40 min |
| BL-0005 | merged_full | **2 gate regressions** on same test `test_board_rules.py::test_engine_loop_guard_max_depth_one` — saved on the FINAL (R10-budget-exhausting) retry. Engineer landed at attempt 3. ~80 min |
| BL-0003 | engineer running | 1 doctrine retry → complete; gate next |
| BL-0004 | queued | permission gating |
| BL-0006 | queued | frontend (dnd-kit new dep) |
| BL-0007 | queued | test hardening |

## PO behavior observations

- **PO numbered BLs as BL-0401…BL-0407 on attempt 2** — took REQ-0401 numbers literally. Doctrine validator caught it with a precise error message; PO corrected on attempt 3. Good demonstration of the focused-fix delta-prompt mechanism (R10.1).
- PO satisfied A36 layer-coverage across all 7 BLs on attempt 3 — no tier_15 kills, no pregrounding_violated events.
- PO consumed 2 R10.1 retries (the budget).

## Engineer behavior observations

- BL-0005 needed BOTH R10 retries on the same test failure — the focused retry prompt didn't move the engineer on the first try. Worth noting as a data point about retry-prompt quality for concurrency/loop-guard class bugs.
- All other engineer phases: ≤1 doctrine retry, gate green first try.
- Zero tablename mismatches (A36 holding).
- Zero graphify-out collisions (A35 holding).

## Cost observations

- BL-0001 scorer's doctrine-retry session alone: **~$0.96** Opus 4.7 with 719K cache-read tokens (heavy cache hit). Caching working as designed.
- Initial PO across 3 attempts: ~9 min cumulative wall, ~$2-3 estimated (heavy retrieval grounding).

## Cumulative test suite size

- Pre-sprint baseline: ~131 tests
- Post-BL-0005: **209 tests passing** — engineer + QA added ~78 net-new tests with zero regressions on the original baseline through 3 BLs

## Open monitor

- Background tail task `bj9ykkrri` filters meaningful phase events from SSE stream
- `stop_on_failure=true` is the abort lever; will fire if R10 budget exhausts on any BL
- ETA to sprint close: ~3 hours from 4h28m mark (4 BLs to go; BL-0006 frontend is the highest-uncertainty remaining)

## Lessons (carry-forward)

1. **PO can take requirement numbers literally** — REQ-0401 → BL-0401. The doctrine validator's precise error message ("first BL must be BL-0001") corrected it. Worth considering whether to add an explicit "BL numbering resets per feature" line to the PO prompt; the validator's catch is sufficient for now.
2. **Engineer can stall on same test across multiple retries** — BL-0005's loop-guard required 3 attempts. R10 budget of 2 retries is the right size: enough to recover from genuine bugs, not so much that engineers grind indefinitely.
3. **Forking from a non-master agent_branch is the right call when the brief depends on entities only that branch has.** intelligent_kanban inherits Workspace/Item/Project/Folder from documents_3 cleanly.
4. **`stop_on_qa_doctrine_failure=true` is the right default for validation sprints** — silent merged_no_qa was the documents_2 failure mode; A37 closed the merge-error variant, this flag closes the doctrine-give-up variant.
