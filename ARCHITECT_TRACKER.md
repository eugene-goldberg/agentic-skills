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

## Batch E — I-2 structural tightening (PROPOSED 2026-05-28, awaiting authorization)

**Scope:** the overdue I-6 response to the 8-instance I-2 enforcement-gap
class. Proposed in `ARCHITECT_PLAN.md` §9.2 from `EVALUATION_2026-05-28.md`.
NOT part of the 2026-05-23 authorization — operator gate pending.

| ID | Item | Status | Commit | Verification |
|---|---|---|---|---|
| E-1 | `doctrine_spec.py` data structure (rule → enforcement_point → check → test_ref) | pending (proposed) | — | spec lists every R-rule with all four fields |
| E-2 | `test_doctrine_contract.py` CI meta-test | pending (proposed) | — | adding a rule w/o enforcement fails CI (negative control) |
| E-3 | Close R9 graph-floor gap (A8 + A11) | pending (proposed) | — | zero-`graph_*` synthetic run → floor fires |
| E-4 | Backfill R14 + layer-coverage (A36) into spec | pending (proposed) | — | R14 + A36 are first-class spec entries with checks |

**Batch E gate:**
- [ ] Meta-test bites on a rule added without enforcement
- [ ] R9 graph-floor fires on zero-`graph_*` run
- [ ] A8, A11, A36 resolved in `DESIGN_SHORTCOMINGS.md` w/ back-ref to E-1..E-4

---

## Batch G — Governance hygiene (PROPOSED 2026-05-28)

**Scope:** doc/ledger drift surfaced by `EVALUATION_2026-05-28.md`
(`ARCHITECT_PLAN.md` §9.3). Architect-owned accuracy maintenance.

| ID | Item | Status | Commit | Verification |
|---|---|---|---|---|
| G-1 | Sync `ARCHITECTURE_INVARIANTS.md` to shipped code (I-3, I-7, add R14 to I-2 table) | pending | — | doc no longer calls I-3/I-7 "missing"; R14 in table |
| G-2 | Reconcile ledger boxes (A32, A35, A37, A43 shipped but open) | pending | — | boxes ticked or annotated "shipped; box stale" |
| G-3 | Reconcile Batch-B gate boxes (below) vs sign-off prose | pending | — | gate boxes match sign-off, or sign-off downgraded |
| G-4 | Close A41/A43 observability gaps (proposals_count justification; prompt-vs-SKILLS fix) | pending | — | `proposals_count:0` event carries reasoning |

---

## Move 2 — closure_check() (I-3)

**Scope:** Strategic move proposed 2026-05-23 in the architect-prereqs strategic plan. Not part of `ARCHITECT_PLAN.md`'s four batches; tracked here because it closes A10 + foundation for A13. Operator approved 2026-05-23 evening.

**Why:** The crew gains the capacity to verify its own runs end cleanly. The 25 orphan containers reaped by hand earlier this session are exactly the gap this closes structurally.

**Items:**

| ID | Item | Status | Commit | Verification |
|---|---|---|---|---|
| M2-1 | Gate-spawned docker containers carry `agentic-skills-<run_id>-` project-name prefix (via `COMPOSE_PROJECT_NAME` env) | done | `ff04634` | `_compose_project_prefix('run-...')` returns `agentic-skills-...`; `run_gate` signature now accepts `run_id`; threaded through both engineer/qa/scorer flows |
| M2-2 | New `closure_check.py` module with scan functions (docker containers, gate worktrees; pgroup + agent branches stubbed/deferred) | done | `616e46f` | `scan_all(Path('/tmp'), 'fake-id')` returns `list[Violation]` cleanly |
| M2-3 | Hook `closure_check.scan_all` into `run_brief` post-`sprint_complete`; emit `orchestrator.closure_violation` per survivor + `closure_check.done` summary | done | `1764ab3` | placement is inside try-block (PEP 525); aborted paths deferred to future startup-scan pattern |
| M2-4 | A13 fix: orchestrator writes per-agent `phase_events.jsonl` co-located with `stream.jsonl` | done | `570b228` | `TraceWriter.write_phase_event` + `_ptag` helper; 26 inline-phase-event sites converted across 3 flows |

**Move 2 gate:**
- [x] M2-1..M2-4 land atomically — `ff04634` + `616e46f` + `1764ab3` + `570b228`
- [ ] Smoke: synthetic sprint terminate → closure_check fires, each scan returns 0 for a clean run *(requires uvicorn restart + sprint run)*
- [ ] Smoke: kill -9 mid-sprint, restart → closure_check on prior run_id emits ≥1 closure_violation *(deferred; needs M2-3b startup-scan pattern for aborted paths)*
- [x] A10 + A13 marked done in `DESIGN_SHORTCOMINGS.md`

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

*Last updated 2026-05-28 (Batch E + Batch G proposed rows added from
`EVALUATION_2026-05-28.md`). Plan is `ARCHITECT_PLAN.md`. Source-of-truth
architectural foundation: `ARCHITECTURE_INVARIANTS.md` (delivered by
Batch A).*
