---
name: arch-active-branch
description: Active work location as of 2026-05-30 mid-day — architect-prereqs @ 3528cad. A43+A44+/init-feature+HARNESS.md+ui_tour+Acceptance Agent SKILLS.md draft all shipped. Time-tracking sprint LIVE on BL-0014 (last BL) after 2 operator hand-patches rescued BL-0007 + BL-0012 from auto-aborts.
metadata:
  type: project
---

Active work branch: **`architect-prereqs`** tip **`3528cad`**, in sync with origin.

## This session's commits (oldest → newest)
| Commit | What |
|---|---|
| `b25cf2b` | fix(A43): meta-agent verify-before-claim discipline (Layer 1) |
| `c3a8014` | fix(A44): StreamReader 64 MiB + api_error events |
| `59445cb` | docs(arch): EVALUATION + Batch E + memory |
| `b54586b` | feat(init-feature): automate clean-baseline branch + harness install |
| `3528cad` | docs(harness): HARNESS.md + tools/ui_tour + Acceptance Agent SKILLS.md draft |

## What's live and operational
- A43 Evidence Discipline enforcement (meta-agent SKILLS.md)
- A44 StreamReader limit (claude_agent.py)
- POST /init-feature endpoint + UI button (replaces manual runbook)
- HARNESS.md teaching doc
- tools/ui_tour/ operator-side visual inspection (validated 9/9)

## What's drafted but not wired
- Acceptance Agent (ABL-0014) — `skills/brownfield/brownfield-acceptance-agent/SKILLS.md`. Needs orchestrator wiring + prompt builder + validator + tests.

## Operator hand-patches this session
- BL-0007 (time-tracking): skipped REQ-0502 test (Radix Dialog aria-hidden interaction); merged QA's main.tsx 403 fix
- BL-0012 (time-tracking): merged engineer's branch; fixed biome formatting in ReportChart.tsx

## Open ledger priorities
- A39 promoted to high (3 worked examples now)
- A40 incomplete (--apply vs --write for biome 2.x)
- A4x candidates not yet filed: per-BL isolation cross-component asymmetry, gate-as-regression-detector-not-correctness-prover

## Sprints this session
- intelligent_kanban resume: 7/7 BLs (validated A44 fix)
- Time_Tracking: 7/14 + abort → resume #1 = 5 BLs + abort → resume #2 LIVE on BL-0014
