# ABL-0018 Stage 3 — Cross-target transfer ("community" cumulative learning)

> **Status: Batch-0 verification gate + design (2026-06-11).** Author: architect.
> Stage 3 of the cumulative-learning program
> ([`CUMULATIVE_LEARNING_ROADMAP.md`](CUMULATIVE_LEARNING_ROADMAP.md) §"Stage 3").
> Builds directly on the Stage 1 / 1.5 substrate
> ([`ABL-0016_LESSONS_AS_CONTEXT.md`](ABL-0016_LESSONS_AS_CONTEXT.md),
> [`ABL-0016_STAGE_1.5_SEMANTIC_LESSONS.md`](ABL-0016_STAGE_1.5_SEMANTIC_LESSONS.md) §6,
> which deliberately laid the `scope` field + vector mechanism so Stage 3 is an
> *additive collection + a graduation write-path*, not a rebuild).
>
> Per the program discipline, **this stage opens with a Batch-0 verification gate
> before any code.** The gate's centerpiece is a data-reality check against the
> live fleet — and that check materially reshapes what Stage 3 can honestly
> deliver *now* vs. what is gated on data accumulation.

---

## 0. The mission stake

This is the literal mission pillar: *"what's learned on one target carries
forward."* Stages 1/1.5/4 made learning cumulative **within** a target. Stage 3
makes it cumulative **across** targets — a fresh org's repo starts with the
accumulated judgment of every prior engagement instead of cold. With two
sprint-proven targets across two languages/stacks (beaverhabits = Python/FastAPI/
aiosqlite; fullstack-ecommerce-app = C#/.NET/EF Core/Postgres), the substrate to
*build* this exists for the first time.

---

## 1. Batch-0 verification gate — what was probed (every claim grounded)

### 1.1 The existing substrate (verified by code read, not assumed)

| Concern | Verified fact | Cite |
|---|---|---|
| Per-target lessons read path | `lessons.list_lessons(repo_root)` unions `_brownfield/features/*/acceptance/findings_log.jsonl`, filters verdict ∈ {confirmed, deferred}, dedups by `finding_id`, ranks same-feature→seen_count→recency, cap 8 | `lessons.py:116` |
| `Lesson` model already source-agnostic + carries `root_cause`/`fix_locus` (A63) | yes — `kind`, `feature_slug`, `classification`, `verdict`, `seen_count`, `source_run_id`, `root_cause`, `fix_locus` | `lessons.py:47` |
| Semantic pull store | `MilvusLessonStore` schema already carries a **`scope` field** (target\|global) — laid by Stage 1.5 §6 specifically for this stage | `lessons_index.py:169` |
| Per-target collection naming | `lessons_<md5(resolved repo_root)[:8]>` — **per-target by construction**; a fixed-name collection is therefore free of collision with any target | `lessons_index.py:212` |
| Read tool already advisory/never-raises | `search_lessons(...)` catches all → `[]`; lazy-builds if empty | `lessons_index.py:247` |
| MCP injection seam | `retrieval_server.py` `search_lessons` tool reads `RETRIEVAL_LESSONS_REPO` (env override, already present) | `retrieval_server.py:339` |
| Read-path env hook | `claude_agent.py` sets `RETRIEVAL_LESSONS_REPO` per agent — **the natural injection point for a second (global) store** | `claude_agent.py:173` |
| Push block (Stage 1) | `lessons.render_lessons_block` / `record_injection`; flows via `inject_lessons` through PO/engineer/QA flows | `lessons.py:185`, `orchestrator.py` |

**Conclusion:** the substrate is genuinely additive-ready. The `scope` field, the
embedder (Ollama bge-m3 1024-dim), the relevance floor (0.55), the advisory
never-raise contract, and the env-override read hook all already exist. Stage 3
adds (a) a **global store** keyed by a fixed name in the *core* project, (b) a
**graduation write-path** into it, and (c) a **merged read-path** that surfaces
global lessons alongside per-target ones.

### 1.2 The data-reality check (the decisive Batch-0 finding)

Graduation cannot key on `finding_id` — IDs are per-feature/per-run, so the *same*
failure mode on two targets has *different* IDs. Graduation must be **semantic**
(cluster confirmed lessons across targets by embedding cosine; a cluster spanning
≥N distinct targets graduates). That raises the empirical question Batch-0 must
answer: **what confirmed cross-target lesson material actually exists today?**

Verified against the live ledgers (2026-06-11):

| Target | Feature ledgers | **Confirmed lessons** (verdict ∈ {confirmed,deferred}) |
|---|---|---|
| beaverhabits | 5 (habit-notes, rest-days-streak-freeze, periodic-habit-goals, habit-insights, habit-history) | **1** — rest-days streak *layer-divergence* product_bug |
| fullstack-ecommerce-app | 1 (ecommerce-wishlist) | **0** — `findings_log.jsonl` empty (acceptance FIND-01 was flagged in the report, never written to the lessons ledger) |

**Fleet total: 1 confirmed lesson, on 1 target.** There is currently **no pair of
confirmed lessons across two targets** that could form a graduation cluster.

**Implication (honest, no-overclaim):** the recurrence-graduation **write-path can
be built and unit-proven now** (synthetic multi-target lessons), but it **cannot be
organically LIVE-PROVEN** until cross-target confirmed-lesson recurrence
accumulates — which, given the two targets are different stacks, may be slow. So
under a recurrence-only design, Stage 3 ships `[~]` (mechanism + unit proof) with
an empty global store and a live-proof gated on data. The **read-path**, by
contrast, *is* live-demonstrable the moment the global store holds ≥1 lesson.

This is exactly the finding a Batch-0 gate exists to surface before code — it
turns the one open governance question (§3) from abstract into decision-forcing.

---

## 2. Design — the calls the architect owns

These are decided (architect accountability; not menu items):

- **Substrate location.** The global store lives in the **core project**, never in
  any target repo (it is cross-target by definition):
  `webapp/backend/.crew-memory/global_lessons.jsonl` (durable source of truth,
  committed-or-gitignored TBD per §3) + Milvus collection **`lessons_global`**
  (fixed name — no md5; collision-free by §1.1). A `GlobalLesson` record =
  the `Lesson` dossier (`root_cause`/`fix_locus`/`classification`/`body`) + Stage-3
  provenance: `origin_targets: [repo_id…]`, `origin_finding_ids: […]`,
  `target_count`, `graduated_ts`, `graduation_kind` (recurrence|curated).
- **Write-path = semantic recurrence clustering.** At `sprint_complete` (after the
  per-target lessons refresh), a best-effort graduation pass embeds this target's
  confirmed lessons and compares (cosine ≥ a graduation floor — **empirically
  calibrated to 0.62**: a genuine cross-target layer-divergence twin measures
  ~0.665 on real bge-m3, unrelated modes ~0.46–0.47, so 0.62 sits in the gap)
  against confirmed lessons from **other** targets; any cluster spanning
  **≥N distinct targets** graduates a representative (richest dossier =
  longest `root_cause`+`fix_locus`) into the global store. **N = 2** (minimal
  generality signal: independently confirmed on ≥2 targets; raising N later is a
  pure tightening). Idempotent: a stable `global_lesson_id =
  sha256(sorted origin_finding_ids)`.
- **Read-path = both push and pull, scope-tagged.** A fresh target with zero
  per-target lessons must still "inherit the global layer on day one," so global
  lessons surface **two ways**: (a) a capped **global push block** (top global
  lessons by `target_count`→recency, rendered with a distinct *"seen across N
  targets"* framing, behind a `inject_global_lessons` flag) so a cold target sees
  them with no query; and (b) the **semantic pull** — `search_lessons` unions the
  per-target collection **and** `lessons_global`, each hit tagged
  `scope=target|global`. The agent weighs both with its own grounding (advisory
  framing preserved).
- **Governance posture of the *content*.** Graduated lessons remain **advisory
  evidence**, never binding rules — they ride the mature grounding property, exactly
  like per-target lessons (roadmap §"governing discipline"). Doctrine stays
  operator-gated and is untouched. *(What is NOT yet decided is the* ***act of
  crossing into global*** *— see §3.)*
- **Safety contract.** The global read-path inherits the never-raise advisory
  contract: if `lessons_global`/Milvus/Ollama are down or absent, the union returns
  only per-target (or empty) — a global-store outage never blocks a sprint.
- **Flag-gated, default-OFF.** Both the graduation write-pass and
  `inject_global_lessons` ship behind default-OFF flags; flip only after a smoke,
  per program discipline.

## 3. The crossing decision — RESOLVED (operator, 2026-06-11): **(C) Both**

> **DECISION LOCKED:** recurrence-≥2-targets **auto**-graduates (canonical,
> un-gated, scaling) **plus** a transparent operator/architect **curated-seed**
> path (`graduation_kind=curated`, honest provenance) for obviously-general
> lessons. `global_lessons.jsonl` is **committed** (operator-auditable, since the
> curated path makes it partly human-authored). Recurrence remains primary;
> curation bootstraps the store + lets the read-path be **live-proven now** by
> seeding the one stack-agnostic lesson (beaverhabits layer-divergence). This is
> §3 option (C) below.

**How does a lesson cross into the global store?** Two prior architect framings
disagreed, and the §1.2 data finding made the choice decision-forcing:

- **(A) Recurrence-only, un-gated** — roadmap §"governing discipline" + the
  session handoff. Auto-graduate on ≥2-target semantic confirmation. Purest fit
  with "lessons are advisory evidence, not doctrine"; scales to "walk away"
  (no human in the graduation loop); recurrence-across-independent-targets is a
  *stronger* generality signal than a single human glance. **Cost:** empty global
  store until organic cross-target recurrence accumulates (today: 0) → the
  write-path is `[~]` unit-proven, live-proof gated on data.
- **(B) Operator-gated graduation** — Stage 1.5 §6 ("operator-gated graduation …
  consistent with 'doctrine stays operator-gated forever'"). The poisoned-global-
  memory blast radius (one bad global lesson contaminates *every* future target)
  is treated like doctrine: architect/meta proposes graduation candidates →
  operator approves into global. **Cost:** a human gate at graduation (mild
  "walk-away" tax, but only at crossing, not per-sprint). **Benefit:** provable
  now (operator can approve the one clearly-general lesson) + the dangerous write
  stays human-checked.
- **(C) Both (architect recommendation)** — recurrence-≥2 **auto**-graduates (the
  canonical, un-gated, scaling mechanism that fills the store organically over
  time) **plus** a transparent operator/architect-curated **seed** path for
  obviously-general lessons. The curated seed is honestly provenance-tagged
  (`graduation_kind=curated`, `origin_targets`, the verified dossier), so memory
  stays un-poisoned, AND it lets us **live-prove the read-path now** (seed the one
  genuinely stack-agnostic lesson — beaverhabits' *"new logic added at core/API
  layer but pre-existing UI callers still hit the legacy path → divergence"*, a
  failure mode that recurs regardless of language — then demonstrate a sprint on
  *either* target pulling it as a `scope=global` hit). Recurrence remains the
  primary mechanism; curation is the bootstrap + the safety valve.

The fork matters because it decides (i) whether the global write is human-gated,
(ii) whether `global_lessons.jsonl` is operator-curated-and-committed or
machine-written-and-gitignored, and (iii) whether Stage 3 can claim a near-term
`[x]` live-proof or ships `[~]` pending data.

## 4. Batches (provisional — finalized after §3 is resolved)

| Batch | Scope | Test gate |
|---|---|---|
| **A — `global_lessons.py`** | `GlobalLesson` model + provenance; `lessons_global` store (reuse `MilvusLessonStore` iface, fixed collection); `list_global_lessons`, `render_global_lessons_block` (the "seen across N targets" framing); jsonl source-of-truth I/O. | unit: model round-trip; render silent-empty; never-raise |
| **B — graduation write-path** | `graduate(repo_root, all_targets)` — embed this target's confirmed lessons, cosine-cluster vs other targets' confirmed lessons, ≥N-distinct-targets → upsert representative to global (idempotent by `global_lesson_id`). | unit (synthetic multi-target lessons): a shared mode across 2 synthetic targets graduates; a target-unique mode does NOT; **effectiveness on real bge-m3 embeddings** (the divergence lesson vs a contrived ecommerce near-twin → clusters; vs an unrelated lesson → does not) |
| **C — merged read-path** | `search_lessons` unions per-target + `lessons_global` (scope-tagged); `inject_global_lessons` push block wired through PO/engineer (and QA) flows; provenance telemetry. | unit: union returns both scopes, floor honored; push block renders global-only on a cold target; flag-OFF = no change |
| **D — graduation trigger + (per §3) curated-seed CLI/path** | `sprint_complete` calls `graduate(...)` best-effort off-thread (mirrors the Stage-4 pattern_profile refresh, `orchestrator.py:3370`); emits `global_lessons.graduated{n,targets}`. If §3=B/C: a `seed_global_lesson` operator path. | integration: a sprint emits the event; (B/C) operator-seed lands + is pull-retrievable |
| **E — smoke + flag-flip** | one sprint with `inject_global_lessons=true` on a target; confirm global block/pull renders + provenance + no regression → propose flip. | live smoke (read-path always provable once store ≥1; write-path live-proof per §3) |

## 5. Calibrated proposal

**Risk:** Low–medium. Entirely additive; advisory (agent grounds against it, not
bound by it); the global read-path inherits the never-raise contract so a global-
store outage cannot break a sprint. The one elevated risk is **poisoned global
memory** (blast radius = all future targets) — mitigated by: the relevance floor,
the ≥N-target recurrence bar (and/or the §3 gate), honest provenance on every
global record, and default-OFF flags.
**Named test that proves benefit:** Batch-B effectiveness on real bge-m3
embeddings (a shared failure mode across two targets clusters and graduates; a
target-unique mode does not) **+** Batch-E read-path live smoke (a sprint pulls a
`scope=global` lesson it could not have learned on this target).
**Named rollback:** `inject_global_lessons` default-OFF (no global push);
`search_lessons` union degrades to per-target-only if `lessons_global` is absent;
delete the `lessons_global` collection + `global_lessons.jsonl` to fully reset.
Per-target Stages 1/1.5/4 are untouched and independent.

## 5b. DORMANT BY DEFAULT (operator directive, 2026-06-11)

> **Cross-target transfer is OFF and must not be used in any run** until explicitly
> re-enabled. A single master switch — `global_lessons.enabled()` reading
> **`STAGE3_CROSS_TARGET=1`** (default unset) — gates ALL THREE consumption paths:
> the push block (`prompts._lessons_block`), the merged `search_lessons` pull
> (`retrieval_server`, which falls back to per-target-only when off), and the
> `sprint_complete` graduation write (`orchestrator`). With the switch unset:
> nothing is pushed, the pull returns only this target's lessons, and graduation
> does not even write. The on-disk global store + curated seed are left intact
> (just not consumed). **Reversible:** `export STAGE3_CROSS_TARGET=1` + restart the
> harness to reactivate. Tests:
> `test_global_lessons_wiring.test_global_dormant_by_default_even_with_flag_and_store`.

## 6. SHIPPED — status / no-overclaim ledger (2026-06-11)

Implemented across `global_lessons.py` (model + jsonl store + graduation + merged
read), the `search_lessons` MCP merge (`retrieval_server.py`), the
`inject_global_lessons` push (prompts + orchestrator + request), the
`sprint_complete` graduation trigger, and `scripts/seed_global_lessons.py`. Tests:
`test_global_lessons.py` (20) + `test_global_lessons_wiring.py` (10). **Full backend
suite: 467 passed, 0 regressions.**

| Component | Status | Proof |
|---|---|---|
| Substrate (global store, fixed `lessons_global`, committed jsonl) | **`[x]`** | round-trip + dedup unit tests; real store seeded + indexed |
| Graduation write-path (recurrence, ≥2 targets, floor **0.62**) | **`[x]` mechanism / `[~]` organic** | real-bge-m3 effectiveness: genuine cross-target twin (cosine ~0.665) graduates, unrelated (~0.47) rejected. NOT organically fired — fleet has 1 confirmed lesson, 0 cross-target recurrence (§1.2); live-proof gated on data |
| Read-path PUSH (`inject_global_lessons`) | **`[x]` LIVE-PROVEN** | global block renders into a REAL ecommerce engineer prompt (0 per-target lessons) — day-one inheritance, no floor dependency |
| Read-path PULL (merged `search_lessons`) | **`[x]` LIVE-PROVEN** | from ecommerce (0 per-target lessons) a neutral hazard-pattern query pulls the beaverhabits global lesson at **0.669 → scope=global**; a distant-domain pricing query at **0.483 correctly stays below the 0.55 floor** (discriminates on proximity, not keywords) |
| Curated seed (operator/architect crossing) | **`[x]` LIVE** | one real, honestly-provenance'd lesson (the beaverhabits layer-divergence, `graduation_kind=curated`, `origin_targets=[beaverhabits]`, `target_count=1`) seeded into the committed store |

**Honest open items (do not overclaim):**
- **Recurrence graduation is `[~]` (never organically fired)** — needs ≥2 targets to
  share a confirmed failure mode; the fleet doesn't yet. Will fire + live-prove as
  confirmed lessons accumulate across targets.
- **Cross-domain PULL is floor-limited.** A single *concrete* lesson matches its own
  domain strongly (~0.65) but a *distant* domain only ~0.48–0.51 — below the 0.55
  floor. The PUSH channel guarantees inheritance regardless; the PULL surfaces a
  global lesson only for genuinely-near problems. **Open follow-up:** a separately-
  calibrated (slightly lower) global-pull floor may surface more genuine cross-target
  matches — deferred until there's enough cross-target data to calibrate it without
  false-surfacing (not lowered blind).
- **Flags default OFF** (`inject_global_lessons`); the recurrence write-pass runs
  best-effort at `sprint_complete` (a pure write; consumed only when the flag is on).
  Smoke + flip is the remaining Batch-E step.

See [[arch_cumulative_learning]], [[feedback_no_scope_overclaim]],
[[feedback_improve_crew_not_accommodate]].
