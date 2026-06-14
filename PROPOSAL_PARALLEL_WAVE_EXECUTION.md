# Proposal — Parallel **Wave** Execution (DAG-scheduled, contract-first, merge-per-wave)

> Author: architect (Claude). Date: 2026-06-14. Status: **PROPOSAL — awaiting operator
> approval.** Origin: operator's target-state sketch (parallel BLs → "ensure all BLs
> finished" → accept → merge → re-index) reviewed against current sequential execution
> and against how human engineering teams actually manage parallel development.

---

## 1. Vision / target (what the operator wants)

Today the crew runs backlog items **strictly sequentially**: BL-0001 completes its whole
cycle (engineer → reindex → QA → reindex → scorer → **merge to `integration`**) before
BL-0002 starts. The just-finished inventory sprint (`run-20260614T025948Z-0c2a26`, 4 BLs,
~4.5h wall-clock, two ~15-min reindexes per BL) is the canonical evidence of the cost: the
pipeline is correct and clean but **serial**, and reindex-dominated.

The operator's target is **parallelism**: decompose the brief, run independent BLs
**concurrently** in isolated worktrees, join when all are finished, accept the assembled
feature, then integrate — with re-indexing collapsed rather than paid per BL. The two
wins sought: **wall-clock** (parallel) and **reindex cost** (fewer, batched).

This proposal endorses that direction with **one structural refinement drawn from human
practice**: schedule by a **dependency DAG into waves**, define **interfaces up front**,
and **integrate per wave** rather than in one big merge at the very end.

---

## 2. How human teams actually manage parallel development (the rationale)

Thirty years of practice converge on a few load-bearing ideas:

1. **Continuous integration beats merge-at-the-end.** Trunk-based development integrates
   small increments to the shared branch many times a day *specifically to avoid* the
   unbounded, context-free conflict resolution of a deferred big-bang merge ("merge hell"
   / integration debt). The long-lived-branch + final-merge model (old gitflow) was
   abandoned for exactly this reason. **Implication:** the target diagram's "merge all
   working trees at the END" is the anti-pattern; keep integration incremental.

2. **Conflict-disjoint decomposition.** Before parallelizing, a lead splits work along
   ownership boundaries (module/service/file) so two people rarely touch the same lines.
   Modular monoliths and microservices exist largely to *enable* parallel teams. Half of
   conflict avoidance is done at decomposition time.

3. **Contract-first interfaces (the key enabler).** When work is interdependent, teams
   agree the **interface** (API schema, function signatures, DTO shape, DB columns) up
   front, then code against the *agreed contract* in parallel, mocking what they don't
   own. You don't need your teammate's implementation if you both committed to the same
   interface. This is what makes "dependent-ish" work parallelizable.

4. **Stacked PRs / dependency sequencing.** Genuinely dependent work isn't pretended to be
   parallel — it's **stacked**: A lands first, B opens on A, C on B (Graphite,
   `git rebase --update-refs`, Gerrit relation chains). This is exactly a **topological
   DAG executed in waves**: parallelize the independent layer, sequence the dependent
   ones.

5. **Frequent rebase / stay current.** In-flight branches pull `main` often to absorb
   landed work, keeping divergence (and conflicts) small and incremental.

6. **Per-PR review + CI gate, plus a continuously-validated integration/staging env.**
   "Does it all work together" runs every time something lands — not once at the end.

7. **Feature flags** let incomplete work merge to trunk continuously without shipping it —
   decoupling *integrated* from *released*.

8. **A human coordinates** — a tech lead sequences work and owns interface decisions. In
   the crew that role is the **PO/architect**.

**Crew twist:** a human rebases mid-work because they work for *days*; a crew agent runs
in *minutes* and can't absorb landed sibling work mid-run. So the crew's faithful analog
to continuous integration is the **wave barrier**: finish a batch of conflict-disjoint
BLs, integrate + reindex **once**, start the next batch on the new base.

---

## 3. The model: DAG-scheduled waves

```
Submit brief
  → Ensure indexed
  → PO decompose: backlog + per-BL acceptance criteria
                + DEPENDENCY DAG (which BL depends on which)
                + INTERFACE CONTRACTS (shared DTOs / signatures / schema each BL exposes or consumes)
  → Wave scheduler (topological layers of the DAG):
       wave W = { BLs whose deps are all already merged }
       run all BLs in W IN PARALLEL  (isolated worktrees, contract-first)
         each BL: implement (+unit tests) → QA gate (BL's own tests) → scorer
       WAVE BARRIER:
         integrate wave W onto integration (conflict-resolver agent handles overlaps)
         reindex ONCE
       next wave …
  → Regression checkpoint (full prior suite vs baseline)
  → Acceptance LOOP (boot whole app → Playwright every AC w/ evidence → fix→re-boot→re-test
                     → accepted | escalate)  — runs on a scratch-assembled branch
  → Merge accepted feature to target  (fast-forward; already assembled)
  → Persist acceptance evidence in-target → Closure-check → Doctrine-meta → done
```

- A **fully independent** feature collapses to **one wave** → exactly the operator's
  diagram (max parallelism, one reindex).
- A **dependent** feature gets 2–3 waves → parallelism *within* a wave, correctness
  *across* waves. Reindexes drop from **2/BL** to **~1/wave** — a large, correctness-
  preserving speedup.

The inventory feature, as decomposed (BL-0001 availability field → BL-0002 decrement
depends on it; BL-0003 badge & BL-0004 cart-cap depend on BL-0001's read value), would be
≈ **3 waves** — `[BL-0001]`, `[BL-0002, BL-0003, BL-0004]` (the latter three only depend
on BL-0001, not each other) — i.e. ~4 reindexes instead of 8, with the three frontend/
write BLs running concurrently. Roughly a **2× wall-clock cut** with no correctness loss.

---

## 4. Contract-first PO interface definition — a first-class NEW responsibility

The single highest-value addition. Parallelism does **not** come from deferring merges; it
comes from the PO defining shared interfaces **up front** so siblings code against the
contract, not each other's source.

Concretely, the PO's decomposition gains two required artifacts:

- **`DEPENDS.md` (or a `depends:` field per BL):** the dependency DAG — every BL names the
  BLs it depends on (empty = wave 1). Cycles are rejected.
- **`CONTRACTS.md`:** for each interface a BL *exposes* or *consumes* — the DTO shape,
  endpoint signature, new DB column/field, service-method signature — stated **before**
  any BL implements. A consuming BL codes (and mocks tests) against the contract; the
  producing BL must honor it. (This is exactly how the inventory PO already, informally,
  specified `TryDecrementStockAsync(productId, quantity)` and the availability read value —
  we make it a *required, machine-checkable* artifact.)

**New doctrine rule (R-rule, I-2 registry + enforcement point):**

> **R21 — every BL declares its dependencies and the interface contracts it exposes/
> consumes; the PO emits an acyclic DAG and a contract for every cross-BL interface.**
> Enforcement point: `validate_po` (post-PO gate). A BL with an undeclared cross-BL
> dependency, a missing contract for an interface another BL consumes, or a dependency
> cycle fails the PO gate → existing doctrine retry loop re-prompts the PO. The wave
> scheduler reads the DAG; the conflict-resolver and QA mock-against-contract both read
> the contracts.

Better contracts ⇒ more BLs are independent ⇒ bigger waves ⇒ more speed. The PO's interface
quality becomes the lever (and a thing to verify), exactly as a human tech lead's does.

---

## 5. Merge-per-wave, NOT merge-at-end

Per §2.1, the target's single end-merge is replaced by **integration at each wave
barrier**:

- Each wave's BLs merge onto `integration` as a batch the moment the wave's gates are
  green — keeping conflicts small, incremental, and resolvable *with* fresh agent context.
- A **conflict-resolver agent** (extend the Janitor, or a dedicated integrator) owns
  cross-BL conflicts at the barrier, because the original BL agents have exited.
- Acceptance runs on the **assembled** branch (all waves merged) — a scratch/assembled
  `integration` — *before* the final fast-forward to the target. So acceptance still gates
  the delivery (all-or-nothing feature landing), but integration itself was never a
  big-bang.

This preserves the operator's "accept before the feature is truly delivered" instinct
while avoiding the deferred-merge failure mode.

---

## 6. What to KEEP (do not regress in the redesign)

The parallelization is orthogonal to — and must not weaken — the properties that make the
crew trustworthy:

- **No-abort doctrine + Janitor** — every gate/merge failure still drives
  investigate→fix→re-test, Janitor env repair, escalate only as Option A. (Now also the
  wave-barrier conflict resolver.)
- **Regression checkpoint** — the one full prior-suite run vs baseline, before acceptance.
- **Live-acceptance loop** — boot the whole app, Playwright every AC with on-disk
  evidence, fix→re-boot→re-test until accepted-live or honest escalation. (Just proven on
  reviews *and* inventory.)
- **Persist acceptance evidence in-target** (`_brownfield/features/<feature>/acceptance/`).
- **Closure-check** (I-3 postconditions) and **doctrine-meta** (I-7 self-hardening).
- **Per-BL gate = only that BL's own tests** (simple gating model, A55) — unchanged; it
  parallelizes naturally.

---

## 7. ARCHITECTURE_INVARIANTS mapping (I-1 … I-7)

| Inv | Impact of wave execution | Action |
|-----|--------------------------|--------|
| **I-1 subprocess lifecycle** | N parallel agents + N worktrees concurrently → more concurrent subprocesses/worktrees to register & reap. | Wave scheduler must register every spawned agent/worktree on every exit path; closure-check asserts empty *after each wave* and at end. |
| **I-2 doctrine contract** | New rule R21 (DAG + contracts). | Land R21 in `doctrine_spec.py` with enforcement point (`validate_po`) + a resolvable check + test, same commit. |
| **I-3 closure postconditions** | Parallel worktrees/branches per wave. | Closure-check runs at each wave barrier (empty worktree/branch set for that wave) and at run end. |
| **I-4 run identity** | One run_id threads through all waves/BLs/worktrees. | Unchanged; ensure wave/BL labels carry the run_id. |
| **I-5 truthful aggregation** | A wave can partially fail (some BLs green, some escalate). | Wave-level status must honestly report which BLs passed/failed; never report a wave "done" if a member escalated. |
| **I-6 failure taxonomy** | New failure classes: cross-BL merge conflict, contract violation (producer ≠ consumer), DAG cycle. | Add these classes; >3 instances ⇒ tighten R21 / decomposition doctrine. |
| **I-7 self-hardening** | Doctrine-meta should learn which decompositions caused conflicts/contract breaks. | Feed wave-barrier conflict/contract-violation events to doctrine-meta to improve PO decomposition over time. |

---

## 8. Risks · named proof-of-benefit · rollback

**Risks**
1. **Under-declared dependencies** → a "parallel" BL grounds against a base missing a
   sibling it actually needs → wrong impl. *Mitigation:* R21 PO gate + the QA-against-
   contract check; doctrine-meta learns from violations.
2. **Cross-BL merge conflicts at the barrier** → *Mitigation:* conflict-disjoint
   decomposition (PO), small per-wave batches, dedicated conflict-resolver agent with
   no-abort authority.
3. **Contract drift** (producer changes the interface mid-wave) → *Mitigation:* contracts
   are frozen for the wave; a producer change is a new wave/BL, not an in-place edit.
4. **Resource pressure** — N concurrent dotnet/vite/ollama + N worktrees → CPU/disk/
   Docker.raw pressure. *Mitigation:* a concurrency cap (max parallel BLs/wave), disk
   preflight per wave.
5. **Harder debugging** — a failure in a parallel wave is less obviously attributable than
   in a serial run. *Mitigation:* per-BL trace isolation (already exists) + wave-scoped
   regression at the barrier.

**Named proof-of-benefit (how we'll know it worked):** re-run the *inventory* brief under
wave execution and show (a) `loop.accepted` with the same B.3–B.6 evidence, (b) regression
checkpoint green, (c) **wall-clock materially lower** than this run's ~4.5h (target: the
3-frontend/write BLs run concurrently; reindexes ~4 not 8), (d) zero cross-BL conflicts
unresolved at the barrier. Same correctness, less time = the benefit, measured.

**Rollback:** the whole feature is flag-gated (`wave_execution`, default OFF). OFF ⇒ the
current sequential loop (the degenerate "1 BL per wave" case) runs exactly as today. No
behavior change until explicitly enabled per run.

---

## 9. Phased build plan

1. **PO DAG + contracts artifact (R21).** PO emits `DEPENDS.md` + `CONTRACTS.md`;
   `validate_po` enforces acyclic + contract-for-every-cross-BL-interface; doctrine_spec
   R21 + test. *(No execution change yet — sequential loop still runs; we just start
   producing the DAG and validate it. Low risk, immediately observable.)*
2. **Wave scheduler.** Orchestrator groups BLs into topological waves from the DAG;
   today's loop becomes the `concurrency=1` degenerate case. Behind `wave_execution` flag.
3. **Wave-barrier integrate + reindex-once.** Merge a wave's BLs as a batch; single
   reindex per barrier (gated by the `has_index`/content-hash check). Closure-check per
   barrier.
4. **Conflict-resolver agent.** Extend the Janitor (or a dedicated integrator) to resolve
   cross-BL conflicts at the barrier under no-abort.
5. **Accept-on-scratch-assembled-branch.** Acceptance loop runs on the assembled branch;
   on accept, fast-forward to target.
6. **Concurrency cap + per-wave disk preflight.** Bound parallel BLs; preflight resources.
7. **Measure + iterate.** Re-run inventory under waves; compare wall-clock + correctness
   vs the sequential baseline; feed conflict/contract events to doctrine-meta.

Each phase is independently shippable and flag-gated; phase 1 delivers value (better PO
decomposition + the DAG) even before any parallelism is enabled.

---

## 10. Corrected target diagram (Mermaid)

```mermaid
flowchart LR
  A[Submit brief] --> B[Ensure target indexed]
  B --> C[PO decompose:<br/>backlog + acceptance criteria<br/>+ dependency DAG + interface contracts]
  C --> D{Wave scheduler<br/>topological layer}
  subgraph W[Wave N — independent BLs run in PARALLEL]
    direction TB
    E1[BL: implement +unit tests] --> F1[QA gate: BL's own tests] --> G1[scorer]
    E2[BL: implement +unit tests] --> F2[QA gate: BL's own tests] --> G2[scorer]
    E3[BL: implement +unit tests] --> F3[QA gate: BL's own tests] --> G3[scorer]
  end
  D --> W
  W --> H[WAVE BARRIER:<br/>integrate wave to integration<br/>conflict-resolver agent · reindex ONCE]
  H -->|more waves| D
  H -->|all waves done| I[Regression checkpoint<br/>full prior suite vs baseline]
  I --> J[Acceptance LOOP<br/>boot whole app · Playwright every AC w/ evidence<br/>fix → re-boot → re-test → accepted | escalate]
  J --> K[Merge accepted feature to target]
  K --> L[Persist evidence in-target]
  L --> M[Closure-check]
  M --> N[Doctrine-meta]
  N --> O[done]
  %% failure path (every gate/merge): investigate→fix→re-test → Janitor → escalate(Option A)
  F1 -.fail.-> X[Janitor / no-abort<br/>investigate→fix→re-test → escalate Option A]
  H -.conflict.-> X
  J -.product_bug.-> X
```

---

## 11. Evidence backing this proposal (the inventory run)

`run-20260614T025948Z-0c2a26` (inventory & stock enforcement, 4 BLs) completed clean:
`acceptance.loop.accepted` (round 1, integrity_ok=true, unverified_criteria=[]), regression
checkpoint green, evidence persisted in-target (`integration` `3028cce`). The crew's
implementation discovered the un-telegraphed concurrency requirement and shipped a correct
atomic `ExecuteUpdateAsync … WHERE Quantity >= qty` decrement inside a `TransactionScope`.
The run was **serial and reindex-dominated (~4.5h, 8 reindexes)** — the concrete motivation
for wave execution. The PO already produced an implicit dependency structure and interface
(`TryDecrementStockAsync`, the availability read value); R21 makes that explicit and
machine-checkable, which is precisely what unlocks safe parallelism.
