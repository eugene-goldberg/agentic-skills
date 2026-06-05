# ABL-0015 Calibration Campaign — closing the acceptance → triage → dispatch loop unattended

> **Status:** DRAFT (2026-06-05) — awaiting operator ratification of thresholds.
> **Operationalizes:** ABL-0015 Batch E (the single "live calibration smoke")
> and ABL-0014 §I.3 Batch E (`inject_acceptance_priors`). This is the
> execution plan that legitimizes flipping the two highest-risk flags:
> `inject_acceptance_priors` and `run_acceptance_followup`.
> **Owner:** architect proposes; operator approves each flag flip.

---

## 1. Why this campaign (the one move toward "walk away")

The mission is: point the crew at a brownfield repo, hand it a requirement,
**walk away**, come back to clean commits + an honest report. As of
2026-06-05 the crew can *deliver and self-repair* a moderate feature, but the
deliver-and-repair arc still contains **one mandatory human decision**: an
operator must record `verdict==confirmed` on each acceptance finding before
the crew is allowed to fix it (R15 gate; `run_acceptance_followup` is OFF
precisely because we cannot yet trust the classifier to self-confirm).

Remove that one decision *safely* and the arc runs unattended. That is the
single highest-leverage capability gain available — it converts "operator
orchestrates" into "crew runs the loop." This campaign builds the **evidence**
required to remove it without the framework acting on a judgment we can't yet
trust.

## 2. The trust signal we actually have (grounded)

There is **no per-finding confidence score** in the `Finding` dataclass
(`findings_ledger.py`). The calibratable trust signal is therefore the
**per-classification precision prior**, already computed by
`FindingsLedger.get_priors_for_classification(cls)` →
`{confirmed, refuted, deferred}` counts, and already surfaced to the
acceptance agent by the `inject_acceptance_priors` prompt block.

Define, per classification (primarily `product_bug`):

```
precision(cls) = confirmed(cls) / (confirmed(cls) + refuted(cls))
```

- **Deferred is excluded** from the denominator — a deferral means "real but
  not acted now," not "classifier was wrong."
- **Recall is NOT directly measurable** (no ground-truth set of all real
  bugs). We substitute two safety proxies: (a) **zero false-merge** in
  unattended runs, and (b) periodic operator spot-audit of journeys the
  agent marked **passed**, to catch false-negatives.

### 2a. Data-hygiene fix (prerequisite, small)

Today's `api_07` finding was deferred as a **duplicate** of the UI finding
(same root cause), *not* because the classifier erred. Counting that as a
non-confirm would understate precision. **Add a deferral sub-reason** so
dedup-deferrals are distinguishable:

- Convention (zero-code): operator `note` must start with `duplicate:` for
  dedup deferrals; the precision calc filters these out of the denominator
  *and* numerator.
- Or (small code): add `deferred_reason: Optional[str]` to `Finding` with
  values `duplicate | post_mvp | wont_fix_now`. Precision excludes
  `duplicate`.

Pick one before Phase 0 metrics are computed. (Recommend the note-convention
for v1 — zero schema change, reversible.)

## 3. Where the data comes from (honest about availability)

Clean-brownfield-reset strips `_brownfield/`, so **old features are largely
not re-runnable** for fresh acceptance data. The dataset accrues from:

1. **The current feature** — `search-and-discovery-2` (1 acceptance run done:
   1 confirmed `product_bug`, 1 dedup-deferred). Re-runnable.
2. **Any prior target branch whose merged code still exists** (best-effort —
   e.g. `agentic-skills-work-invoice_soft_delete` if still present): re-run
   `/run-acceptance` against it for backfill. Optional, opportunistic.
3. **Forward sprints** — `run_acceptance=True` is already the default, so
   every future sprint contributes findings + verdicts automatically. **This
   is the primary source.** The campaign therefore runs *alongside* normal
   work, not as a separate big batch.

> Realism: precision on a trustworthy N takes several sprints to accumulate.
> This is a multi-week campaign that piggybacks on real feature work, not a
> one-afternoon backfill.

## 4. Phases (each gated; each reversible)

### Phase 0 — Instrument & baseline (NO flag flips)
- Ship the §2a deferral-reason hygiene fix.
- Add a tiny read-only **precision report**: a script/endpoint that reads all
  per-feature ledgers and prints `precision(cls)`, N, and the
  confirmed/refuted/deferred breakdown (dedup-deferrals excluded). This is the
  campaign's dashboard.
- Operator triages every acceptance finding going forward
  (confirm/refute/defer-with-reason) — already the workflow; just be
  disciplined and use the `duplicate:` note convention.
- **Exit criterion:** the precision report runs and shows live numbers;
  ≥1 verdict exists for `product_bug`.

### Phase 1 — Flip `inject_acceptance_priors` ON (lower risk)
- Rationale: gives the acceptance agent its *own* accuracy history in-prompt
  so it self-calibrates classification — does **not** let it act.
- Run ≥3 acceptance passes with the flag ON.
- **Proof it helped:** `precision(product_bug)` is **non-decreasing** vs the
  Phase-0 baseline over those runs, with no rise in refuted-rate.
- **Rollback:** set `inject_acceptance_priors=false`. Pure prompt input; zero
  state change.
- **Exit criterion:** precision stable-or-up AND N(`product_bug` verdicts) ≥ 10.

### Phase 2 — Flip `run_acceptance_followup` ON, gated by precision (highest risk)
- Only for classifications clearing the precision floor (below). All others —
  and anything classified `uncertain` — **route to operator review**
  (this *is* the "honest escalation" property: crew handles what it's proven
  to be right about, escalates the rest).
- Keep the existing safety envelope: every auto-dispatched fix still clears
  **doctrine + regression gate + R15 cost cap**; on green merge, A50 syncs the
  ledger. A wrong fix cannot merge dirty — worst case is a wasted dispatch.
- **Proof it worked:** ≥1 **fully unattended** run (brief → BLs → acceptance →
  auto-confirm high-precision `product_bug` → auto-dispatch → green gate →
  merge) with **zero false-merges** and correct escalation of the
  low-confidence/uncertain findings.
- **Rollback:** set `run_acceptance_followup=false` → back to operator-gated
  dispatch (today's behavior).

## 5. Proposed thresholds (operator to ratify)

| Knob | Proposed | Rationale |
|---|---|---|
| Min verdicts per classification before trusting precision | **N ≥ 10** | small enough to reach in ~3–4 sprints; large enough to not over-trust 1–2 datapoints |
| `product_bug` precision floor to enable auto-dispatch | **≥ 0.90** | auto-dispatch is the riskiest action; one-in-ten false-positive is the ceiling, bounded further by the gate |
| Classifications eligible for auto-dispatch | `product_bug` only (v1) | other classes (`test_bug`, `data_bug`, `infra_bug`) are not engineer-fixable the same way; keep manual |
| `uncertain` findings | **never auto-dispatch** | always escalate — the honesty property |
| Auto-dispatch cost cap per run | existing `FOLLOWUP_COST_CAP` | unchanged; bounds blast radius |
| False-merge tolerance | **0** | a single false-merge halts the campaign and reverts Phase 2 |

## 6. Architect calibration (risk / proof / rollback) — whole campaign

- **Risk:** auto-dispatch is the framework's highest-risk action (acceptance
  becomes a writer acting on its own classification). Mitigations: phased
  (priors-injection before auto-action), precision-gated, gate-protected,
  cost-capped, zero-false-merge halt, every step a default-OFF flag.
- **Proof of benefit:** the mission property itself — one fully unattended
  deliver→repair→merge run with zero false-merges and correct escalation.
  Secondary: measured `product_bug` precision ≥ 0.90 over N ≥ 10.
- **Rollback:** both flags default OFF and independently revertible; reverting
  returns the system bit-for-bit to today's operator-gated behavior. No schema
  migration if the note-convention hygiene option is chosen.

## 7. Known limitations (stated, not hidden)

1. **Recall is unmeasured.** We can prove "what it dispatched was real"
   (precision) but not "it found everything." Mitigated by zero-false-merge +
   operator spot-audit of passed journeys; a true recall measure needs a
   labeled bug-injection benchmark (future work, out of scope here).
2. **Per-feature precision ≠ cross-target precision.** Early N comes mostly
   from `full-stack-fastapi-template`. Precision earned on one target does not
   guarantee another; the floor must be re-met per target before auto-dispatch
   is trusted there. (This is also the natural on-ramp to the cumulative-
   learning leg, ABL-0016→0019.)
3. **Small current N.** As of today: 1 confirmed + 1 dedup-deferred. The floor
   is far off; this is a multi-sprint campaign by construction.

## 8. Immediate next actions (if ratified)

1. Decide the §2a deferral-reason mechanism (recommend note-convention).
2. Build the Phase-0 **precision report** (read-only ledger aggregation).
3. Re-tag today's `api_07` deferral as `duplicate:` so the baseline is clean.
4. Begin accumulating: keep `run_acceptance=True` (already default); triage
   every finding with discipline.
5. Revisit at N(`product_bug`) ≥ 10 to evaluate the Phase-1 flip.

---

*Drafted 2026-06-05 by the architect after the first live acceptance →
confirm → dispatch exercise on `search-and-discovery-2`. Add to the
`CLAUDE.md` governance map on ratification.*
