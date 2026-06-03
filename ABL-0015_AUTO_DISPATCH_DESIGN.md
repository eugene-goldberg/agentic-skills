# ABL-0015 — Auto-dispatch follow-up engineer on `product_bug` acceptance findings

> **Design draft — operator approval required before any implementation.**
> Author: architect (Claude Code). Date: 2026-06-02.
> Status: **DRAFT / proposed.** Nothing here is built yet.
> Dependency: ABL-0014 §I.3 findings ledger — **satisfied** (closed
> `17919a8`). The financial-management ledger carries one real
> `product_bug` finding (`sha256:6e533e84…`, Journey 03) that is the
> first dispatch test case.

This document is grounded in a code read of the current
`architect-prereqs` tip (`db6e3fb`). Every file:line reference below was
verified against the working tree on 2026-06-02.

---

## 1. What this closes

The crew today runs:

```
brief → BACKLOG → per-BL engineer/QA/scorer → acceptance agent
      → findings ledger → STOP (operator must read + act manually)
```

The acceptance agent is the only component that sees *cross-BL*
integration bugs (per-BL QA structurally cannot — proven by Journey 03).
But its output dead-ends at the ledger: a human must read the finding,
decide it's real, and manually kick off a fix. **Auto-dispatch removes
that round-trip for unambiguous, operator-sanctioned bugs**, closing the
self-correction loop the THESIS calls for.

The loop after ABL-0015:

```
… → acceptance agent → findings ledger
      → [gate: operator policy] → auto-spawn follow-up engineer
      → doctrine_validate → regression_gate → auto-merge
      → mark finding remediated → (optional) re-run acceptance
```

---

## 2. Structural lens — invariant boundaries this crosses

Per CLAUDE.md, every move is classified against
`ARCHITECTURE_INVARIANTS.md` before implementation. ABL-0015 is the
**single highest-leverage and highest-risk action the framework takes**
because it is the first place the crew *acts on its own classification
without an operator in the loop*. It crosses two boundaries that no prior
component crossed:

| Boundary | Today | After ABL-0015 | Invariant at stake |
|---|---|---|---|
| **Acceptance becomes a writer** | Acceptance only observes + reports | Its classification spawns code changes that auto-merge | I-3 (closure), I-6 (new failure class: *false-dispatch*) |
| **Engineer gets non-PO work** | Every BL is PO-decomposed with brief refs | A synthetic remediation "BL" never went through PO | I-4 (run identity — the synthetic BL needs a traceable id) |

Two invariants must be *actively preserved*, not just not-broken:

- **I-1 subprocess lifecycle** — the follow-up engineer spawns a
  worktree + (via gate) docker stacks. Reuse of `_engineer_flow`
  inherits its `finally:`-block teardown (verified:
  `orchestrator.py:520` → `remove_worktree`, which carries the A48
  compose reaper). **No new spawn primitive is introduced** — this is the
  central safety property of the design.
- **I-3 closure postconditions** — the synthetic worktree/branch must be
  reaped before `closure_check.scan_all` runs (`orchestrator.py:1942`).
  See §6 for the one genuine gap and its fix.

A new R-rule is required (§7) and lands with its enforcement point + test
per I-2 (no rule without a callable check).

---

## 3. Verified machinery we reuse (no new primitives)

The design's safety rests on reusing existing, battle-tested machinery
rather than building a parallel path. Confirmed by code read:

| Need | Existing function | Location | Notes |
|---|---|---|---|
| Spawn engineer for one BL | `_engineer_flow(repo_dir, repo_name, bl_id, timeout, retrieval_kwargs_builder, *, run_id, feature_slug)` | `orchestrator.py:384` | Async event stream; full doctrine→gate→merge path built in |
| Worktree create | `create_worktree(repo_root, task_id=None, *, base_ref)` | `git_worktree.py:33` | `agent/<task_id>` off `cfg.agent_branch` |
| Worktree teardown (+ A48 reaper) | `remove_worktree(repo_root, wt, *, force)` | `git_worktree.py:114` | Already in `_engineer_flow`'s `finally:` |
| Doctrine validate | `validate_engineer(...)` | `doctrine_validator.py:189` | R10.1 retry at `orchestrator.py:426` |
| Gate fix prompt | `build_gate_fix_prompt(...)` | `doctrine_validator.py:827` | R10.2 retry at `orchestrator.py:452` |
| Auto-merge | `fast_forward_target(...)` + non-FF rebase fallback | `git_worktree.py:137`, `orchestrator.py` rebase path | A1 auto-rebase inherited |
| Ledger read/filter | `FindingsLedger.list_all()`, `.list_pending()`, `.set_verdict()`, `.get_priors_for_classification()` | `findings_ledger.py:129–272` | verdict ∈ {confirmed, refuted, deferred, None} |
| Event emit | `_evt(phase, **kw)` → `{"type":"_meta","phase":f"orchestrator.{phase}",…}` | `orchestrator.py:58` | mirror for `acceptance.followup.*` |

**Design principle: ABL-0015 is a *selector + invoker*, not a new
executor.** It chooses which findings to fix and calls `_engineer_flow`.
All the dangerous parts (subprocess, gate, merge, teardown) are unchanged.

**One minimal parameterization is required** (verified, not zero-change):
`_engineer_flow` builds its prompt from
`backlog_svc.extract_section(…, bl_id)` (`orchestrator.py:396–398`), and a
synthetic `BL-ACCEPT-…` has no BACKLOG entry.

> **DEVIATION (recorded at Batch C, 2026-06-02):** the design originally
> proposed a `prompt_override` that replaces the whole engineer prompt.
> Reading `build_engineer` → `build_engineer_prompt_brownfield`
> (`prompts_brownfield.py:273`) showed that all doctrine scaffolding —
> the `eng_patterns.md` artifact path, retrieval-grounding, R5b citation
> requirements — lives *inside* that builder and is keyed on `bl_id`. A
> raw prompt override would bypass it and the follow-up engineer would
> fail `validate_engineer`. The correct override is at the **`bl_section`**
> level: a new `section_override: str | None = None` param that swaps only
> the task text fed to `build_engineer`, leaving every scaffold intact. As
> shipped: `_resolve_engineer_section(repo_dir, bl_id, feature_slug,
> section_override)` returns the override verbatim (skipping the backlog
> lookup) when set. Because the artifact-path mechanics are identical to a
> normal BL, whatever lets a normal BL pass `validate_engineer` lets the
> synthetic one pass too.

The dangerous parts stay untouched — this preserves the single-executor
property. The doctrine validator needs **no** change: `validate_engineer`
(`doctrine_validator.py:189`) is generic on `bl_id` — it requires only
the engineer's own `<art>/<bl_id>/eng_patterns.md` + R5b citations
(line 219, 234), **not** a PO `codebase_context.md`. The follow-up
engineer's prompt instructs it to write that artifact under its synthetic
`bl_id` dir, and the existing gate/merge/teardown path runs unchanged.

---

## 4. Ledger schema additions (net-new dispatch state)

The current `Finding` dataclass (`findings_ledger.py:104–118`) has 13
fields and **no dispatch/remediation state** — verdict is as far as I.3
goes. ABL-0015 adds remediation tracking so a finding is dispatched *at
most once* and the operator can see outcome:

| New field | Type | Meaning |
|---|---|---|
| `dispatch_state` | `str \| None` | `None` (never dispatched) · `dispatched` · `merged` · `gate_failed` · `doctrine_failed` · `skipped_cap` |
| `dispatch_bl_id` | `str \| None` | The synthetic BL id used for the follow-up run (I-4 traceability) |
| `dispatch_run_id` | `str \| None` | run_id of the sprint that dispatched it |
| `dispatch_merged_sha` | `str \| None` | merge SHA if the fix landed |
| `dispatch_ts` | `str \| None` | ISO-8601 UTC when dispatch started |

`dispatch_state` is the **idempotency key**: a finding with any non-null
`dispatch_state` other than a retriable failure is never re-dispatched.
This prevents the "re-spawn on every sprint" failure mode.

A new ledger method mirrors `set_verdict`'s locked read-modify-write:

```
set_dispatch_state(finding_id, state, *, bl_id=None, run_id=None,
                   merged_sha=None) -> Finding   # fcntl.LOCK_EX
```

---

## 5. The dispatch flow

### 5.1 Where it hooks

Inside `_acceptance_flow`, **after** the ledger append
(`acceptance.ledger.appended`, `orchestrator.py:1374`) and **before**
the terminal `acceptance.done` (`orchestrator.py:1414`). This placement
is deliberate:

- It runs while still inside `_acceptance_flow`, so the follow-up
  engineer completes (and reaps its worktree via `_engineer_flow`'s
  `finally:`) **before** `acceptance.done` returns — which is before
  `closure_check.scan_all` at `orchestrator.py:1942`. Ordering is
  satisfied by construction (Option 1 from recon: synchronous within the
  flow).

### 5.2 The selection gate (the core safety knob)

```
candidates = [f for f in ledger.list_all()
              if f.classification == "product_bug"
              and f.dispatch_state is None
              and _verdict_gate(f.verdict)]
candidates = candidates[:cost_cap]          # default cost_cap = 1
```

`_verdict_gate` is the **operator-policy decision** (see §9, Decision 1).
Two definitions are on the table:

- **Conservative (recommended v1):** `f.verdict == "confirmed"` — only
  dispatch findings the operator has explicitly confirmed real.
- **Spec-literal:** `f.verdict != "refuted"` — dispatch confirmed *and*
  pending (un-triaged) findings; only refuted ones are excluded. This is
  what `ABL-0014…md:470` literally says, but it dispatches on the agent's
  unreviewed classification, which is materially riskier.

### 5.3 The spawn

For each candidate (capped):

```
bl_id = f"BL-ACCEPT-{run_id}-{idx}"                 # I-4 traceable
ledger.set_dispatch_state(f.finding_id, "dispatched",
                          bl_id=bl_id, run_id=run_id)
yield _evt("acceptance.followup.start", run_id=run_id,
           finding_id=f.finding_id, bl_id=bl_id,
           classification=f.classification, verdict=f.verdict)

merged_sha = None; merged = False
async for ev in _engineer_flow(repo_dir, repo_name, bl_id,
                               followup_timeout, retrieval_kwargs_builder,
                               run_id=run_id, feature_slug=feature_slug,
                               section_override=_build_followup_section(
                                   f, hypothesis=_followup_hypothesis(f))):
    # capture terminal outcome from the verified event shapes:
    if ev.get("phase") == "merge_to_target":          # orchestrator.py:509
        merged_sha = ev.get("merged_sha")
    if ev.get("_orchestrator_outcome"):               # orchestrator.py:518
        merged = bool(ev.get("merged"))
    yield ev                                          # stream sub-events

state = "merged" if merged else "not_merged"          # v1: no gate/doctrine split
ledger.set_dispatch_state(f.finding_id, state, merged_sha=merged_sha)
yield _evt("acceptance.followup.done", run_id=run_id,
           finding_id=f.finding_id, bl_id=bl_id, outcome=state,
           merged_sha=merged_sha)
```

The terminal outcome is read from two **verified** event shapes
(`orchestrator.py:509` and `:518`): the `merge_to_target` `_meta` event
carries `merged_sha`; the final `_orchestrator_outcome` dict carries the
`merged` bool. v1 records `merged` vs `not_merged` (the
`gate_failed`/`doctrine_failed` split is a post-calibration refinement).

### 5.4 The fix prompt

The follow-up engineer's initial prompt is built from the finding's
structured fields (Journey 03 shape, verified verbatim):

- `caveat.summary` → *what* is wrong (the cross-BL integration gap)
- `caveat.hypothesis` → *where* (`backend/app/api/routes/billing/invoices.py update_invoice`)
- pointer to the acceptance report + screenshots in
  `traces_archive/<run_id>/acceptance/` for evidence

This is a new prompt builder `build_followup_prompt(finding)` — distinct
from `build_fix_prompt` (doctrine) and `build_gate_fix_prompt` (gate);
it seeds the *initial* engineer task, after which the existing
R10.1/R10.2 fix prompts take over on retries.

---

## 6. Closure-check coverage — the one real gap

`_engineer_flow` reaps its own worktree (`orchestrator.py:520`), so the
**primary** teardown is covered. The gap is in the **defense-in-depth
net**: `closure_check.scan_all` (`closure_check.py:250`) scans
`.gate-worktrees/` and `.agent-worktrees/accept-{run_id}`, but a
follow-up engineer worktree is named `agent/<uuid>` in `.agent-worktrees/`
and `scan_orphan_agent_branches` is a deferred stub
(`closure_check.py:157`). So if `_engineer_flow`'s `finally:` ever fails
to reap (crash, SIGKILL), closure_check would **not** flag the orphan.

**Fix (small, lands with the feature):** name the follow-up worktree with
a scannable prefix and add a scan function:

- spawn with `task_id=f"followup-{run_id}-{idx}"`
- add `scan_stale_followup_worktrees(repo_root, run_id)` mirroring
  `scan_stale_acceptance_worktrees` (`closure_check.py:231`)
- register it in `scan_all`

This keeps I-3 honest: the closure postcondition asserts the follow-up
worktree set is empty, not just trusts the `finally:` block.

---

## 7. New doctrine rule (I-2 compliant)

| Rule | Floor | Enforcement point | Callable check |
|---|---|---|---|
| **R15** | A finding is dispatched **at most once** per its lifetime; never re-dispatched while `dispatch_state ∈ {dispatched, merged}` | dispatch selector in `_acceptance_flow` | `test_followup_idempotent` — append finding, dispatch, re-run flow, assert second pass yields zero spawns |

Per I-2, R15 lands with its enforcement point and test in the same change
or not at all.

---

## 8. Events (mirror existing `acceptance.*` pattern)

| Event | When | Key fields |
|---|---|---|
| `orchestrator.acceptance.followup.skipped` | flag off, or no eligible candidates | `run_id`, `reason` (`flag_off` / `no_candidates` / `cap_reached`) |
| `orchestrator.acceptance.followup.start` | per candidate, before spawn | `run_id`, `finding_id`, `bl_id`, `classification`, `verdict` |
| (engineer sub-events) | streamed verbatim from `_engineer_flow` | tagged `orchestrator_step="acceptance.followup"` |
| `orchestrator.acceptance.followup.done` | per candidate, after merge attempt | `run_id`, `finding_id`, `bl_id`, `outcome` (`merged`/`gate_failed`/`doctrine_failed`) |

---

## 9. Operator decisions (gray areas — your call before implementation)

> **APPROVED 2026-06-02** — operator approved all four architect
> recommendations below verbatim. v1 ships: conservative verdict gate
> (`verdict == "confirmed"`), `cost_cap = 1`, no auto re-run of
> acceptance, gate-fail → `gate_failed` + manual review (no extra retry).

**Decision 1 — verdict gate (the safety knob).** Conservative
(`verdict == "confirmed"`) vs spec-literal (`verdict != "refuted"`).
*Architect recommendation:* ship v1 **conservative** — auto-dispatch only
on operator-confirmed findings. This requires the operator to verdict the
Journey 03 finding (via Batch C/D from I.3) before it dispatches, which
is the right calibration discipline for the framework's riskiest action.
Loosen to `!= refuted` only after N clean confirmed-only dispatches, the
same default-flip discipline used for API-acceptance (§I.1).

**Decision 2 — cost cap.** BACKLOG `:258` says max 1 follow-up per
sprint to start. *Recommendation:* keep `cost_cap = 1` for v1; make it an
operator-configurable int.

**Decision 3 — re-run acceptance after the fix?** BACKLOG `:259` says
"per operator policy." *Recommendation:* v1 = **no** auto re-run (avoids
unbounded fix→accept→fix loops); the operator re-runs acceptance manually
to confirm the fix closed the finding. Revisit after calibration.

**Decision 4 — what if the follow-up gate fails?** *Recommendation:* mark
`dispatch_state = gate_failed`, leave the agent branch in place (the
existing "Review & merge" path), surface in the event stream. Do **not**
auto-retry beyond R10.2's built-in budget. Operator decides.

---

## 10. Calibrated proposal — risk / test / rollback

**Risk (explicit):** auto-spawning engineers on agent classifications is
the highest-leverage action the framework takes. Worst case: a
misclassified finding spawns an engineer that makes an unwanted change
that passes the gate (gate proves no *regression*, not *correctness*).
Mitigations: conservative verdict gate (Decision 1), cost cap of 1,
default flag OFF, idempotency (R15), and the fact that the change still
auto-merges only on `doctrine_ok AND gate green` — the same bar every
other BL clears.

**Named test that proves benefit:** an end-to-end test that seeds the
financial-management ledger with the confirmed Journey 03 finding, runs
the dispatch selector, asserts exactly one `_engineer_flow` spawn with a
prompt containing the `update_invoice` hypothesis, and asserts
`dispatch_state` transitions `None → dispatched → merged|gate_failed`.
Plus `test_followup_idempotent` (R15) and `test_followup_flag_off`
(default OFF yields zero spawns).

**Named rollback:** the feature is gated by `run_acceptance_followup:
bool = False`. Rollback = leave the flag default (or set False); the
dispatch block is a no-op and `_acceptance_flow` behaves exactly as
today. The ledger schema additions are additive/nullable, so old ledgers
load unchanged. Full revert = drop the dispatch block + the 5 schema
fields + R15; no other code path depends on them.

---

## 11. Implementation batches (proposed sequencing)

| Batch | Scope | Test gate |
|---|---|---|
| **A — schema** | Add 5 dispatch fields to `Finding` + `set_dispatch_state()` (locked) | ledger tests + backward-compat load of existing financial-management ledger |
| **B — flag plumbing** | `run_acceptance_followup: bool = False` through `RunBriefRequest` (`projects.py`) → `run_brief()` → `_acceptance_flow()`, mirroring `inject_acceptance_priors`; **+ thread `retrieval_kwargs_builder` into `_acceptance_flow`** (call site `orchestrator.py:1903`) | `test_followup_flag_off` |
| **C — dispatch block** | Selector + `build_followup_prompt` + `_engineer_flow` invocation + events, hooked between ledger.appended and acceptance.done; **+ add `prompt_override: str \| None = None` param to `_engineer_flow`** (skips `extract_section` when set) | e2e test on Journey 03 finding + R15 idempotency |
| **D — closure coverage** | `followup-{run_id}-{idx}` naming + `scan_stale_followup_worktrees` in `scan_all` | closure_check test asserting orphan detection |
| **E — first live calibration smoke** | Operator confirms Journey 03 finding, runs one sprint with flag ON, observes one dispatch | manual; produces first real auto-fix |

Batches A–D are ~3–4 days (matches the §I.4 estimate). Batch E is the
operator-gated calibration smoke that legitimizes flipping the default.

---

## 12. Verification items — RESOLVED (code-read 2026-06-02)

All three pre-coding unknowns were resolved against the working tree
before approval. Findings:

1. **Terminal merge outcome — RESOLVED.** `_engineer_flow` emits a
   `merge_to_target` `_meta` event carrying `merged_sha`
   (`orchestrator.py:509–513`) and a final
   `{"_orchestrator_outcome": True, "role":"engineer", "merged": <bool>}`
   dict (`orchestrator.py:518`). The dispatch block reads both (see §5.3).
   No change needed to `_engineer_flow`'s event contract.

2. **`retrieval_kwargs_builder` scope — RESOLVED (small thread-through).**
   It is a `run_brief` parameter (`orchestrator.py:1573`) but is **not**
   currently a `_acceptance_flow` param (signature
   `orchestrator.py:1143–1151`). Batch B threads it into `_acceptance_flow`
   alongside the new flag; it is in scope at the call site
   (`orchestrator.py:1903`). Mechanical.

3. **Synthetic `bl_id` doctrine collision — RESOLVED, smaller than
   feared.** `validate_engineer` (`doctrine_validator.py:189`) is generic
   on `bl_id`: it requires only `<art>/<bl_id>/eng_patterns.md` + R5b
   citations + a non-artifact code diff + fast-forward to base
   (lines 219, 234, 244, 274). It does **not** require any PO
   `codebase_context.md`. So **no relaxed doctrine profile is needed** —
   the follow-up engineer writes `eng_patterns.md` under its synthetic
   `bl_id` dir and passes doctrine like any BL. The **only** real blocker
   was the prompt build (`orchestrator.py:396–398`, `extract_section(bl_id)`
   on a non-existent BACKLOG entry), fixed by the `prompt_override` param
   (§3). This moves into **Batch C** scope, not a separate doctrine batch.

**Net effect on the plan:** Batch C gains one small `_engineer_flow`
signature change (`prompt_override`); Batch B gains one extra
thread-through (`retrieval_kwargs_builder`). No new batch, no
doctrine-profile work, no executor duplication. Design is at ≥95%
verified across all surfaces.
