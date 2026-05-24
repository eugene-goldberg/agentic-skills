# Architect-Mode Prerequisites — Implementation Tracker

> Live status of `ARCHITECT_PLAN.md`. Update only this file as work lands.

**Plan version:** 2026-05-23 v1
**Branch:** `architect-prereqs` (forked from `sprint-2-orchestrator` @ `710992b`)
**Operator authorization:** all four items approved 2026-05-23.

---

## Status legend

`pending` · `in_progress` · `done` · `blocked` · `deferred` · `reverted`

---

## Pre-flight gate

| Check | Status | Notes |
|---|---|---|
| Branch created | ☑ | `architect-prereqs` off `710992b` |
| Sprint 4 unaffected | ☑ | launcher PID 14719 still alive; uvicorn in-memory code unchanged |
| ARCHITECT_PLAN.md committed | ☐ | this batch |

---

## Batch A — Architectural memory artifacts

**Commit style:** atomic per sub-item.

| ID | Item | Status | Commit | Verification |
|---|---|---|---|---|
| A-1 | `ARCHITECTURE_INVARIANTS.md` at repo root (7 invariants) | done | `658dcb1` | 371 LOC; back-maps 21 A/B items |
| A-2 | 7 architectural memory files + MEMORY.md index update | done | `a50026a` | `ls .claude/memory/arch_*.md \| wc -l` = 7; index has 7 new lines |
| A-3 | CONTINUATION_PROMPT.md cites invariants doc | done | `a2fa12a` | mandatory-reading bumped from 7 to 8 |

**Batch A gate:**
- [x] All 3 files committed
- [x] No code paths touched
- [x] No uvicorn restart needed (Sprint 4 unaffected)

---

## Batch B — Doctrine-meta-agent (ABL-0003)

| ID | Item | Status | Commit | Verification |
|---|---|---|---|---|
| B-1 | doctrine-meta SKILLS.md | done | `c65ff09` | 166 LOC; follows brownfield-role format with forbidden_targets safeguard |
| B-2 | `prompts_brownfield.py` SKILL_PATHS update | done | `9ec64c6` | `_load_skill('doctrine_meta')` returns 9294 chars |
| B-3 | `_doctrine_meta_flow` in orchestrator + post-sprint hook | done | `0cdfec7` | 131 LOC; hook between `sprint_complete` yield and outer finally |
| B-4 | `POST /run-doctrine-meta` endpoint | done | `47e7157` | OpenAPI now lists `/api/projects/{repo}/run-doctrine-meta`; `run_doctrine_meta` flag added to `RunBriefRequest` |
| B-5 | `.planning/doctrine_proposals/` dir + README + gitignore | done | `d5c17f3` | dir tracked via `.gitkeep`; non-README `*.md` ignored |

**Batch B gate:**
- [ ] Unit smoke: synthetic trace dirs → proposal file written with ≥1 cited trace path
- [ ] Backend imports clean
- [ ] `run_brief` post-sprint_complete flow emits new events

---

## Batch C — Framework-reviewer adversarial role

| ID | Item | Status | Commit | Verification |
|---|---|---|---|---|
| C-1 | framework-reviewer SKILLS.md | pending | — | file exists |
| C-2 | `prompts_brownfield.py` wiring | pending | — | `_load_skill("framework_reviewer")` works |
| C-3 | `_framework_reviewer_flow` + `POST /run-framework-review` | pending | — | endpoint live; produces concerns artifact |
| C-4 | Pre-commit hook script (opt-in) | pending | — | script lints; not auto-installed |

**Batch C gate:**
- [ ] Synthetic plan with planted flaw → reviewer flags blocker
- [ ] Reviewer never auto-blocks (advisory only)

---

## Batch D — Scheduled observer

| ID | Item | Status | Commit | Verification |
|---|---|---|---|---|
| D-1 | `observer.py` script | pending | — | runs against `traces_archive/<run_id>/` and produces health report |
| D-2 | `SCHEDULING.md` cron / launchd / Task Scheduler templates | pending | — | doc lints; entries documented but not auto-installed |
| D-3 | Health-report "candidate shortcoming" detection | pending | — | observer flags any new event phase not in WORKFLOW.md taxonomy |

**Batch D gate:**
- [ ] Health report file produced
- [ ] Cron sample documented
- [ ] Disk-usage cap enforced (rolling 12 weeks)

---

## Move 2 — closure_check() (I-3)

**Scope:** Strategic move proposed 2026-05-23 in the architect-prereqs strategic plan. Not part of `ARCHITECT_PLAN.md`'s four batches; tracked here because it closes A10 + foundation for A13. Operator approved 2026-05-23 evening.

**Why:** The crew gains the capacity to verify its own runs end cleanly. The 25 orphan containers reaped by hand earlier this session are exactly the gap this closes structurally.

**Items:**

| ID | Item | Status | Commit | Verification |
|---|---|---|---|---|
| M2-1 | Label gate-spawned docker containers with `agentic-skills.run_id=<run_id>` | pending | — | `docker ps --filter label=agentic-skills.run_id=<id>` returns the gate's containers; existing unlabeled containers ignored |
| M2-2 | New `closure_check.py` module with scan functions (pgroup survivors, stale worktrees, agent branches, docker containers); no integration yet | pending | — | `python -c "from app.services import closure_check; closure_check.scan_all('fake-run-id')"` returns a `list[Violation]` |
| M2-3 | Hook `run_closure_check` into `run_brief` outer finally; emit `orchestrator.closure_violation` per survivor | pending | — | kill -9 mid-run → next run's start finds violations from prior `run_id` and emits SSE events |
| M2-4 | A13 fix: orchestrator writes per-agent `phase_events.jsonl` co-located with `stream.jsonl` | pending | — | doctrine_check, regression_gate, pregrounding events appear in the per-agent trace dir, not just orchestrator stream |

**Move 2 gate:**
- [ ] M2-1..M2-4 land atomically
- [ ] Smoke: synthetic sprint terminate → closure_check fires, each scan returns 0 for a clean run
- [ ] Smoke: kill -9 mid-sprint, restart → closure_check on prior run_id emits ≥1 closure_violation
- [ ] A10 + A13 marked done in `DESIGN_SHORTCOMINGS.md`

---

## End-to-end smoke

After all four batches land, one final exercise validates the loop:

| Step | Status |
|---|---|
| Synthetic sprint completes (e.g., Sprint 4 archive) | ☑ (Sprint 4 archive `run-20260523T212548Z-5bfff3` used; 11 trace dirs) |
| Doctrine-meta reads archive → ≥1 proposal in `.planning/doctrine_proposals/` | ☑ (smoke1: 2 valid proposals; smoke2 after A12+A14 fixes: 0 — also correct, "silence is correct when nothing to say"; both runs verified `forbidden_tools` held) |
| Framework-reviewer reads the proposal → ≥1 concern in `.planning/reviews/` | ☐ (pending Batch C) |
| Observer writes first health report → no UNKNOWN events | ☐ (pending Batch D) |

---

## Issues log

(Append as encountered.)

| Date | Batch | Issue | Resolution |
|---|---|---|---|
| 2026-05-23 | pre-flight | Sprint 4 mid-flight on `sprint-2-orchestrator` | Branch off current HEAD; uvicorn in-memory code unaffected by working-tree switch |

---

## Sign-off

- [x] Batch A verified — sign: claude (Opus 4.7)  date: 2026-05-23  notes: 658dcb1 + a50026a + a2fa12a. Docs-only; Sprint 4 unaffected throughout.
- [x] Batch B verified — sign: claude (Opus 4.7)  date: 2026-05-23  notes: c65ff09 + 9ec64c6 + 0cdfec7 + 47e7157 + d5c17f3. **Smoke validated end-to-end:** smoke1 produced 2 valid proposals against Sprint 4 archive (A12, A13 surfaced by the agent itself; A14 surfaced by my review pass). Smoke2 (after A12+A14 SKILLS.md fixes landed at d126bd4) correctly produced 0 proposals — agent recognized A12/A13/A14 in ledger and applied "silence is correct" discipline. Forbidden-tools constraint held in both runs (smoke2 explicitly refused `git add`/`git commit` per SKILLS.md). I-7 self-hardening loop closed and validated.
- [ ] Batch C verified — sign: ____  date: ____
- [ ] Batch D verified — sign: ____  date: ____
- [ ] **End-to-end smoke** — sign: ____  date: ____
- [ ] Merged back to `sprint-2-orchestrator` (or main, operator's call) — sign: ____  date: ____

---

*Last updated 2026-05-23. Plan is `ARCHITECT_PLAN.md`. Source-of-truth
architectural foundation: `ARCHITECTURE_INVARIANTS.md` (delivered by
Batch A).*
