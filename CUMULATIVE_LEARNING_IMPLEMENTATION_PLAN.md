# Cumulative Learning — comprehensive implementation plan

> **Status: program plan, operator approval required per stage before
> implementation.** Author: architect. Date: 2026-06-03.
> Branch: `cumulative_learning`.
>
> This is the master implementation plan for the mission's **cumulative**
> property — "what's learned on one target carries forward." It sequences
> the four-stage strategy in [`CUMULATIVE_LEARNING_ROADMAP.md`](CUMULATIVE_LEARNING_ROADMAP.md)
> into an executable ABL program (ABL-0016 → ABL-0019), with shared
> architecture, per-stage batches, tests, invariant posture, risk, and a
> verification gate at the head of every stage that isn't yet fully
> seam-verified.
>
> **Fidelity discipline (CLAUDE.md Rule 6):** Stage 1 is fully
> seam-verified (file:lines confirmed). Stages 2–4 are design-grounded in
> components confirmed to exist but each opens with a **Batch 0
> verification gate** before any code — the same discipline that turned
> Stage 1 from sketch into [`ABL-0016`](ABL-0016_LESSONS_AS_CONTEXT.md).
> Every later-stage file:line is a **candidate** until its Batch 0 confirms
> it. Markers: ✅ verified · 🔎 to-verify (Batch 0) · ✎ design decision.

---

## 0. Definition of done

The feature is done when the crew **reads** prior experience at decision
time, **measures** whether acting on it helped, and **carries** the
generalizable part to new targets — without auto-applying anything that
should stay operator-gated.

Concretely, all four must hold:

1. Every role consults relevant prior lessons before acting (read path). — *Stage 1*
2. The crew measures whether an enforced rule actually reduced its target failure class (closed loop). — *Stage 2*
3. A fresh target inherits target-agnostic doctrine + failure priors on day one (cross-target transfer). — *Stage 3*
4. Pattern Fidelity compounds: each sprint seeds the next sprint's pattern matching on that target. — *Stage 4*

Tracked against the mission's "cumulative" property, currently the least
mature of the four defining properties (the "crew brain").

---

## 1. The program at a glance

| Stage | ABL | Capability gained | Depends on | Fidelity | Est. |
|---|---|---|---|---|---|
| 1 | **ABL-0016** Lessons-as-context | all roles read prior confirmed lessons | §I.3 ledger ✅ | ✅ seam-verified | A+B ~1–1.5d + smoke |
| 2 | **ABL-0017** Closed-loop doctrine efficacy | crew measures which of its rules help | ABL-0003 doctrine-meta ✅; Stage-1 provenance | 🔎 Batch 0 | ~3–4d |
| 3 | **ABL-0018** Cross-target transfer | new target inherits global doctrine + priors | Stages 1–2 substrate | 🔎 Batch 0 | ~3–5d |
| 4 | **ABL-0019** Pattern/convention profile | Pattern Fidelity compounds per target | Stage 1 substrate | 🔎 Batch 0 | ~3–4d |

**Sequencing rule:** Stage 1 is the foundation — it builds the lessons
substrate + the read path + the provenance hook that Stages 2–4 write into
and read from. **Do Stage 1 fully (incl. its calibration smoke) before
starting Stage 2.** Stages 3 and 4 both depend on Stage 1 only and could
run in parallel after Stage 2, but serial is safer (one calibration at a
time).

```
ABL-0016 (Stage 1) ──┬──> ABL-0017 (Stage 2) ──> ABL-0018 (Stage 3)
                     └────────────────────────-> ABL-0019 (Stage 4)
                        (3 & 4 depend on Stage 1 substrate; serialize for calibration)
```

---

## 2. Shared architecture (cross-cutting, owned by Stage 1)

### 2.1 The Lessons substrate — data model

A **Lesson** is a durable, advisory record the crew can consult. v1 source
is the §I.3 findings ledger (✅ exists); the model is source-agnostic so
Stages 2/4 can contribute new lesson kinds.

```
Lesson:
  lesson_id        # stable hash (reuse finding_id when sourced from ledger)
  kind             # "finding" (v1) | "gate_failure" | "doctrine_rule" | "pattern" (later)
  scope            # "target" (v1) | "global" (Stage 3)
  target_key       # md5(repo_path) or repo slug — the target it was learned on
  feature_slug     # provenance: which feature produced it
  classification   # product_bug | test_bug | ... (from ledger) or kind-specific
  summary          # the human-readable lesson
  hypothesis       # optional site pointer (file:func)
  verdict          # confirmed | deferred  (refuted/pending excluded from lessons)
  weight           # rank signal: seen_count, recency, same-feature boost
  provenance       # source finding_id / run_id / report_path
```

### 2.2 Storage layout (✎ decision)

- **Per-target lessons** (Stages 1, 4): derived live by union over the
  target's existing ledgers (`_brownfield/features/*/acceptance/findings_log.jsonl`)
  — **no new persistent store in v1**, the ledger *is* the store. Stage 4
  adds a per-target `pattern_profile.md` consolidated from eng_patterns.
- **Global crew memory** (Stage 3): a new store **outside** any target
  repo (targets are not ours to commit) — proposed
  `~/.cache/agentic-skills/crew-memory/` (mirrors the graphify cache
  convention) holding target-agnostic doctrine + failure-class priors.
  ✎ Operator decision on location at Stage 3 Batch 0.
- **Efficacy records** (Stage 2): appended to the run's orchestrator state
  / a `.planning/doctrine_efficacy.jsonl` 🔎 (Batch 0 confirms the seam).

### 2.3 Governing discipline (applies to every stage)

- **Doctrine stays operator-gated forever** (I-7: propose, never
  auto-merge). Stage 2 measures efficacy and *proposes* retirement; it
  never auto-retires a rule.
- **Lessons are advisory, never binding** — evidence the agent weighs
  against its own grounding ("falsification priors, not bans," the §I.3
  framing). This is what lets the read path be lower-risk than doctrine.
- **Flag discipline** — every stage ships behind a default-OFF flag and
  flips only after a live calibration smoke, consistent with
  `run_acceptance`, `inject_acceptance_priors`, `run_acceptance_followup`.
- **Provenance for everything** — any lesson/prior that influences an
  action is logged with its source id, so Stage 2 can attribute outcomes.

### 2.4 Invariant posture (whole feature)

- **I-2 (doctrine contract):** lessons/priors are advisory context — **no
  new R-rule**. The one place a rule *could* arise is Stage 2's
  efficacy-driven retirement, which routes through the existing
  propose-only doctrine-meta path (no new enforcement primitive).
- **I-4 (run identity):** every lesson carries source `finding_id`/`run_id`;
  every efficacy record is keyed by `run_id`.
- **I-1/I-3 (subprocess/closure):** zero impact for Stages 1, 2, 4 (pure
  reads + prompt assembly + record appends). Stage 3's global store is
  read/written outside sprint subprocesses — no worktree/docker surface.
- **I-7 (self-hardening):** Stage 2 is the *closure* of I-7 — it adds the
  missing feedback measurement to the propose loop.

### 2.5 Test strategy (whole feature)

- Pure helpers (readers, renderers, selectors, efficacy calculators) are
  unit-tested with synthetic ledgers/traces on `tmp_path` — no subprocess,
  no docker (the ABL-0015 testing model).
- Wiring is covered by signature/source-inspection tests (the
  `test_followup_flag_wiring` model).
- Behavioral flows are covered with faked agent/engineer flows.
- Each stage's live calibration smoke is operator-gated and is the only
  step requiring a real sprint.
- Run scoped: `cd webapp/backend && python3 -m pytest tests/`.

---

## 3. Stage 1 — ABL-0016 Lessons-as-context  ✅ seam-verified

Full detail in [`ABL-0016_LESSONS_AS_CONTEXT.md`](ABL-0016_LESSONS_AS_CONTEXT.md).
Summary here for program completeness.

**Goal:** surface prior `confirmed`/`deferred` findings to all four
brownfield roles as advisory context. Closes the read-path gap.

**Verified seams:** four `build_*` call sites pass `repo_dir`+`feature_slug`
(orchestrator.py:290/422/574/576); injection points in
`prompts_brownfield.py` (`:124/:286/:430/:526`); `_build_priors_block`
(orchestrator.py:962-1023) is the template; v1 is **target-scoped** (union
across feature ledgers) and **Option A** (prompt injection, Option B Milvus
deferred to Stage 1.5).

**Batches:**
- **A** — `lessons.py`: `list_lessons(repo_dir, feature_slug=None)`
  (target-scoped union, verdict filter, dedup, rank) + `render_lessons_block`
  (silent-empty). Dormant. Unit-tested.
- **B** — `inject_lessons: bool = False` plumbed request → `run_brief` →
  4 `build_*` calls; block threaded into the 4 brownfield builders.
  Wiring + per-role injection tests.
- **C** — provenance logging (writes which lessons were injected, keyed by
  run_id/role/bl_id — **this is the hook Stage 2 consumes**) + operator
  calibration smoke + flag-flip proposal.

**Deferred from Stage 1:** Option B semantic lessons retrieval (Stage 1.5);
lesson sources beyond the ledger (Stages 2/4 add them).

---

## 4. Stage 2 — ABL-0017 Closed-loop doctrine efficacy  🔎

**Goal:** make I-7 self-hardening *closed-loop*. Today doctrine-meta
proposes rules from sprint evidence (open loop); nothing measures whether
an enforced rule actually reduced the failure class it targeted. Add
**outcome attribution** + **rule-efficacy tracking** so rules that don't
help get flagged for retirement (proposal only — never auto-retired).

### Batch 0 — verification gate (🔎 do first)
Confirm, with file:lines, before any code:
1. Where per-BL outcomes are persisted — the `run_brief` `summary` dict and
   `.orchestrator-state/<run_id>.json` (A7 disk state); the terminal event
   shapes (`_orchestrator_outcome` merged/no_op ✅ known; `regression_gate`
   kind, `awaiting_review` reason, acceptance findings).
2. The doctrine-meta input contract — what it reads from
   `traces_archive/<run_id>/` and writes to `.planning/doctrine_proposals/`
   (ABL-0003 / `_doctrine_meta_flow`).
3. Which "active rules" are knowable per run — how enforced R-rules are
   recorded per sprint (doctrine-spec data structure, I-2) so a rule can be
   correlated with subsequent outcomes.

### Batch A — outcome attribution
- Define a per-BL **outcome label**: `clean_merge | gate_retry |
  awaiting_review | acceptance_caught_bug | no_op`, derived from the
  existing terminal events. Persist one record per BL per run
  (`outcome_log.jsonl` keyed by run_id/bl_id) ✎.
- Pure deriver `classify_bl_outcome(events) -> label`, unit-tested against
  recorded event sequences (incl. the BL-0009 transient-regression case).

### Batch B — rule-efficacy index
- For each enforced rule, aggregate the outcome distribution of BLs run
  while it was active, across runs on a target. `rule_efficacy(rule_id)
  -> {targeted_failure_rate_before, after, n}` ✎.
- A rule whose targeted failure class did **not** drop after N post-enforce
  BLs is flagged `low_efficacy`.

### Batch C — efficacy → doctrine-meta retirement proposals
- Extend `_doctrine_meta_flow` to read the efficacy index and emit
  **retirement proposals** to `.planning/doctrine_proposals/` for
  `low_efficacy` rules (operator approves; never auto-retires).
- Mirrors the existing proposal schema; adds a `proposal_kind: retire`.

### Batch D — calibration
- Operator-gated: run ≥2 sprints, confirm outcome labels + efficacy index
  populate, confirm a retirement proposal is generated for a deliberately
  ineffective rule.

**Risk:** Low–medium. Read-only attribution + proposal generation; no
auto-retirement. Worst case = a noisy/incorrect retirement proposal, caught
at operator review (the I-7 gate). **Rollback:** flag-gate the efficacy
read in doctrine-meta; revert leaves the open-loop behavior intact.

---

## 5. Stage 3 — ABL-0018 Cross-target transfer  🔎

**Goal:** split the substrate into **global** (target-agnostic: doctrine
rules, failure-class priors, retrieval strategies) vs **per-target** (this
codebase's conventions/hotspots). A fresh target inherits the global layer
on day one. Makes "carries forward" literally true across orgs.

### Batch 0 — verification gate (🔎)
1. Confirm the global store location + that it is never committed to a
   target repo (✎ propose `~/.cache/agentic-skills/crew-memory/`).
2. Confirm how a sprint bootstraps on a brand-new target (the
   `RUNBOOK_clean_brownfield_reset` + init-feature path) — where a
   "inherit global priors" step would slot in.
3. Confirm which lesson kinds are safely target-agnostic (doctrine rules,
   failure-class priors) vs which must stay target-scoped (file-level
   hypotheses, pattern profiles).

### Batch A — global substrate
- `crew_memory.py`: a global store (outside any target) of
  target-agnostic lessons + accepted doctrine rules + failure-class
  priors. Promotion rule: a lesson generalizes when its **class** (not its
  site) recurs across ≥K targets ✎. Pure, unit-tested.

### Batch B — promotion path
- After a sprint, promote target-agnostic lessons (class-level) from the
  per-target store into global, **operator-gated** (same as doctrine).
  Per-target specifics never promote.

### Batch C — cold-start inheritance
- On a new target, seed the role prompts with the global failure-class
  priors + global doctrine (reuses Stage 1's `_build_lessons_block`
  pipeline, with `scope=global` lessons unioned in).

### Batch D — calibration
- Operator-gated: bootstrap a **second target** (the §I.5 Django smoke is
  the natural vehicle), confirm it inherits global priors with zero prior
  sprints of its own.

**Risk:** Medium — cross-target generalization is where false lessons do
the most damage (a lesson from target A misleading target B). Mitigations:
only **class-level** lessons promote (not site-specific), promotion is
operator-gated, lessons remain advisory. **Rollback:** disable global-scope
union in the lessons pipeline; per-target behavior unchanged.

---

## 6. Stage 4 — ABL-0019 Pattern/convention profile  🔎

**Goal:** consolidate per-BL `eng_patterns.md` into a durable per-target
**pattern profile** (layering, naming, error handling, DI idioms) that
seeds future Pattern Matching instead of re-deriving it every sprint.
Pattern Fidelity compounds.

### Batch 0 — verification gate (🔎)
1. Confirm the eng_patterns.md structure + path (✅ partially known:
   `_brownfield/<bl_id>/eng_patterns.md`, the "Pattern Matching Summary"
   template, scorer reads it) and how consistently the sections are filled.
2. Confirm the engineer prompt seam where a "prior pattern profile" block
   would slot in (reuses Stage 1's seam) and the scorer's Pattern Fidelity
   rubric input.

### Batch A — profile builder
- `pattern_profile.py`: consolidate all `eng_patterns.md` on a target into
  a deduped per-target `pattern_profile.md` (closest-analog index,
  architectural patterns, invariants, hotspots). Pure, unit-tested against
  synthetic eng_patterns sets.

### Batch B — inject into engineer (and PO) pre-work
- Surface the pattern profile via the Stage 1 lessons pipeline (a new
  lesson `kind="pattern"`) so the engineer's Pattern Matching starts from
  the accumulated profile, not from scratch.

### Batch C — refresh + calibration
- Profile refreshes after each sprint (append/dedup). Operator-gated smoke:
  run a second feature on a target, confirm the engineer's eng_patterns
  cites the inherited profile and the scorer's Pattern Fidelity reflects it.

**Risk:** Low. Additive context; advisory. **Rollback:** flag-gate the
pattern-profile lesson kind.

---

## 7. Cross-cutting plan elements

### 7.1 Flag inventory (all default OFF until per-stage smoke)
- `inject_lessons` (Stage 1)
- `track_outcomes` / efficacy read in doctrine-meta (Stage 2)
- `inject_global_priors` (Stage 3)
- `inject_pattern_profile` (Stage 4)

Each flips independently after its own calibration smoke. The feature can
ship incrementally — Stage 1 alone is a real capability gain.

### 7.2 Observability
Every injected lesson/prior and every outcome label is logged with
provenance (run_id, role, bl_id, source id) so the architect can answer
"what did the crew learn, what did it consult, and did it help" from
traces alone — closing the same diagnosability bar §I.2 raised for
acceptance.

### 7.3 Governance docs to update on landing (per stage)
- BACKLOG.md — add ABL-0016..0019 (currently only through ABL-0015).
- CLAUDE.md governance map + R-rules table only if a stage adds a rule
  (none planned; Stage 2 retirement routes through propose-only).
- The arch memory (`.claude/memory/`) — one entry per landed stage.
- CONTINUATION_PROMPT.md — handoff per stage.

### 7.4 Definition of done (per stage)
A stage is done when: its batches are merged, its flag is flipped ON after
a clean calibration smoke, its governance docs are updated, and the
capability in §0 for that stage is demonstrable from a real run's traces.

---

## 8. Fidelity & verification ledger

| Claim | Status |
|---|---|
| Stage 1 prompt seams + call-site context | ✅ verified (ABL-0016 §2) |
| `_build_priors_block` analog | ✅ verified |
| Findings ledger verdict model {confirmed/refuted/deferred/None} | ✅ verified (ABL-0015 Batch A) |
| Target-scope union over feature ledgers | ✅ design follows from verified ledger keying |
| Stage 2 outcome persistence seam (summary / .orchestrator-state / events) | 🔎 Batch 0 |
| Stage 2 doctrine-meta input/output contract | 🔎 Batch 0 (ABL-0003 exists ✅) |
| Stage 2 per-run active-rule record | 🔎 Batch 0 |
| Stage 3 global store location + bootstrap seam | 🔎 Batch 0 + ✎ decision |
| Stage 4 eng_patterns structure/consistency | 🔎 Batch 0 (path ✅ known) |

**No later-stage code starts before its Batch 0 closes its 🔎 items** —
the discipline that converted Stage 1 from sketch to a verified plan.

---

## 9. Recommended execution order

1. **ABL-0016 Batch A + B** (architect; ~1–1.5d) — the substrate + read
   path. Highest leverage, lowest risk, unblocks everything.
2. **ABL-0016 Batch C + smoke** (operator-gated) — flip `inject_lessons`.
3. **ABL-0017** (Stage 2) — closed-loop efficacy; needs Stage 1 provenance.
4. **ABL-0019** (Stage 4) *or* **ABL-0018** (Stage 3) — both depend only on
   Stage 1; pick by appetite. Stage 4 is lower-risk; Stage 3 is higher-value
   and pairs naturally with the §I.5 Django multi-target smoke.

Start point on approval: **ABL-0016 Batch A.**
