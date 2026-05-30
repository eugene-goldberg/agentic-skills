# Architect-Mode Prerequisites — Implementation Plan

> **Scope:** the four prerequisites named in conversation as necessary for
> Claude to operate at full-architect level on this product. Operator
> authorized all four on 2026-05-23.
>
> **Branch:** `architect-prereqs` off `sprint-2-orchestrator` at `710992b`.
>
> **North star:** the framework should harden itself across sprints without
> requiring the operator + me to manually catch every new shortcoming. The
> patterns we ship in this branch make ABL-0003 / ABL-0009 deliverable and
> close the structural gap noted in the "tactical vs. architect" exchange.

> **Status banner (2026-05-28):** Batches **A** + **B** + **Move 2** landed;
> Batches **C** + **D** not started. A findings-driven amendment (proposed
> **Batch E** + governance hygiene) was appended in **§9** following the
> 2026-05-28 project evaluation (`EVALUATION_2026-05-28.md`). Batch E is
> **proposed, awaiting operator authorization** — it is not part of the
> original four batches authorized 2026-05-23. See §9 for the full findings
> mapping.

---

## 0. Pre-flight

Already met:
- `sprint-2-orchestrator` carries the 18-item hardening pass + A8 ledger.
- No uvicorn restart required during this work (Sprint 4 is mid-flight; we
  do not touch the running process).
- All changes land on `architect-prereqs`; merge-back is operator-gated
  after Sprint 4 completes.

---

## 1. Items + ordering

Four atomic batches. Each independently revertible.

| Batch | Theme | Risk | Touches | Independent? |
|---|---|---|---|---|
| **A** | Architectural memory artifacts | Near-zero | New docs + `.claude/memory/` | Yes |
| **B** | Doctrine-meta-agent (ABL-0003) | Medium | New role, new flow hook, new validator | Depends on A's invariants doc |
| **C** | Framework-reviewer adversarial role | Medium | New role, new endpoint | Pairs with B (sibling) |
| **D** | Scheduled observer | Low | New script + cron template | Yes |

Sequencing: A → B → C → D. A is foundational (it names the invariants the
later three operate against). B and C are siblings (both new roles); B
first because it has higher leverage and tighter scope. D last because it
depends on the trace-format conventions A enshrines.

---

## 2. Batch A — Architectural memory artifacts

### A-1 — `ARCHITECTURE_INVARIANTS.md` at repo root

**Goal:** name the structural rules the system must satisfy, with each
existing A/B item back-mapped as an instance.

**Files:**
- new `ARCHITECTURE_INVARIANTS.md`

**Content (proposed sections):**
1. Resource-lifecycle invariant — every subprocess we spawn must register
   a cleanup hook; every worktree must register removal; every container
   must register stop. Back-map: B1, A9 (if added), B3, A1.
2. Doctrine-as-contract invariant — every documented R-rule maps to
   exactly one enforcement point and one test. Back-map: R5, R5b, R7,
   R8, R9, R10, R10.1, R10.2, R11, R12, Tier 1.5; missing enforcement
   = A8.
3. Closure-postcondition invariant — at run termination, the system
   asserts (not "hopes for") an empty active worktree set, empty agent
   branch set, empty active gate container set. Failures here become
   structured events, not silent leaks.
4. Single-source-of-identity invariant — `run_id` mints in exactly one
   place (router B2/B9) and threads through everything (orchestrator,
   traces, state, logs, archive). Back-map: A7 + B14 + B15 reconcile
   via this rule.
5. Truthful-outcome invariant — no aggregate label is more optimistic
   than its worst component. Back-map: A5 (engineer-merged but QA-failed
   ≠ "merged").
6. Failure-mode taxonomy invariant — every shortcoming is tagged with
   one class ∈ {race, resource-leak, silent-failure, silent-success,
   consistency-violation, enforcement-gap, starvation, data-loss}. The
   class informs the fix shape.
7. Self-hardening invariant — at sprint close, a meta-agent reads the
   sprint's traces + R-rule triggers and proposes ledger entries or
   doctrine changes. No new R-rule from a human in steady state.

**Test:** none code-side; it's a spec doc. The proof is whether subsequent
ABL-0003 + future patches reference these invariants by number.

**Effort:** ~600 LOC of markdown.
**Risk:** zero (docs only).
**Rollback:** revert one commit.

### A-2 — `.claude/memory/` architectural decision records

**Goal:** capture decisions that should survive across sessions so the
next Claude instance doesn't rebuild understanding from logs alone.

**Files:**
- new `.claude/memory/arch_invariants.md` (pointer to ARCHITECTURE_INVARIANTS.md)
- new `.claude/memory/arch_subprocess_lifecycle.md`
- new `.claude/memory/arch_doctrine_contract.md`
- new `.claude/memory/arch_closure_postconditions.md`
- new `.claude/memory/arch_run_identity.md`
- new `.claude/memory/arch_failure_taxonomy.md`
- new `.claude/memory/arch_self_hardening.md`
- update `.claude/memory/MEMORY.md` index

Each memory file uses the established format (frontmatter + body with
**Why** and **How to apply** lines). They link to the canonical doc and
to the relevant A/B item commits so future sessions can grep both
artifacts and history.

**Test:** `ls .claude/memory/arch_*.md | wc -l` returns 7; MEMORY.md
contains 7 new lines.

**Effort:** ~150 LOC across 7 small files.
**Risk:** zero.
**Rollback:** revert one commit.

### A-3 — `CONTINUATION_PROMPT.md` updates

**Goal:** ensure the next session bootstraps with the invariants doc
in its mandatory reading list.

**Files:**
- `CONTINUATION_PROMPT.md` § "Mandatory reading"

**Change:** add `ARCHITECTURE_INVARIANTS.md` as item #8 in the table.

**Effort:** ~5 LOC.
**Risk:** zero.

### Batch A verification

- [ ] `ARCHITECTURE_INVARIANTS.md` exists with all 7 invariants populated.
- [ ] 7 new files under `.claude/memory/arch_*.md`.
- [ ] `MEMORY.md` index updated.
- [ ] `CONTINUATION_PROMPT.md` cites the new doc.
- [ ] No code paths touched (imports + uvicorn unaffected).

---

## 3. Batch B — Doctrine-meta-agent (ABL-0003)

### B-1 — Role doctrine file

**Goal:** establish the meta role's SKILLS.md the same way PO/Engineer/QA
have one.

**Files:**
- new `skills/brownfield/brownfield-production-incremental-doctrine-meta/SKILLS.md`

**Content:** sections — Identity & Scope, Inputs (all sprint trace dirs,
scorer rubrics, R-rule trigger counts, FULL_EVENT logs), Outputs
(`.planning/doctrine_proposals/<sprint>-<topic>.md` with motivation +
evidence count + proposed change), Required Completion Steps (commit
proposal file + JSON summary), Constraints (must cite trace paths;
must NOT auto-merge proposals; operator approval required).

**Effort:** ~200 LOC.
**Risk:** low (additive role, opt-in invocation).

### B-2 — `prompts_brownfield.py` wiring

**Goal:** load the new role's SKILLS.md through the cached loader.

**Files:**
- `webapp/backend/app/services/prompts_brownfield.py`

**Change:** add `"doctrine_meta": SKILLS_DIR / "brownfield-production-incremental-doctrine-meta" / "SKILLS.md"` to `SKILL_PATHS`.

**Effort:** ~2 LOC.

### B-3 — `_doctrine_meta_flow` in orchestrator

**Goal:** flow function that spawns the meta-agent, reads the proposal
artifact, validates it (must cite at least one trace path), and reports
the proposal count via an SSE event.

**Files:**
- `webapp/backend/app/services/orchestrator.py`

**Changes:**
- new `_doctrine_meta_flow(repo_dir, repo_name, run_id, timeout, rk_builder)`
- emits `orchestrator.doctrine_meta.start`, `.done`, `.proposals` events
- the flow opens trace dirs under `traces_archive/<run_id>/`,
  passes summary stats into the meta-agent prompt
- runs AFTER sprint_complete (NOT after aborted; rationale: meta needs a
  complete sprint to draw conclusions)
- new request flag `run_doctrine_meta: bool = True` (default on, opt-out
  via flag for short test runs)

**Effort:** ~120 LOC.
**Risk:** medium (touches the run_brief generator; protected by being
strictly after the existing sprint_complete yield).

### B-4 — New endpoint `/run-doctrine-meta`

**Goal:** allow operator to invoke the meta-agent against any past run
without re-running the whole sprint.

**Files:**
- `webapp/backend/app/routers/projects.py`

**Change:** new `POST /api/projects/<repo>/run-doctrine-meta {run_id}` —
reads `traces_archive/<run_id>/`, runs `_doctrine_meta_flow`, returns SSE
stream.

**Effort:** ~40 LOC.
**Risk:** low (additive endpoint; runs against archived data only).

### B-5 — `.planning/doctrine_proposals/` directory + README

**Goal:** stable home for proposals. Gitignored content; tracked dir.

**Files:**
- new `.planning/doctrine_proposals/.gitkeep`
- new `.planning/doctrine_proposals/README.md` explaining the format
- `.gitignore` entry to ignore `*.md` here except README + .gitkeep

**Effort:** ~30 LOC of doc.

### Batch B verification

- [ ] Unit smoke: stub agent run with synthetic trace dirs → meta-agent
      produces a proposal file with cited paths.
- [ ] OpenAPI exposes `/run-doctrine-meta`.
- [ ] `run_brief` emits `orchestrator.doctrine_meta.*` events post-
      sprint_complete when the new flag is true.
- [ ] Backend imports clean; uvicorn restart (after Sprint 4 done) brings
      the new path live.

---

## 4. Batch C — Framework-reviewer adversarial role

### C-1 — Role doctrine file

**Goal:** sibling of doctrine-meta but inward-facing: reads a plan or
proposal, tries to break it, writes a structured concerns artifact.

**Files:**
- new `skills/brownfield/brownfield-production-incremental-framework-reviewer/SKILLS.md`

**Content:** identity (adversarial; assume the proposal is wrong; find
where), inputs (plan file path OR commit range), outputs
(`.planning/reviews/<id>.md` with concerns categorized as
blocker/concern/nit), constraints (must cite a counter-example for any
"blocker"; nits are advisory).

**Effort:** ~200 LOC.

### C-2 — Wiring (mirror of B-2)

**Files:** `prompts_brownfield.py` adds `"framework_reviewer"` entry.

**Effort:** ~2 LOC.

### C-3 — `_framework_reviewer_flow` + endpoint

**Goal:** invokable against `IMPLEMENTATION_PLAN.md`-style docs OR against
doctrine proposals from B-3.

**Files:**
- `webapp/backend/app/services/orchestrator.py` — new flow
- `webapp/backend/app/routers/projects.py` — new `POST /run-framework-review {plan_path}`

**Effort:** ~150 LOC.

### C-4 — Pre-commit integration (optional, opt-in)

**Goal:** any commit that adds/edits a file under `.planning/proposals/`
or any new `IMPLEMENTATION_PLAN*.md` triggers a framework review by
default.

**Files:**
- new `scripts/pre-commit-framework-review.sh` (operator opts in via
  `git config core.hooksPath`)

**Effort:** ~50 LOC.

### Batch C verification

- [ ] Synthetic plan with an obvious flaw → reviewer flags it as a blocker.
- [ ] `/run-framework-review` endpoint live.
- [ ] Reviewer never auto-blocks merges (advisory by default).

---

## 5. Batch D — Scheduled observer

### D-1 — `observer.py` script

**Goal:** runs unattended (via cron / launchd / scheduled task); reads
the most-recent `traces_archive/<run_id>/`, computes health metrics,
appends to a rolling report at `webapp/backend/logs/observer/health-<YYYY-WW>.md`.

**Files:**
- new `webapp/backend/scripts/observer.py`

**Metrics emitted:**
- BLs per outcome class
- mean retrieval calls per role
- doctrine retry rate
- gate failure rate (with regression-test list)
- A/B item trigger counts (e.g., "B12 fired N times")
- new event phases not in the WORKFLOW.md taxonomy (alert if any)

**Effort:** ~150 LOC.

### D-2 — Cron template + doc

**Goal:** make the install path obvious; do not auto-install.

**Files:**
- new `SCHEDULING.md` at repo root with sample cron entries + launchd
  plist + Windows Task Scheduler XML

**Effort:** ~80 LOC of doc.

### D-3 — Health-report taxonomy

**Goal:** observer alerts feed back into ledger candidates.

**Convention:** if observer finds a NEW event phase, NEW failure pattern
(3+ occurrences), or a metric drift >20% week-over-week, it appends a
"candidate shortcoming" section to the health report. Operator triages
into DESIGN_SHORTCOMINGS.md.

**Effort:** included in D-1.

### Batch D verification

- [ ] `observer.py` runs against `traces_archive/<run_id>/` and produces
      a health-<week>.md file.
- [ ] No new event phase in the current archived run (which is the
      negative-control case).
- [ ] Cron template documented; not auto-installed.

---

## 6. Risk register

| Risk | Mitigation | Detection |
|---|---|---|
| New meta-agent loops endlessly | timeout_per_role respected; idle_timeout enforced via B5 | trace's `_meta phase=idle_timeout` fires |
| Reviewer over-blocks legitimate proposals | advisory-only by default; pre-commit hook is opt-in | operator override at any time |
| Observer accumulates disk usage | rolling weekly file; cap retention to 12 weeks in observer.py | `du -sh webapp/backend/logs/observer/` should stay <50 MB |
| ABL-0003 invocation creates feedback loop with framework changes | proposals are docs, not auto-merged; operator gates | proposals reside in `.planning/`, never in code |
| Memory files drift from canonical docs | every memory file has a 1-line "Source:" pointer; if source path 404s, memory is stale | new observer check: validate Source: paths still exist |

---

## 7. Done criteria

This plan is complete when:

- [ ] All 13 sub-items above land on `architect-prereqs`.
- [ ] One end-to-end run: a synthetic sprint completes → doctrine-meta
      writes ≥1 proposal → framework-reviewer flags ≥1 concern on the
      proposal → observer writes its first health report.
- [ ] `MEMORY.md` index lists all 7 new arch memories.
- [ ] Operator merges `architect-prereqs` back to `sprint-2-orchestrator`
      (or to main, operator's call) after review.

Then the framework can begin self-hardening at sprint-close instead of
requiring me + operator to catch every new shortcoming by hand.

---

## 8. What's still beyond me even after this lands

Honest acknowledgment from the earlier exchange:

- I am still invoked per-turn; I do not run between turns. The observer
  delegates the always-on observation to a scheduler (cron / launchd) —
  which IS always-on. I designed around the residual, but the residual
  is real.
- The doctrine-meta agent proposes; the operator approves. This is
  intentional. Auto-applying doctrine changes would risk runaway
  self-modification. The proposal-review loop preserves operator
  authority.

Both of these are features, not bugs, of the architecture this plan
enshrines.

---

## 9. Findings-driven amendment (2026-05-28)

Source: `EVALUATION_2026-05-28.md` — objective assessment of the project
against the thesis's own definition-of-done. This section translates the
evaluation's findings into plan items. Original Batches A–D are unchanged
above; this is additive.

### 9.1 Current execution state

| Unit | State | Evidence / open gap |
|---|---|---|
| Batch A (memory/invariant artifacts) | ✅ done + verified | `658dcb1`, `a50026a`, `a2fa12a` |
| Batch B (doctrine-meta-agent) | ✅ done, **with open gaps** | smoke-verified on one archive; A41 (prompt-vs-SKILLS contradiction + 0-proposals observability), A43 (false-evidence) open; tracker Batch-B gate boxes unticked despite sign-off prose |
| Move 2 (closure_check / I-3) | ✅ done, 2 smokes deferred | `ff04634`, `616e46f`, `1764ab3`, `570b228` |
| Batch C (framework-reviewer) | ⬜ not started | the adversarial check on meta-agent proposals — currently proposals reach the operator **unchallenged** |
| Batch D (scheduled observer) | ⬜ not started | the only always-on component; the piece that removes the per-turn bottleneck |

The self-hardening loop the plan defines as "done" (propose → adversarially
review → continuously observe) is **open at two of four stations** (C, D).

### 9.2 Batch E — I-2 structural tightening *(PROPOSED — awaiting operator authorization)*

**Why now:** the I-2 (doctrine-enforcement-gap) failure class has **8
instances** (A8, A11, A12, A16, A36, A39, A40, A41) — well past the I-6 `>3`
threshold that obligates the architect to propose *tightening the invariant*
rather than another per-site patch. The open cluster (R9 enforcement =
A8+A11; layer-coverage = A36) is still being handled per-site. This is the
single highest-value architect move available and is overdue by project
doctrine. `ARCHITECTURE_INVARIANTS.md` already mandates this machinery under
"Architectural mandate"; it was never built.

| ID | Item | Goal | Files | Effort | Risk | Rollback |
|---|---|---|---|---|---|---|
| E-1 | Doctrine-spec data structure (in code, not prose) | One source of truth: each rule → `{id, floor, enforcement_point, check_callable, test_ref}`. Documentation alone stops being "enforcement." | new `webapp/backend/app/services/doctrine_spec.py` | ~150 LOC | low (additive; nothing reads it until E-2/E-3 wire in) | revert one commit |
| E-2 | CI meta-test | Assert every doctrine entry has an enforcement point AND a callable check AND a test_ref. Adding a rule without enforcement **fails CI**. Makes I-2 self-policing. | new `webapp/backend/tests/test_doctrine_contract.py` | ~80 LOC | low | revert one commit |
| E-3 | Close R9 enforcement gap (A8 + A11) | Wire a `graph_*`-call floor (≥1) into the spec + streaming check, same shape as R5/R8. Retires the "advisory only" status. | `streaming` enforcement site + `doctrine_spec.py` | ~60 LOC | medium (touches the live streaming kill path) | feature-flag the floor; revert |
| E-4 | Backfill R14 + layer-coverage (A36) into the spec | R14 (pytest-timeout) and the PO layer-coverage requirement become first-class spec entries with checks, not prose in SKILLS.md only. | `doctrine_spec.py` + PO post-validation | ~80 LOC | medium | revert |

**Batch E gate:**
- [ ] `test_doctrine_contract.py` fails when a rule is added without an enforcement point (negative-control proves the gate bites).
- [ ] R9 graph-floor fires on a synthetic run with zero `graph_*` calls.
- [ ] A8, A11, A36 marked resolved in `DESIGN_SHORTCOMINGS.md` with back-reference to E-1..E-4.

### 9.3 Batch G — Governance hygiene *(PROPOSED)*

The evaluation surfaced doc/ledger drift the architect is obligated to keep
accurate (CLAUDE.md responsibility #5).

| ID | Item | Detail |
|---|---|---|
| G-1 | Sync `ARCHITECTURE_INVARIANTS.md` to code | It is stamped 2026-05-23 and now lags the code: I-3 (`closure_check.py`) and I-7 (doctrine-meta-agent) both shipped but are still described as "missing/aspirational"; **R14 is absent from the I-2 table entirely.** Update to reflect shipped state. (Stale doctrine doc is itself an I-2 violation.) |
| G-2 | Reconcile ledger boxes | A32, A35, A37, A43 have fixes shipped (per commits) but open `[ ]` boxes — makes open-count read worse than reality (~17 genuinely open vs 19 by box). Tick or annotate "shipped; box stale." |
| G-3 | Reconcile Batch-B gate boxes | `ARCHITECT_TRACKER.md` Batch-B gate (lines 55–57) is unticked though the sign-off prose claims end-to-end smoke validation. Tick to match, or downgrade the sign-off to "smoke-only." |
| G-4 | Close A41/A43 observability gaps | Make the doctrine-meta `proposals_count:0` event carry a justification (so "0 = nothing to say" is distinguishable from "0 = silent failure"); fix the prompt-vs-SKILLS commit contradiction (A41). A43 Layer-1 shipped; Layer-2 remains deliberately deferred (n=1). |

### 9.4 Capability gaps beyond this branch (forward pointer)

These are **not** architect-prereqs work (they belong to `BACKLOG.md` /
the sprint plan), but the evaluation elevates their priority and the
sequencing matters:

- **ABL-0002 Triage agent** and **ABL-0004 Escalation Bridge** are the two
  unbuilt components that most directly remove the human. Today's
  "self-correction" is hardcoded retry (R10/R10.1/R10.2), not a judging
  agent that decides retry / rewrite / defer / split / escalate. This caps
  the *self-correcting* property at "half."
- **ABL-0007 Cross-project memory** is the weakest crew property
  (*cumulative*): what's learned on one target does not yet carry to the
  next as a crew capability — it's carried by the architect + ledger by hand.
- **Sequencing implication:** **Batch C (framework-reviewer) should land
  before** the doctrine-meta-agent's proposals are trusted unsupervised —
  A43 proved a proposal can be confidently wrong and only operator forensics
  caught it. C is the structural adversarial check that closes that loop.

### 9.6 Batch H — ABL-0014 Acceptance Agent (added 2026-05-30)

Stand-alone batch landed mid-stream after operator approval. Closes A45
(per-BL isolation prevents cross-component bug recovery) by introducing
an acceptance pass that runs once at `sprint_complete` against the
assembled feature with seeded multi-user state and exercises end-to-end
user journeys via playwright with full-page screenshots. Read-only on
code; advisory-only on the sprint (§E.1 Q3 — never aborts).

**Status:**
- Batch A (skill loader + validator + flow skeleton + 14 tests) — SHIPPED `4a5c108`
- Batch B (worktree + agent spawn + R10.1 retry + archive + closure_check extension + 11 new tests) — SHIPPED `f1bdb8b`
- Batch C (frontend + 7 docs + memory flips) — IN FLIGHT
- ABL-0015 (auto-dispatch follow-up engineer on `product_bug`) — deferred to its own ABL

Full deliverable + test matrix + operator-locked answers to the 7 §E.1
blocking questions live in `ABL-0014_ACCEPTANCE_AGENT_IMPLEMENTATION.md`.

**Calibration plan:** `run_acceptance=False` default for first 3 sprints;
flip after FP-rate is verified low.

---

### 9.5 Operator decisions required

1. **Resolve the success-metric contradiction.** `THESIS.md` §7 names
   *operator-time < 1 hr* as THE "Success metric"; `CLAUDE.md` +
   `arch_mission_framing.md` demote it to "a thermometer, not the patient."
   The two governing docs disagree on what "done" means. Architect needs one
   authoritative definition to score against.
2. **Authorize (or decline) Batch E and Batch G.** Batch E is the overdue
   I-6 structural response; Batch G is governance hygiene. Neither is in the
   original 2026-05-23 authorization.
3. **Confirm Batch C/D priority** vs. pausing the prereqs branch to build
   ABL-0002/0004 — i.e., finish the *self-hardening* loop first, or pivot to
   the *autonomy* agents that most move the thesis.

---

*Authored 2026-05-23. §9 amendment appended 2026-05-28 from
`EVALUATION_2026-05-28.md`. Companion: `ARCHITECT_TRACKER.md`. Architectural
foundation: `ARCHITECTURE_INVARIANTS.md` (delivered by Batch A).*
