---
name: arch-cumulative-learning
description: Cumulative-learning program (mission's "cumulative" property). ABL-0016 Stage 1 (lessons-as-context) batches A–C shipped flag-OFF on branch cumulative_learning; ABL-0017/0018/0019 are Stages 2–4. Only operator calibration smoke remains for Stage 1.
metadata:
  type: project
---

The mission's **cumulative** property ("what's learned on one target
carries forward") was the least-mature of the four defining properties
(the "crew brain"). A 4-stage program addresses it. Strategy:
`CUMULATIVE_LEARNING_ROADMAP.md`; whole-feature plan:
`CUMULATIVE_LEARNING_IMPLEMENTATION_PLAN.md`.

## The program (ABL-0016 → ABL-0019)

- **Stage 1 / ABL-0016 — Lessons-as-context** (read path) — SHIPPED A–C.
- **Stage 2 / ABL-0017 — Closed-loop doctrine efficacy** (measure) —
  closes I-7; consumes Stage-1 provenance + per-BL outcomes.
- **Stage 3 / ABL-0018 — Cross-target transfer** (carry) — global crew
  memory outside target repos; pairs with §I.5 Django smoke.
- **Stage 4 / ABL-0019 — Pattern/convention profile** (compound) —
  consolidate eng_patterns into a per-target profile.

Each later stage opens with a **Batch-0 verification gate** before any
code — the discipline that turned Stage 1 from sketch to a verified plan.
Each ships behind a default-OFF flag, flipped only after an operator smoke.

**ABL-0017 Batch 0 (done)** found Stage 2 blocked: no way to attribute
outcomes to rules. Operator chose Option C → built the **ABL-0020
doctrine-spec registry** keystone (see [[arch-doctrine-spec-registry]]),
now COMPLETE. That discharged the I-2 mandate AND unblocked Stage 2 — both
halves of its input contract now persist per run (`bl_outcomes` +
`doctrine_manifest`). Stage 2 is ready to design/build.

## ABL-0016 as shipped (branch `cumulative_learning`)

- **A** (`eb20d6f`) `app/services/lessons.py`: `list_lessons(repo_root,
  feature_slug=None, cap=)` — **target-scoped** union over
  `_brownfield/features/*/acceptance/findings_log.jsonl`, keeps verdict in
  {confirmed, deferred}, dedups by finding_id, ranks same-feature →
  seen_count → recency. `render_lessons_block` — silent-empty advisory
  block ("falsification priors, not bans"). `Lesson` model is
  source-agnostic for later stages.
- **B** (`294f725`) `inject_lessons: bool = False` request → run_brief →
  3 flows (`_po_flow`/`_engineer_flow`/`_qa_or_scorer_flow`); 4 dispatchers
  (`build_po/engineer/qa/score`) gain a `_lessons_block` helper; 4
  brownfield builders interpolate `lessons_block` at the seams (after
  `{skills_md}`; scorer after `{RETRIEVAL_HINT_BROWNFIELD}`). I/O in the
  dispatcher; builders stay pure.
- **C** (`512a1c5`) `lessons.record_injection` → per-run
  `webapp/backend/logs/lessons/<run_id>.jsonl` of which lessons hit which
  role/bl_id. Framework telemetry, never in the target repo. **This is the
  hook Stage 2 consumes.**

## Key design decisions (verification-driven)

- **Option A (prompt injection)**, not Option B (Milvus indexing) — A
  reuses the proven `_build_priors_block` pattern; B (semantic lessons
  retrieval) deferred to Stage 1.5.
- **Target-scoped, not feature-scoped** — the ledger is per-feature and
  written at sprint *end*, so feature-scoped lessons are useless within a
  sprint; the value is cross-feature memory on the same target.
- **Advisory, no new R-rule** — lessons are evidence the agent weighs, not
  rules that bind (I-2 unaffected). Contrast [[arch-auto-dispatch]]'s R15.

## Status / open

233/233 backend tests. **Only the operator-gated calibration smoke
remains** for Stage 1: one sprint with `inject_lessons=true` on a target
with prior confirmed findings → confirm block renders + provenance written
+ no regression → architect proposes flag-flip. Next architect-doable work
is ABL-0017 Stage 2, starting with its Batch-0 verification gate.
