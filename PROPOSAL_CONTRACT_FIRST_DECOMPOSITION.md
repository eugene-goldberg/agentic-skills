# PROPOSAL: Contract-First Decomposition + Stub Materialization Program

> **Status:** proposed (operator-directed 2026-06-15). Architect: Claude (Opus 4.8).
> **One line:** make the crew decompose and build like a professional team — agree the
> interfaces first, then build vertical slices **concurrently against the contract + mocks**,
> and integrate once at the end — so the parallel executor we already built actually gets
> parallel work to run.

---

## 1. Motivation — the gap this closes

We have shipped and live-proven the parallel **executor**: wave scheduling (`wave_execution`,
R21 DAG → topological waves) and intra-wave concurrency (`wave_concurrency>1`, Strategy A:
isolated per-BL branches + deterministic BL-id-ordered barrier assembly). It works.

But it is **starved**. The PO decomposes features by **horizontal architectural layers**, which
produces strictly serial dependency chains, which the scheduler (correctly) runs one-at-a-time.

**Evidence (2026-06-15, Product Q&A sprint `run-20260615T175833Z-083f51`, fullstack-ecommerce-app):**
the PO produced a 4-BL chain —
`BL-0001 persistence → BL-0002 read API → BL-0003 write API → BL-0004 UI` —
where each BL declares the previous as a dependency. Topological waves = `[[1],[2],[3],[4]]`,
every wave width-1. **No two BLs can run in parallel**, regardless of flags, because each waits
for the *real merged code* of the one before it.

A professional team would not build this serially. They:
1. agree the **interfaces / DTOs / API shapes up front** (the contract), then
2. build the slices **in parallel against that contract**, each **mocking** its dependencies
   (frontend against a mocked endpoint, backend against the agreed repo interface, tests against
   the contract), and
3. **integrate once** at the end, replacing mocks with real wiring.

**The key insight (operator, 2026-06-15):** contract-first-against-mocks changes the **unit of
dependency** from *"my upstream's merged code"* to *"the agreed interface."* That single change
collapses the serial layer-chain into a parallel fan-out:
`[contract] → {persistence, read, write, UI all at once} → integrate`. A width-1 chain becomes a
width-N wave. **The bottleneck was never the scheduler — it is the decomposition philosophy and
an execution model that assumes real upstream code instead of an agreed contract.**

---

## 2. Thesis fit

This is the structural enabler of the mission's *"point it at a brownfield repo, hand it a
product requirement, walk away"* (THESIS) — specifically the difference between a crew that
**hands a baton from one engineer to the next** and a crew that **works like a team**. It does
not replace any existing pillar (grounded / self-correcting / honest / cumulative); it adds
**team-like parallelism** on top of them.

---

## 3. Architecture — three pieces

### 3a. Contract materialization (contract → compilable stubs, first)
The PO's R21 `**Exposes:**` / `**Consumes:**` declarations stop being *prose validated after the
fact* and become the **source** for a **contract-establishment step** that commits **compilable
stubs** to the baseline BEFORE any slice runs:
- **C#:** interfaces (`IProductQuestionRepository`), DTO/`record` types, controller method
  signatures returning `NotImplementedException`; DI registrations for the interfaces.
- **Python:** `Protocol`/ABC interfaces, pydantic models, route stubs raising `NotImplementedError`.
- **TS/React:** TypeScript interfaces + a mock layer (e.g. MSW handlers) for the agreed endpoints.

The stubs compile and the suite builds — nothing is implemented yet, but every slice now has a
real, typed contract to code and test against.

### 3b. Contract-first decomposition (PO doctrine — the hard part)
The PO decomposes into **a contract BL + vertical, file-disjoint, mockable slices**, each of which
**consumes the contract** (not the prior BL's code). This is a genuine doctrine shift: the PO must
design *against the contract* rather than mirror the existing code's layering. Done right, the
slices land in **one wave** and the executor parallelizes them.

### 3c. Mock-based per-slice work + one real integration at the barrier
Each slice implements its part against the contract and **mocks its dependencies**; its **per-BL
gate runs against mocks** (which our per-BL gates already are — mock-only by design). At the wave
**barrier**, real implementations are **bound** (DI / wiring) in place of the stubs; the
**acceptance phase** (R17/R20 — live, no-mock, whole-app E2E per acceptance criterion) is the
**integration truth** that catches any mock-vs-reality drift.

---

## 4. Why our existing machinery already fits

This program is **mostly assembly of parts we already have**, plus two new pieces:

| Have | Role in contract-first |
|---|---|
| `wave_execution` + `wave_concurrency` (live-proven) | runs the parallel slices |
| per-BL gates are **mock-only by design** | fits "test the slice against the contract/mocks" |
| **acceptance** = the one real, no-mock, whole-app integration checkpoint (R17/R20) | the safety net that makes mocking safe — catches mock drift at integration |
| R21 `Exposes`/`Consumes` already declared by the PO | becomes the **source** for stub materialization (validation → generation) |
| reindex incremental + complete baseline (just shipped) | fast indexing so concurrent slices ground cheaply |

**Missing (the build):** (1) the **contract-materialization step** (stubs from contracts,
language-aware) and (2) the **contract-first PO decomposition doctrine** (+ the dependency
semantics that say "depends on the contract," scheduled as wave 0, not "depends on code").

---

## 5. Phased plan (proposed; each phase operator-gated, flag-guarded, live-proven)

- **Phase 0 — design (this doc).** Capture the program; classify against invariants; agree scope.
- **Phase 1 — contract as a first-class artifact.** PO emits a machine-usable contract spec from
  `Exposes`/`Consumes`; a materializer turns it into **compilable stubs** for ONE language (C#,
  since ecommerce is the proving ground). DoD: stubs compile, suite builds, contract spec
  validates. Flag `contract_first` default OFF.
- **Phase 2 — contract-first decomposition doctrine.** PO skill/prompt change so it produces a
  contract BL + parallel, file-disjoint, mockable slices. DoD: on a feature a human team would
  parallelize, the PO's DAG **fans out** (a width-≥2 wave) — measured by a DAG-width metric.
- **Phase 3 — mock execution + barrier binding.** Slices build against stubs+mocks (per-BL gate
  green on mocks); the barrier binds real impls; acceptance verifies the wired whole. DoD: a
  width-N wave runs **concurrently**, all slices merge, acceptance green on real (no-mock) wiring.
- **Phase 4 — live proof on ecommerce.** Deliver a feature end-to-end with genuinely concurrent
  slices + green live acceptance; compare wall-clock + parallelism vs the sequential baseline.

---

## 6. Risk / test / rollback

- **Risk — mock drift** (a slice's mock diverges from the real impl). **Mitigation:** acceptance
  is the no-mock whole-app integration truth (already binding, R17/R20); drift surfaces there as a
  `product_bug` finding → the no-abort fix loop. This is the *defining* safety property of the
  design and must stay strong.
- **Risk — the PO won't reliably decompose contract-first** (it grounds on existing layered code
  and mirrors it). This is the hardest part; Phase 2 is iterative (doctrine + measure DAG width)
  and gated on the fan-out metric, not vibes.
- **Risk — stub→real binding conflicts** at the barrier. **Mitigation:** impls land in disjoint
  files behind the interface (DI), so binding is additive, not an edit-conflict.
- **Test:** DAG-width metric per feature; per-slice mock-gate green; acceptance green on real
  wiring; wall-clock vs sequential baseline.
- **Rollback:** entirely **additive + flag-gated** (`contract_first` default OFF). With the flag
  off, today's layered/sequential decomposition + execution path is byte-identical.

---

## 7. Invariant classification (architect lens)

- **I-2 (doctrine contract):** introduces new PO doctrine (contract-first decomposition) and likely
  a new R-rule (e.g. **R22**: a feature's contract is materialized as compilable stubs before any
  consuming slice runs) — lands in `doctrine_spec.py` with an enforcement point + check + test, per
  the standing I-2 mandate. The contract-materialization step + DAG-width are its checks.
- **I-6 (failure taxonomy):** **mock-drift** is a new failure class that acceptance owns; track its
  instances.
- Composes with: no-abort (slice/contract failures investigate→fix→escalate, never abort), simple
  gating (per-BL mock-only gate + one acceptance integration checkpoint — *already* the right
  shape), and R17/R20 live acceptance (the integration truth).

---

## 8. Definition of done (program)

The crew, handed a product requirement whose natural shape is parallelizable, **autonomously**:
1. agrees + materializes the contract as compilable stubs,
2. decomposes into vertical slices that fan out into a concurrent wave,
3. builds each slice against the contract + mocks (per-slice gates green),
4. binds real implementations at the barrier, and
5. passes live, no-mock, whole-app acceptance —
delivering the feature with **real team-like parallelism**, honestly reported, with mock-drift
caught at acceptance rather than shipped.

---

*Authored 2026-06-15 after the Product Q&A sprint exposed the serial-decomposition bottleneck.
Operator-directed program. Pending operator approval of the phased plan before Phase 1 begins.*
