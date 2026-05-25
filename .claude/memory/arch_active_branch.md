---
name: arch-active-branch
description: Active work location as of 2026-05-24 EOD — branch architect-prereqs at 7ffad52; pushed to public GitHub https://github.com/eugene-goldberg/agentic-skills. Target repo wiped and re-cloned to vanilla; first BL ever merged through full A18+A19+A20+A21+A22+A24+A25+A26+WI3A+A32 stack.
metadata:
  type: project
---

Active work branch: **`architect-prereqs`** (off `sprint-2-orchestrator@710992b`). Tip at memory-write time: **`7ffad52`**, 45+ commits ahead. **Pushed to `origin` (public GitHub).**

## Public GitHub

- URL: https://github.com/eugene-goldberg/agentic-skills (PUBLIC)
- Default branch: `architect-prereqs` (the current frontier)
- 6 branches mirrored: `main`, `skills_with_graphs`, `webapp`, `brownfield-production`, `sprint-2-orchestrator`, `architect-prereqs`
- README at repo root is the synthesized reviewer entry (13 sections, ~400 lines).

## What landed today (2026-05-24)

### Framework hardening — committed on architect-prereqs

| Commit | Item | Effect |
|---|---|---|
| `9142263` | gate(A21/A22/A25b/A26) | Truthful aggregation + lowercase compose name + infra_fail kind + 5GB disk pre-flight |
| `58d9468` | brownfield(A25a/A19/A20/WI3A) | Infra-aware extractor + per-feature BL-0001 reset + canonical brief.md + sibling-feature touch guard |
| `b2ed5c4` | docs(ledger+memory) | A19-A26 marked done; A27 (per-feature branch), A28-A31 (gate throughput) filed; arch_gate_throughput.md memory |
| `839cc67` | chore(lg-SKILLS) | Pre-existing dirty briefs/skills committed (Group A) |
| `d0d33d9` | docs(README) | Reviewer entry point ~400 lines synthesizing 8 governance docs |
| `3c64b43` | docs(README §2) | Added "The team" section up front |
| `7ffad52` | doctrine(qa): R14 | Test design constraints to prevent gate hangs (R14.1 TestClient, R14.2 Alembic DDL, R14.3 timeout discipline) |

### Target repo (full-stack-fastapi-template)

Wiped + re-cloned from upstream FastAPI on 2026-05-24 PM (operator approved). Lost: 4 sprints' worth of prior work (Team Collaboration, Notifications, api-keys, RBAC) + 47 agent branches. Preserved & restored:
- `.agentic-skills.json` (agent_branch=`agentic-skills-work`, NOT `-v3`)
- `scripts/regression_gate.sh`
- `compose.gate.yml`
- `.git/info/exclude` entry for events.jsonl

Target's `agentic-skills-work` branch tip: **`c7ea13e`** (A32 gate fix). Above it: `801847d` (BL-0001 — first crew code shipped on fresh target).

## Sprints run today on fresh target

| Sprint | Run ID | Outcome |
|---|---|---|
| documents (1st) | run-20260524T173501Z-653b2f | Aborted — events.jsonl tracked → merge blocker (A24) |
| documents (resubmit) | run-20260524T180834Z-3bbf81 | Aborted on BL-0201 engineer_unmerged — A21/A22/A25/A26 root causes |
| documents_1 (1st) | run-20260524T200334Z-1b6c40 | Aborted — QA-side gate inconclusive on baseline test failures (A19 first-real test) |
| documents_1 (clean) | run-20260524T220528Z-f56070 | **BL-0001 merged successfully** (sha `801847d5`); QA-side gate hung 30+ min on `test_alembic_upgrade_downgrade_upgrade_round_trip` → operator killed → A32 root-cause + two-layer fix shipped |

**First BL-0001 production merge against the fresh, clean baseline** = `801847d` on target's `agentic-skills-work`.

## Open ledger items (architect-prereqs DESIGN_SHORTCOMINGS.md)

| ID | Class | Status |
|---|---|---|
| A8 | enforcement-gap (R9 post-validator) | open |
| A9 | resource-leak (gate subprocess pgroup leak) | open; closes in Move 3 |
| A11 | enforcement-gap (R9 streaming-side) | open; depends on A8 |
| A27 | per-feature branch isolation | deferred until parallel sprints justify |
| A28 | Playwright --workers 1 → 4 | one-line fix, defer until first clean green sprint |
| A29 | PRE-phase result cache | ~50% gate speedup per sprint after first BL |
| A30 | Test Impact Analysis | 5-20× reduction on focused changes |
| A31 | Tiered gate (per-BL fast, sprint-end full) | restructures merge contract |
| **A32** | **gate-hang from QA test bugs** | **CLOSED** by c7ea13e (target) + 7ffad52 (doctrine R14) |
| A33 | `.latest` symlink not pointing at current run | minor, deferred |

## Process state at handoff

| Process | State |
|---|---|
| uvicorn | PID 98752 alive on port 8000 |
| vite | port 5173 |
| docker stack | torn down clean (no orphan containers) |
| Active sprints | none (last killed by operator after A32 investigation) |
| Worktrees on target | main checkout only (`agentic-skills-work` @ c7ea13e) |
| Free disk | ~50 GB |

## Pending for next session

1. **Test the A32 fix end-to-end.** Submit a fresh sprint that includes a Q&A pattern → confirm pytest timeout fires at 120s rather than hanging.
2. **A18-followup migration** — relocate the two `<agentic-skills>/sprint_briefs/` files to `<target>/_brownfield/features/<slug>/`, delete `sprint_briefs/` dir.
3. **Move 3** (ManagedSubprocess for A9) — closes structurally.
4. **Batches C + D** of ARCHITECT_PLAN — framework-reviewer + scheduled observer.
5. **A28** — one-line fix to playwright workers=4 once green-path proven.

Source: commit log on `architect-prereqs`, target commit log on `agentic-skills-work`, `DESIGN_SHORTCOMINGS.md`, `ARCHITECT_PLAN.md`.
