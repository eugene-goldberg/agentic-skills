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
| B-1 | doctrine-meta SKILLS.md | pending | — | file exists, follows existing brownfield-role format |
| B-2 | `prompts_brownfield.py` SKILL_PATHS update | pending | — | role loadable via `_load_skill("doctrine_meta")` |
| B-3 | `_doctrine_meta_flow` in orchestrator + post-sprint hook | pending | — | synthetic sprint emits `orchestrator.doctrine_meta.*` events |
| B-4 | `POST /run-doctrine-meta` endpoint | pending | — | OpenAPI lists endpoint; invocation produces SSE |
| B-5 | `.planning/doctrine_proposals/` dir + README + gitignore | pending | — | dir tracked; non-README .md ignored |

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

## End-to-end smoke

After all four batches land, one final exercise validates the loop:

| Step | Status |
|---|---|
| Synthetic sprint completes (e.g., Sprint 4 archive) | ☐ |
| Doctrine-meta reads archive → ≥1 proposal in `.planning/doctrine_proposals/` | ☐ |
| Framework-reviewer reads the proposal → ≥1 concern in `.planning/reviews/` | ☐ |
| Observer writes first health report → no UNKNOWN events | ☐ |

---

## Issues log

(Append as encountered.)

| Date | Batch | Issue | Resolution |
|---|---|---|---|
| 2026-05-23 | pre-flight | Sprint 4 mid-flight on `sprint-2-orchestrator` | Branch off current HEAD; uvicorn in-memory code unaffected by working-tree switch |

---

## Sign-off

- [x] Batch A verified — sign: claude (Opus 4.7)  date: 2026-05-23  notes: 658dcb1 + a50026a + a2fa12a. Docs-only; Sprint 4 unaffected throughout.
- [ ] Batch B verified — sign: ____  date: ____
- [ ] Batch C verified — sign: ____  date: ____
- [ ] Batch D verified — sign: ____  date: ____
- [ ] **End-to-end smoke** — sign: ____  date: ____
- [ ] Merged back to `sprint-2-orchestrator` (or main, operator's call) — sign: ____  date: ____

---

*Last updated 2026-05-23. Plan is `ARCHITECT_PLAN.md`. Source-of-truth
architectural foundation: `ARCHITECTURE_INVARIANTS.md` (delivered by
Batch A).*
