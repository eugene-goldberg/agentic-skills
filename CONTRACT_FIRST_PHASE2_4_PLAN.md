# Contract-First Decomposition — Phases 2–4 Implementation Plan

> Author: architect, 2026-06-15. Companion to `PROPOSAL_CONTRACT_FIRST_DECOMPOSITION.md`
> (Phase 0–1, shipped). This plan covers everything still needed so that backlog
> items (BLs) **develop against the contract/stubs/mocks** and are **executed in
> PARALLEL** by the engineering agent. Operator-approved 2026-06-15 ("write a
> comprehensive implementation plan and begin executing").

## North star
A contract-first feature should run like a pro team: agree the interface (contract
+ stubs) up front, then build **file-disjoint vertical slices CONCURRENTLY** against
that contract + mocks, and integrate once. The unit of cross-slice dependency
becomes the **agreed interface (contract)**, not the upstream slice's **merged code**.

## What already exists (do NOT rebuild)
- **Parallel executor** — `wave_concurrency>1` (`orchestrator.py::_concurrent_wave_mode`)
  runs a wave's BLs concurrently on isolated work-branches + barrier-merges. LIVE-PROVEN.
- **Contract + stub materialization** — PO authors OpenAPI 3.1; Engineer materializes
  compilable C# stubs; R22 gate (validate + conformance + `dotnet build`); merged to
  `agent_branch` BEFORE any BL runs (`_contract_flow`). Phase 1, shipped.
- **R21 DAG primitives** — `backlog.adjacency/topological_waves/dependency_report`.
  The scheduler keys ONLY on `**Dependencies:**`.

## The six gaps (verified at file:line, 2026-06-15)
| # | Gap | Status | File evidence |
|---|-----|--------|---------------|
| 1 | `Consumes` forces a producer→consumer **Dependency** edge → serial DAG | **keystone** | `backlog.py:359` (`prod not in deps`) |
| 2 | PO doctrine decomposes horizontal layers, not contract-first vertical slices | partial | `skills/.../incremental-po/SKILLS.md`; engineer skill "models→repositories→services→routers" |
| 3 | Per-BL engineer prompt is contract/stub/mock-UNAWARE | missing | `prompts_brownfield.py:277` (no `contract_first` branch) |
| 4 | No barrier **binding** (stub→real swap + shared-seam assembly) | missing | `orchestrator.py:4517` (`_assembler` = pure merge) |
| 5 | No **fan-out / DAG-width metric** to gate Phase 2 | missing | `backlog_parsed` emits waves but no width metric |
| 6 | No live proof of contract-first parallel delivery | missing | newsletter run was capped + acceptance off |

**Keystone:** #1. Until a contract-satisfied `Consumes` stops forcing a producer
dependency, the DAG is structurally serial and #2–#6 cannot help.

---

## Phase A — Dependency semantics (keystone #1)  ← EXECUTING FIRST
**Change.** Add `contract_first` to `backlog.contract_report` and thread it through
`validate_po`. When `contract_first` is on, a `Consumes` token that ANY BL `Exposes`
(i.e. is part of the materialized contract/stub seam, which R22 guarantees exists +
compiles before slices run) is satisfied **by the contract** — it no longer requires
the consumer to declare the producer as a `Dependency`. Only a `Consumes` that NO BL
`Exposes` (a genuine contract gap) still fails. `Dependencies` is then reserved for
true execution-ordering needs; the scheduler (`adjacency`/`topological_waves`, which
already keys only on `Dependencies`) fans out everything not explicitly ordered.

**Files (remote).** `webapp/backend/app/services/backlog.py` (contract_report);
`webapp/backend/app/services/doctrine_validator.py` (validate_po signature + call);
`webapp/backend/app/services/orchestrator.py` (pass `contract_first` to validate_po,
lines ~399/409); `webapp/backend/app/routers/projects.py` (default False at 361/383).

**Risk.** Trusts the stub seam to provide every BL-exposed interface. Mitigated:
R22 already proves stubs compile + conform to the contract before slices run; and a
`Consumes` of an interface NO BL exposes is still flagged. Flag-OFF = byte-identical.

**Test (named).** `test_po_dag_contracts.py::test_contract_first_consume_without_dep_ok`
(flag-ON: consumer with no `Dependencies` consuming a sibling's `Exposes` passes;
flag-OFF: same input still flagged) + `..._consume_of_nonexistent_still_flagged`.

**Rollback.** `contract_first=False` default → original behavior; revert the commit.

## Phase B — Contract-first PO decomposition doctrine (#2) + fan-out metric (#5)
**Change.** (a) PO skill/prompt (`contract_first` block) instructs: produce a contract
that exposes the cross-slice service interface(s) + DTOs, then decompose into
**file-disjoint vertical slices** that each `Consumes` ONLY contract interfaces and
declare `Dependencies: none` unless true ordering is required. Reconcile the engineer
skill's layer-first language. (b) Add a DAG-width metric: emit `max_wave_width` /
`dag_fanout` on `backlog_parsed`; optionally a soft PO gate ("a human-parallelizable
feature should yield a width≥2 wave") that drives the doctrine retry loop.
**Risk.** Doctrine quality is probabilistic; gate softly first (warn), harden later.
**Test.** `test_fanout_metric` (linear DAG → width 1; diamond → width ≥2);
PO-prompt block presence test. **Rollback.** flag-gated prompt block; metric is additive.

## Phase C — Per-BL engineer builds against stubs + mocks (#3)
**Change.** Add a `contract_first` branch to `build_engineer_prompt_brownfield`:
build against the materialized contract interfaces/stubs; **mock** any collaborator
interface not yet implemented (siblings run concurrently, unmerged); unit tests run
against mocks (per-BL gates are already mock-only). 
**Risk.** Mock drift vs real wiring — caught by the no-mock acceptance checkpoint (R17/R20).
**Test.** prompt-builder test asserting stub/mock guidance present iff `contract_first`.
**Rollback.** flag-gated prompt branch.

## Phase D — Barrier binding: stub→real swap + shared-seam assembly (#4)
**Change.** After a wave's concurrent slices barrier-merge, run a **binding** step that
(a) rebinds DI from `interface→stub` to `interface→real impl`, (b) deterministically
assembles the shared wiring files (DI registration / Program.cs / routing) that the
stub commit + multiple slices all touch, (c) confirms the composed solution
`dotnet build`s green. Surface conflicts no-abort (escalate, siblings stay merged).
**Risk.** Highest-complexity item; several valid designs. Start with: slices keep
real impls in disjoint files + register via a single additive DI extension method the
binder regenerates from the merged impls. **Test.** `test_binding_swaps_stub_for_real`
+ assembly-conflict escalation test. **Rollback.** flag-gated; without it, flag-ON path
is blocked at assembly (fail-safe), flag-OFF unaffected.

## Phase E — Live proof (#6)
**Change.** Run a full contract-first sprint on `fullstack-ecommerce-app` — **no
`max_bls` cap, `run_acceptance: true`** — and verify: width≥2 wave, ≥2 engineers
running concurrently, binding produces a real (non-stub) app, acceptance (no-mock)
exercises the real endpoints and catches any mock drift. Capture as `[x]` live-proof.

---

## Execution rules
- **Remote-first** (`192.168.12.180`): every code change edited + `pytest`-green on the
  remote venv, then synced remote → GitHub → Mac.
- **Flag-gated, default OFF**: all new behavior behind `contract_first` (Phase A–D).
  Flag-OFF path stays byte-identical; each phase independently revertible.
- **95% + no-abort**: each phase lands only when its named test is green on the remote.

## Status
- [x] Phase A — dependency semantics (keystone) — **DONE, tested green on remote
  (597 passed, 0 regressions; 3 new tests in `test_po_dag_contracts.py`). UNCOMMITTED.**
- [x] Phase B — PO doctrine + fan-out metric — **DONE, tested green on remote (603 passed; dag_width metric + fanout advisory + PO decomposition doctrine; 6 new tests).**
- [x] Phase C — engineer stubs/mocks — **DONE, tested green on remote (605 passed; contract_first engineer block: build against stubs, mock unmerged collaborators, file-disjoint; threaded build_engineer + _engineer_flow x3 call sites; 2 new tests).**
- [x] Phase D — barrier binding (Option A: per-slice DI module + binder composes) — **DONE, tested green on remote (616 passed; contract_bind.py pure core parse/plan/render/compute + 9 tests; _contract_bind orchestrator step: worktree -> compose real DI modules + drop stubs + regenerate aggregator + dotnet build + FF-merge, no-abort escalate, wired before acceptance; materializer+engineer module conventions; 11 new tests). Pure core unit-proven; live binding awaits Phase E.**
- [x] Phase E — live proof — **LIVE-PROVEN 2026-06-16 (run-20260616T035453Z-9ef193, fullstack-ecommerce-app / catalog-extras-cf): dag_width=2 fan-out, contract.materialized (R22), concurrent wave both BLs merged_full, contract_bind.done ok=true (real impl bound + dotnet build green), regression checkpoint, acceptance self-healed 11 anomalies via reround -> loop.accepted + integrity_ok=true -> sprint_complete. Surfaced+fixed 2 bugs: login-shell PATH (operational) + _contract_bind missing local import subprocess.**
