---
name: arch_contract_first_phase2_4
description: Contract-First Phases A-E plan + Phase A/B shipped (parallel BL execution via contracts/stubs/mocks)
metadata: 
  node_type: memory
  type: project
  originSessionId: 59c4055b-d383-442d-a3b9-8143fb3676c3
---

Contract-First Decomposition Phases 2–4 — making BLs develop against
contracts/stubs/mocks AND run in PARALLEL. Plan: `CONTRACT_FIRST_PHASE2_4_PLAN.md`
(repo root). Operator-approved + executing 2026-06-15.

**Why:** Phase 1 (shipped, `944c259`) materializes the contract + C# stubs (R22) but
the parallel executor (`wave_concurrency>1`, already live-proven) was STARVED — the PO
decomposed horizontal layers → serial width-1 DAGs (newsletter-cf run = evidence).

**The 6 gaps (file:line verified):** (1) `backlog.contract_report:359` forced a
consumed interface to be exposed by a declared **Dependency** → serial DAG [keystone];
(2) PO doctrine layer-first not contract-first; (3) per-BL engineer prompt
(`prompts_brownfield.py:277`) stub/mock-UNAWARE; (4) `_assembler` (`orchestrator.py`)
pure merge, no stub→real binding; (5) no fan-out/DAG-width metric; (6) no live proof.

**SHIPPED (remote→GitHub→Mac, dev ahead of main):**
- `[x]` Phase A keystone — `f0315ca`. `contract_report(items, contract_first=False)`:
  when ON, a `Consumes` ANY BL `Exposes` is satisfied by the contract/stub seam, NO
  longer needs a producer `Dependency` edge (only a consume no BL exposes still fails).
  Threaded through `validate_po` + both PO-gate call sites. Wave scheduler keys only on
  Dependencies, so the PO can now leave `Dependencies: none` → fan-out. Flag-OFF
  byte-identical. 597 passed.
- `[x]` Phase B — `8bbcefe`. `backlog.dag_width(items)` (widest wave) emitted on
  `backlog_parsed`; under contract_first a serial DAG emits non-blocking
  `contract_first.fanout_advisory` (no false-fail of genuinely-serial features).
  `po_contract_instruction` extended with a Decompose-for-PARALLELISM doctrine block
  (file-disjoint vertical slices, Consumes only contract interfaces, Dependencies:none
  unless ordering). 603 passed.
- `[x]` Phase C — `e868f54`. `build_engineer_prompt_brownfield(contract_first=)` injects a
  CONTRACT-FIRST SLICE block: implement THIS slice (replace its own
  NotImplementedException stubs), MOCK any Consumed interface a sibling builds
  concurrently (never the real unmerged impl), file-disjoint, per-BL gate = own tests vs
  mocks. Threaded through `prompts.build_engineer` + `_engineer_flow` (sig + 3 call
  sites). 605 passed.
- `[x]` Phase D — `03b07e8`. **Option A chosen by operator** (per-slice DI module + binder
  composes). `contract_bind.py` pure core (parse `// @contract-module interface= impl=
  kind=<stub|real>` markers → plan_binding prefers real over stub per interface, drops
  superseded stubs, flags conflicts → render_aggregator rewrites the
  `// @contract-aggregator:begin/end` region → compute_binding). `_contract_bind`
  orchestrator step (after BLs, before acceptance, contract_first-gated): worktree →
  compose real modules + drop stubs + regen aggregator → commit → `dotnet build` →
  FF-merge; no-abort `contract_bind.escalated` on conflict/build-fail (siblings stay
  merged), clean skip when no DI modules. Materializer+engineer emit the module
  convention. 616 passed. **Pure core unit-proven; live binding awaits Phase E.**

**REMAINING:** `[ ]`
Phase E (live proof: full contract-first sprint, no max_bls cap, run_acceptance ON,
width≥2 wave + ≥2 concurrent engineers + binding swaps stub→real + acceptance catches
mock drift).

All flag-gated behind `contract_first` (default OFF). See [[arch_target_ecommerce]]
(C#/.NET substrate), [[feedback_remote_first_dev]].
