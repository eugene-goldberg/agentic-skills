---
name: arch-active-branch
description: architect-prereqs branch tip and ABL-0014 status. As of 2026-05-31, tip is `c069082` (after this session's 10 commits); ABL-0014 Acceptance Agent shipped + calibrated + flipped to default-ON + proven in production via the health-version sprint which surfaced 3 product_bug findings per-BL QA missed.
metadata:
  type: project
---

## Current state (2026-05-31)

- **Branch:** `architect-prereqs`
- **Tip:** `c069082 docs(handoff): CONTINUATION_PROMPT for next session + A47 filed`
- **Sync:** clean — all commits this session pushed to origin
- **ABL-0014:** OPERATIONAL by default since `8499dd3` (verified by real-sprint run `run-20260531T134012Z-dd4864`)

## This session's commits (oldest → newest)

| Commit | Layer | What |
|---|---|---|
| `4a5c108` | code | ABL-0014 Batch A — skill + validator + flow skeleton + 14 tests |
| `f1bdb8b` | code | ABL-0014 Batch B — worktree + agent spawn + R10.1 retry + archive + closure_check ext + 11 tests |
| `c504e4f` | code+docs | ABL-0014 Batch C — frontend + 7 docs + memory + ABL renumber 0010→0014 |
| `f3b4a7a` | code | Drop retrieval-tools from SKILLS.md (contract gap fix) |
| `aa0e9ef` | code | Smoke-1 calibration — 5 validator gap fixes + smoke driver + /run-acceptance endpoint |
| `eb075ad` | code | Smoke-2 calibration — accept `status` as outcome synonym |
| `8499dd3` | code | **Default flipped `run_acceptance=True`** — OPERATIONAL milestone |
| `c343d87` | docs | CLAUDE.md: "Operating principle: quality over speed" (Rules 1-5) |
| `72e95d1` | docs | CLAUDE.md: Rule 6 — 95% verified/tested certainty floor |
| `514f181` | ledger | A39 39b sub-mode + HIGH escalation + A45 idle-timeout |
| `fef3284` | ledger | A46 per-BL isolation (RESOLVED by ABL-0014) |
| `c069082` | ledger+docs | A47 ScheduleWakeup/Glob bypass --allowedTools + handoff prep |

## ABL-0014 proof points (in order)

| Test | Run | Outcome |
|---|---|---|
| smoke-1 | `smoke-20260530T161537Z` | validator_ok=False (5 calibration gaps surfaced + fixed); 7 journeys, 5 passed |
| smoke-2 | `smoke-20260531T022625Z` | validator_ok=True attempts=2 (1 gap fixed); 8 journeys, 5 passed; **2 product_bug + 1 test_bug** on time-tracking |
| smoke-3 | `smoke-20260531T034747Z` | validator_ok=True attempts=1, ZERO new gaps; 7/7 passed — calibration complete |
| **REAL** `health-version` | `run-20260531T134012Z-dd4864` | both BLs merged_full; acceptance attempts=2 (R10.1 fixed validator gaps); **3 product_bug findings** (missing VersionPill.tsx); closure 0/0 leaks |

## Open work prioritized

1. Operator triage on 3 product_bug findings from health-version (BL-0003 vs accept-partial vs file-as-debt)
2. A39 immediate fix (5 worked examples; promote from HIGH to immediate)
3. ABL-0015 design (auto-dispatch follow-up engineer on `product_bug` findings)
4. CONTINUATION_PROMPT.md (this handoff — shipped)

## Other operational status

- uvicorn: running PID 65773 (restarted mid-session for default-flip load)
- Docker daemon: healthy (restarted mid-session, was throwing 500s)
- Milvus: auto-restarted by sprint's index_initial; healthy
- All worktrees clean (0 leaked)
- All docker stacks clean (only Milvus persistent)
