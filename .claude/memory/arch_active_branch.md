---
name: arch-active-branch
description: Active work location as of 2026-05-24 — branch architect-prereqs at 60e5557; 38 commits ahead of sprint-2-orchestrator. Three production sprints validated; A18 per-feature isolation live.
metadata:
  type: project
---

Active work branch: **`architect-prereqs`** (off `sprint-2-orchestrator@710992b`). Tip at memory-write time: **`60e5557`**, 38 commits ahead.

## What landed on this branch (2026-05-23 → 2026-05-24)

**Batch A — Architectural memory** (done): `658dcb1` ARCHITECTURE_INVARIANTS.md, `a50026a` 7 arch_*.md memory files, `a2fa12a` continuation prompt cites, `2185cef` tracker, `e3e0e6f` CLAUDE.md architect directive.

**Mission reframing** (`fcb6d41`): crew is the goal, operator-time is a symptom.

**Sprint 4 unfiled findings filed** (`7820f8b`): A9, A10, A11.

**Batch B — Doctrine-meta-agent / I-7** (done, validated end-to-end):
- `c65ff09`..`d5c17f3` B-1..B-5 (SKILLS.md + SKILL_PATHS wiring + `_doctrine_meta_flow` + endpoint + `.planning/doctrine_proposals/`).
- `fc094f8` tracker.
- `f1a229a` agent's own commit (caught + addressed via A14).
- `1b95955` A12/A13/A14 ledger entries.
- `d126bd4` doctrine_meta SKILLS.md fixes (events.jsonl → stream.jsonl + Forbidden Tools).

**Move 2 — closure_check / I-3** (done): `ff04634` M2-1 docker prefix, `616e46f` M2-2 scan primitives, `1764ab3` M2-3 hook into run_brief, `570b228` M2-4 per-agent phase_events.jsonl. `5c85dd3` tracker + A10/A13 closed.

**R13 + R5b (operator-approved doctrine-meta proposals)**:
- `0e6bab6` R13 streaming-kill on history-rewriting git commands.
- `68a1f11` SKILLS.md updates (Forbidden Tools + Required Retrieval Evidence Footer).
- `86afca7` CLAUDE.md + INVARIANTS codification.
- `4db55cd` A15+A16 ledger + accepted proposals archived.
- `8087c4b` doctrine retry prompts switched from --amend to new-commit per R13.

**A17 sprint brief persistence**: `9594558` → `d929973` relocated from agentic-skills to target's `_brownfield/` after operator correction.

**A18 per-feature isolation** (current canonical layout):
- `165bbe1` backend across 7 files (RunBriefRequest.feature_name, feature_artifact_dir helper, feature-aware backlog/validators/prompts/orchestrator, per-feature events.jsonl tailable log, PO copy-back switched to dirs_exist_ok=True).
- `1279f69` UI feature_name input in AppV2.jsx + scripts/tail_feature.py CLI.
- `5727cb4` + `60e5557` static-mount attempt + revert (8000=backend, 5173=frontend per operator's correction).

## Production sprints validated on this branch

| Sprint | Brief | Outcome |
|---|---|---|
| api-keys (run-20260524T014937Z-e74aff) | personal API key system | 5 merged_full + 1 no_op; doctrine_meta produced 2 valid proposals (A12 + A13) post-sprint |
| RBAC (run-20260524T144409Z-90e234) | Phase 1 RBAC (roles + permissions + middleware + admin UI + Playwright e2e) | killed mid-flight at BL-0010 by operator to land A18; BL-0007/8/9 merged_full; **11/11 R5b first-try pass** (100%, up from 38% in api-keys); **0 R13 trips** |

## Open ledger items

| ID | Class | Status |
|---|---|---|
| A8 | enforcement-gap (R9 post-validator) | open |
| A9 | resource-leak (gate subprocess pgroup leak) | open; closes structurally in Move 3 |
| A11 | enforcement-gap (R9 streaming-side) | open; depends on A8 |

**Closed**: A10, A12, A13, A14, A15, A16. A17 closed by `d929973`. A18 closed by `165bbe1`+`1279f69`.

## Pending follow-up

- Migrate two backfilled briefs in `sprint_briefs/` → `<target>/_brownfield/features/<slug>/` and delete `sprint_briefs/` from agentic-skills. Held for after next clean sprint.
- Move 3 (ManagedSubprocess primitive / I-1) — closes A9 structurally.
- Batches C (framework-reviewer) and D (scheduled observer) of `ARCHITECT_PLAN.md` — pending operator authorization.

## Live process state at handoff

| | |
|---|---|
| uvicorn (backend API) | port 8000, PID 39374 |
| vite (frontend dev server) | port 5173, PID 39736, HMR live |
| Open in browser | `http://localhost:5173/` |
| Active sprint | none |

Source: `ARCHITECT_PLAN.md`, `ARCHITECT_TRACKER.md`, `DESIGN_SHORTCOMINGS.md`, commit log on `architect-prereqs`.
