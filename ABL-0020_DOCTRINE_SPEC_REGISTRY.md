# ABL-0020 — Doctrine-spec registry (I-2 fulfillment + per-run manifest)

> **Status: DRAFT plan — operator chose this path (Option C) at ABL-0017
> Batch 0.** Author: architect. Date: 2026-06-03. Branch:
> `cumulative_learning`.
>
> The **keystone** that unblocks ABL-0017 Stage 2 (closed-loop doctrine
> efficacy) AND discharges the standing I-2 architectural mandate. ABL-0017
> Batch 0 proved Stage 2 cannot attribute outcomes to rules without this.

---

## 1. Why this exists

I-2's architectural mandate (`ARCHITECTURE_INVARIANTS.md:129`) — *"A single
doctrine spec data structure (in code, not prose) names each rule, its
enforcement point, and a callable check"* + a meta-test — has been
**unfulfilled** since the invariants were written. Rules live as prose
(CLAUDE.md + ARCHITECTURE_INVARIANTS tables) and scattered enforcement.

Consequences this blocks:
- Stage 2 efficacy can't enumerate "which rules exist / target which
  failure class / were active in run X" (ABL-0017 Batch 0, Seam 3).
- I-2's promise — "adding an R-rule without enforcement fails CI;
  documenting a rule no code enforces is a build failure" — isn't enforced.

This ABL builds the registry (P1) + a per-run manifest (P2). Full per-rule
trigger events (P3 / A13 closure) are deferred; medium-fidelity efficacy
(ABL-0017) sits on P1+P2.

## 2. Design — the registry

A single in-code data structure, `app/services/doctrine_spec.py`:

```
ALLOWED_ENFORCEMENT_POINTS = {prompt, preflight, streaming,
                              post_validation, gate, orchestrator, flow}

@dataclass(frozen=True)
class DoctrineRule:
    id: str                      # "R5", "R10.1", "Tier1.5", "R15"
    summary: str
    enforcement_point: str       # one of ALLOWED_ENFORCEMENT_POINTS
    enforced: bool               # False = documented gap (R9/A8), explicit
    check_ref: str | None        # "module:symbol" of the enforcing code, or None
    synthetic_test: str | None   # named test that exercises the rule, or None
    targeted_failure_class: str | None   # I-6 class — the Stage-2 efficacy hook
    docs: tuple[str, ...]        # where documented

DOCTRINE_SPEC: tuple[DoctrineRule, ...] = ( ... R5 … R15, Tier1.5 … )
```

Seeded from the verified canonical tables (CLAUDE.md R-rules +
ARCHITECTURE_INVARIANTS I-2 coverage): **R5, R5b, R7, R8, R9, R10, R10.1,
R10.2, R11, R12, R13, R15, Tier1.5**. (R14 QA test-timeout lives in QA
SKILLS + pytest config; added once its enforcement point is confirmed —
not force-fit now.)

`targeted_failure_class` is the **Stage-2 hook**: it's what lets efficacy
ask "did failure class C drop while rule R (which targets C) was active."
Populated where the mapping is clear; `None` where genuinely ambiguous
(not force-fit — honesty over coverage).

## 3. Design — the I-2 meta-test

`tests/test_doctrine_spec.py` asserts, for every rule:
- `enforcement_point ∈ ALLOWED_ENFORCEMENT_POINTS`;
- `id` unique;
- **if `enforced`**: has a `check_ref` OR a `synthetic_test` (something
  verifies it) — *an enforced rule with no check is a build failure*;
- **if not `enforced`**: it's an explicitly-flagged gap (R9/A8) — so
  "documented but unenforced" is intentional, never silent;
- the registry covers the canonical rule set (guards against a rule added
  to prose but not the registry).

This is I-2's meta-test, pragmatically realized: "callable check" =
resolvable `check_ref` or named `synthetic_test`.

## 4. Design — the per-run manifest (P2)

At run start, snapshot the active registry into the A7 disk state:
extend `.orchestrator-state/<run_id>.json` with a `doctrine_manifest`:
`{harness_sha, rules: [{id, enforced}]}`. Cheap once the registry exists;
this is the per-run "which rules were in force" record Stage 2 joins
against `bl_outcomes` (already persisted) + `phase_events`.

## 5. Batches

| Batch | Scope | Test gate |
|---|---|---|
| **A — registry + meta-test** | `doctrine_spec.py` (`DoctrineRule` + `DOCTRINE_SPEC` seeded from the 13 canonical rules) + `test_doctrine_spec.py` (the I-2 meta-test). Dormant — pure data + test, zero behavior change. | meta-test green; registry covers canonical set |
| **B — per-run manifest** | snapshot `doctrine_manifest` into run_state at run start; extend the A7 schema; thread through `run_brief`/`run_state`. | manifest written + shape asserted; backward-compat load of pre-manifest state |
| **C — reconcile + mark I-2 fulfilled** | a consistency check (registry vs the CLAUDE.md prose table) so the registry is the source of truth; update ARCHITECTURE_INVARIANTS to mark the I-2 doctrine-spec mandate fulfilled; note the registry in CLAUDE.md. | consistency test; docs updated |

Batches A+B ≈ 1–1.5d. No calibration smoke needed (no agent-facing
behavior change); this is internal scaffolding.

## 6. Invariant posture

- **I-2:** this *is* the I-2 fulfillment — registry + meta-test.
- No new R-rule; no subprocess/closure impact (pure data + a state-file
  field). The manifest write rides the existing A7 checkpoint path.

## 7. Calibrated proposal

**Risk:** Low. Batch A is pure data + a test (no runtime path touches it
yet). Batch B adds one nullable field to the run-state JSON (backward
compatible). Worst case: the registry drifts from reality — mitigated by
the Batch-C consistency check that fails CI if the prose table and registry
disagree.

**Named test:** the I-2 meta-test (`test_doctrine_spec.py`) + the
manifest-shape test + the registry/prose consistency test.

**Rollback:** revert; the registry is dormant until ABL-0017 reads it, and
the manifest field is additive/nullable.

## 8. Relationship to the program

```
ABL-0020 (registry P1 + manifest P2)  ← keystone, I-2 debt
        └──> ABL-0017 (Stage 2 efficacy, medium-fidelity on P1+P2)
        (P3 / A13 per-rule trigger events deferred; would raise fidelity)
```

Start point: **Batch A** (registry + meta-test).
