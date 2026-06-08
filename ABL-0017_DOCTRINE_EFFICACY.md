# ABL-0017 — Closed-loop doctrine efficacy (cumulative learning, Stage 2)

> **STATUS 2026-06-08: STAGE 2 STARTED. Prereqs cleared + aggregator (Batch A) shipped.**
> - **P1 doctrine-spec registry** ✅ (ABL-0020). **P2 per-run manifest** ✅ (ABL-0020).
> - **P3 per-rule trigger events (A13)** ✅ **COMPLETE** — every enforcement event
>   (16 `_ptag` sites) + streaming kills (R8/Tier1.5/R13, with `rule_id`) now seal
>   into `phase_events.jsonl`; schema header + `traces.read_phase_events`; CI-pinned
>   by `test_phase_events_sealing.py`. "Which rule fired in which run" is now
>   reconstructable from the sealed archive.
> - **Aggregator (Batch A)** ✅ `app/services/doctrine_efficacy.py` — joins sealed
>   firings × `doctrine_manifest` × `bl_outcomes` → per-rule fire-rate +
>   `never_fired_review_candidates` vs `unobserved_rules` (HONEST split: a rule
>   whose phase never appears is unassessable, NOT dead — caught on real pre-A13
>   data where gate/kill firings weren't sealed). Verified on real archives.
> - **NEXT:** wire the aggregator into the doctrine-meta-agent (consume efficacy +
>   add the `retire` Direction) + a read endpoint; accumulate post-A13 runs so the
>   failure-class trend becomes assessable. I-7 stays operator-gated: this
>   MEASURES, never auto-changes doctrine.
>
> ---
>
> **Status (original 2026-06-03): BATCH 0 VERIFICATION COMPLETE — gate did NOT cleanly pass.**
> Author: architect. Date: 2026-06-03. Branch: `cumulative_learning`.
> Stage 2 of [`CUMULATIVE_LEARNING_IMPLEMENTATION_PLAN.md`](CUMULATIVE_LEARNING_IMPLEMENTATION_PLAN.md) §4.
>
> The Batch-0 verification gate surfaced a **hard prerequisite gap**: the
> rule-attribution side of efficacy measurement cannot be built from
> existing artifacts. This is exactly what the gate exists to catch.
> **No Stage-2 code starts until the operator picks a path below.**

---

## Goal (unchanged)

Close the I-7 self-hardening loop: today doctrine-meta *proposes* rules
open-loop; Stage 2 should *measure* whether an enforced rule actually
reduced its targeted failure class, and propose retirement for rules that
don't help (operator-gated, never auto-retires).

To do that, Stage 2 must correlate **"rule R was active/triggered in run
X"** with **"run X's BL outcomes."** Batch 0 verified whether each half of
that correlation is reconstructable today.

---

## Batch 0 findings (all file:line-verified against the tip)

### Seam 1 — per-BL outcomes: ✅ READY (no new instrumentation)

Outcomes are durably persisted. `run_state.write_checkpoint`
(`run_state.py:46`, field at `:69`) writes `bl_outcomes: [{bl_id,
outcome}]` to `.orchestrator-state/<run_id>.json`, moved to
`done/<run_id>.json` on terminate (`mark_terminated`, `:82`). Outcome
vocabulary: `no_op | engineer_unmerged | merged_no_qa | merged_no_score |
merged_full`. Gate/retry detail (kind, gate_attempt, awaiting_review
reason, merge_to_target sha) is recoverable from `phase_events.jsonl` in
the archived per-agent traces. The acceptance side is in the findings
ledger. **A Stage-2 outcome label per BL per run is reconstructable from
existing artifacts.**

### Seam 2 — doctrine-meta contract: ✅ READY (retire = small extension)

`_doctrine_meta_flow` (`orchestrator.py:1643`) spawns after
`sprint_complete`, reads `traces_archive/<run_id>/`, invokes the
doctrine-meta skill (Bash/Read/Write/Edit, propose-only, I-7). Proposals
follow a fixed schema in
`skills/brownfield/brownfield-production-incremental-doctrine-meta/SKILLS.md`
with a **`Direction:` field** currently `{tighten | loosen | new-rule |
new-invariant}`. `accepted/` and `rejected/` subdirs already provide an
approval audit trail. **Adding a `retire` Direction value + SKILLS.md
guidance is a one-value extension** — the output path for retirement
proposals is cheap.

### Seam 3 — per-run active-rule recording: ❌ BLOCKED (the gate's catch)

This is where Stage 2 hits a wall. Three confirmed gaps:

1. **No doctrine-spec registry.** I-2's architectural mandate —
   "a single doctrine spec data structure (in code, not prose) names each
   rule, its enforcement point, and a callable check"
   (`ARCHITECTURE_INVARIANTS.md:129`) — is **unfulfilled**. Rules live as
   prose (`ARCHITECTURE_INVARIANTS.md` table + CLAUDE.md) plus scattered
   enforcement (`doctrine_validator.py`, `claude_agent.py` streaming,
   `orchestrator.py` retries, `regression_gate.py`). No grep-able registry
   module exists. So Stage 2 cannot programmatically enumerate "which
   rules should fire."

2. **No per-run active-rule snapshot.** Neither `meta.json` nor
   `.orchestrator-state/<run_id>.json` records which rules were in force.
   `harness_sha` (B14, `traces.py`) captures the *code version* but not
   *rule-enablement state* (a commit can document R9 while its enforcement
   is disabled — exactly the A8 case). harness_sha is a proxy, not the
   signal.

3. **Per-rule trigger events are fragmented (A13, open).** `doctrine_check`
   phase events are **aggregate** (kind=incomplete/complete/give_up +
   retry count) with **no per-rule detail**. Streaming kills (R5, R8, R13
   via Tier 1.5 in `claude_agent.py`) land in `stream.jsonl`, **not** in
   `phase_events.jsonl` — the open A13 observability gap. So "rule R fired
   in run X" is not reliably recoverable.

**Verdict:** rigorous rule→outcome correlation is **impossible from
current artifacts**. Stage 2's core premise depends on instrumentation
that does not exist.

---

## Why this is the gate working, not a failure

The Batch-0 discipline (from the program plan: *"No later-stage code
starts before its Batch 0 closes its 🔎 items"*) just prevented building
an efficacy engine on a foundation that can't carry it. Had we taken the
plan's estimate at face value, we'd have shipped retirement proposals
driven by outcome *trends* misattributed to specific rules — the kind of
plausible-but-wrong output that erodes trust (CLAUDE.md Rule 6). The
outcome side is ready; the rule side is not.

## What Stage 2 actually requires (the prerequisite)

To attribute outcomes to rules, the missing pieces are:
- **P1 — Doctrine-spec registry** (fulfils the standing I-2 mandate): a
  code dataclass mapping each rule → enforcement point → callable check,
  plus the I-2 meta-test. *Independently valuable; the project already
  committed to this.*
- **P2 — Per-run doctrine manifest**: a snapshot (in `meta.json` or
  `.orchestrator-state`) of which rules were active for the run. Cheap
  once P1 exists.
- **P3 — Per-rule trigger events** (closes A13): emit rule-fire events
  with per-rule detail into `phase_events.jsonl`. *Independently valuable;
  A13 is an open ledger item and also the §I.2 acceptance-observability
  cousin.*

P1 + P2 + P3 are the foundation; efficacy + retirement proposals sit on
top.

---

## Options for the operator (this re-sequences the roadmap)

**Option A — Proxy-efficacy v1 (no foundation work).** Build efficacy
purely on Seam-1 outcome trends + the aggregate gate/doctrine_check data
the meta-agent already scans; mark every signal `evidence_source:
indirect`; add the `retire` Direction. *Pro:* small, ships now. *Con:*
cannot attribute to a specific rule — weak, risks noisy retirement
proposals; arguably violates the 95% bar for a recommendation engine.
**Architect view: not good enough to drive rule retirement honestly.**

**Option B — Build the foundation first (recommended).** Land P1 (I-2
doctrine-spec registry + meta-test) + P2 (per-run manifest) + P3 (A13
per-rule trigger events) as the prerequisite, *then* ABL-0017 efficacy on
solid rule-attribution data. *Pro:* correct foundation; discharges two
standing debts (I-2 mandate + A13) that block more than just Stage 2.
*Con:* meaningfully larger than the plan's ~3–4d estimate; it's a detour
through architecture the project already owes itself.

**Option C — Keystone-only split.** Land P1 (registry) + P2 (manifest)
now as their own small ABL — the keystone — and accept *medium* fidelity
for v1 efficacy (we'd know which rules were active, and have aggregate —
not per-rule — trigger data, deferring full A13 closure / P3). *Pro:*
unblocks a credible efficacy v1 without the full A13 detour; the registry
is the highest-value standing debt. *Con:* trigger attribution stays
coarse until A13 closes.

**Architect recommendation:** **Option C**, leaning B. The I-2 doctrine-
spec registry (P1) is the keystone — it's a standing architectural mandate,
it makes P2 trivial, and it's the prerequisite for *rigorous* efficacy.
Build P1+P2 as a focused prerequisite ABL; sequence A13 closure (P3) next;
then efficacy. This turns a blocked Stage 2 into discharging the I-2 debt
the project has owed since the invariants were written — a real crew-brain
foundation, not a proxy.

## Decision needed

Which path (A / B / C)? No Stage-2 code proceeds until this is chosen —
and if B or C, the first deliverable is the **I-2 doctrine-spec registry**,
which I'd scope as its own ABL with batches before touching efficacy.
