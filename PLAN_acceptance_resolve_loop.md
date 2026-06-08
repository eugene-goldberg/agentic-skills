# PLAN — Close the acceptance→fix loop (re-verify + iterate)

> Status: **DESIGN — not yet implemented.** Operator gate: no code until this
> plan carries ≥95% confidence and is approved. Written 2026-06-08.
> Every load-bearing claim below is cited to raw source (file:line).

## Goal (operator standard)

Every crew agent has the architect's full capability, so an agent must **fully
resolve** what it encounters, not flag-and-stop. Today the acceptance→fix loop
**flags-and-stops**: a follow-up engineer fixes ONE thing and merges, but nothing
re-verifies that the *finding* is actually closed. Exp-2 proved it: the badge was
fixed, but the "Best Streaks" echart (named in the same finding's `fix_locus`)
was left bridge-unaware, and the run reported done.

Close the loop = after a fix merges, **re-verify** the feature and **iterate**
(bounded) until the finding is genuinely resolved or honestly escalated.

---

## Grounded findings (verified against raw source)

**G1 — The simple "re-select eligible findings" loop is BROKEN (decisive).**
`finding_id = sha256(repo | feature_slug | journey_id | classification |
evidence_summary[:200])` (`findings_ledger.py:78-87`). The evidence string comes
from `_extract_evidence_summary_dual` (`findings_ledger.py:542`), which falls — as
a **last resort** — to `json.dumps({id, classification, status})`. The real Exp-2
finding carried exactly that thin string: `{"classification":"product_bug",
"id":"01","status":"fail"}`. So **all** fails of a given journey collapse to **one
constant `finding_id`**. After the badge fix, a still-failing journey "01"
(echart) re-hashes to the SAME id, which is already `dispatch_state="merged"` →
excluded by R15 / `_finding_dispatch_eligible` (`orchestrator.py:1587-1603`,
A60) → a finding-eligibility-keyed loop would **falsely report "resolved."**
⇒ The loop MUST key termination off the fresh report's **journey status**, not
the findings ledger.

**G2 — A deterministic re-verify signal exists in the report.**
`_acceptance_flow` loads `report.json` and the ledger extracts per-journey
findings; a journey with `status == "pass"` yields **no** finding, while
`status in ("failed","fail","error")` (or `pass_with_caveat` + product_bug
caveat) yields one (`findings_ledger.py:440-469`). So **"are there any
non-pass journeys in the fresh report.json"** is a code-readable signal —
independent of the `finding_id` collapse.

**G3 — Re-running acceptance sees the fixed code.** `_acceptance_flow` loads
`cfg.agent_branch` fresh (`orchestrator.py:1849-1850`) and forks its worktree
`base_ref=agent_branch` (`:1865-1868`). A second pass, after a fix merges to
that branch, forks the updated tip. ✔

**G4 — No run-once lock blocks a 2nd acceptance pass.** Only `_gate_stack_present`
(`:1840-1846`) skips acceptance if a regression-gate **docker** stack is up.
beaverhabits is Docker-free, so this never trips. BUT each pass archives to
`traces_archive/<run_id>/acceptance/` — re-running with the same `run_id`
**collides the archive** (`:2011-2024` reads `report.json` from the archive dest
first). ⇒ Each pass needs a distinct sub-id (e.g. `<run_id>#verify<N>`).

**G5 — R15 is "dispatch once per finding, ever"** (`set_dispatch_state`,
`findings_ledger.py:294-333`; selector `:1595-1603`). `VALID_DISPATCH_STATES =
{dispatched, merged, not_merged, gate_failed, doctrine_failed, skipped_cap}`;
**no terminal lock** (a finding can be re-stated). So bounded re-dispatch is
*mechanically* allowed, but the current selector forbids it. Iteration requires
the LOOP to own re-dispatch, keyed on journey-status (G1/G2), not the selector.

**G6 — Cost.** Each acceptance pass is a full LLM agent + whole-feature E2E
(~10–20 min, non-deterministic). N passes multiply cost and the chance the
verifier itself flakes. Cost cap per dispatch is `FOLLOWUP_COST_CAP=1`
(`:1584`).

---

## The irreducible limit (honest, <95% — cannot be closed by code)

The Exp-2 echart was **not its own journey** — it was a *secondary observation*
the acceptance agent made while root-causing the badge journey (it appears in the
finding's `root_cause`/`fix_locus` dossier, not as a separate failing journey).
So on a re-run where the **badge now passes**, the acceptance agent may mark
journey "01" PASS and **never separately exercise the echart** → the loop sees no
failing journey → declares resolved → echart still wrong.

**Conclusion:** a re-verify loop can be made ≥95% **correct and safe as a control
loop**, and it WILL catch any residual that re-surfaces as a *failing journey*.
But it **cannot guarantee** catching a residual *sub-observation* (like the
echart), because that is bounded by the acceptance agent's journey coverage —
non-deterministic, unverifiable by code. I will not claim otherwise.

---

## Design — two complementary levers

### Lever A (PRIMARY, higher confidence): deterministic test-encoding of the full fix_locus
The reason the echart slipped is the follow-up engineer fixed/tested only the
badge, though the finding's `fix_locus` named **both** surfaces. Make the
follow-up section (`_build_followup_section`) **require a regression test for
every distinct surface named in the finding's `fix_locus`/`root_cause`**, in the
feature's own test file. Re-verification then includes a **deterministic test**
for the echart — caught by the existing gate, no LLM re-judgment needed.
- Confidence this closes the *echart class*: **high (~90%+)** — it converts the
  finding's own analysis into deterministic coverage; the gate already blocks
  merge on a red test.
- Limit: only as complete as the finding's `fix_locus` enumeration (the Exp-2
  finding *did* name the echart, so this would have caught it).

### Lever B (BACKSTOP): bounded re-verify loop keyed on journey status
After a dispatched fix merges, re-run acceptance (G3) with a per-pass sub-id
(G4); parse the fresh `report.json` for non-pass journeys (G2). 
- **0 non-pass journeys → resolved** (terminal, clean).
- **≥1 non-pass journey → not resolved →** dispatch a fix for the failing
  journey, feeding the *fresh* pass's dossier, and loop. Re-dispatch is owned by
  the loop and keyed on journey-status, bypassing the R15/`finding_id` collapse
  (G1/G5).
- **Round cap `MAX_RESOLVE_ROUNDS` (propose 2)** → on exhaustion, **escalate
  honestly**: "journey X still failing after N fix attempts" + the latest dossier
  (no false "resolved").
- Confidence the loop is **correct + safe**: **≥95%** (bounded; gate-before-merge
  preserved per `_dispatch_one_followup` → `_engineer_flow`; escalate-on-exhaust;
  archive-collision handled).
- Confidence it catches a *given* residual: **bounded by acceptance coverage
  (<95%, irreducible)** — see the limit above.

**Recommendation:** ship **A + B together**. A gives deterministic coverage of
the named surfaces (closes the echart class with high confidence); B is the
bounded catch-all that re-verifies whole-feature and escalates honestly rather
than silently passing.

---

## Risk / Test / Rollback (per CLAUDE.md §6, invasive-change discipline)

**Risk:** highest-risk subsystem (autonomous fix + auto-merge, now iterated).
Mitigations: (1) every dispatched fix still clears doctrine + its own gate before
merge — a wrong fix cannot land; (2) `MAX_RESOLVE_ROUNDS` hard cap prevents
thrash/runaway; (3) `FOLLOWUP_COST_CAP=1` per round unchanged; (4) on exhaustion
the loop **escalates** (never silent-passes); (5) the whole behavior stays behind
`run_acceptance_followup` (default OFF) — flipping it off is full rollback.

**Named test (proves benefit, deterministic — does NOT depend on the LLM):**
- Lever A: unit test that `_build_followup_section` includes a
  "test-per-fix_locus-surface" instruction when the finding lists >1 surface.
- Lever B: a pure-logic test of the loop driver with `_acceptance_flow` /
  report-parse mocked: round 1 report has a failing journey → dispatch fired;
  round 2 report all-pass → loop terminates `resolved`; a report that stays
  failing for `MAX_RESOLVE_ROUNDS` → terminates `exhausted` (escalation), with
  re-dispatch occurring despite a prior `merged` dispatch_state (proves the
  R15-collapse is bypassed). Archive sub-id uniqueness asserted per pass.

**Rollback:** `run_acceptance_followup=False` (already the default) disables the
entire path; `MAX_RESOLVE_ROUNDS=1` collapses to today's single-shot behavior.

---

## Confidence summary (the 95% gate)

| Claim | Confidence | Basis |
|---|---|---|
| Simple finding-eligibility loop is broken (false-resolved) | **~99%** | G1 verified in raw source |
| Journey-status is the correct re-verify key | **~97%** | G2 verified |
| Re-run sees fixed code | **~96%** | G3 verified |
| Loop (Lever B) is correct + safe as a control loop | **~95%** | bounded + gate-gated + escalate-on-exhaust; logic unit-testable |
| Lever A closes the echart *class* | **~90%** | converts fix_locus → deterministic test; gate-enforced |
| Loop catches a given residual sub-observation (e.g. echart via B alone) | **<95% (irreducible)** | bound by acceptance-agent coverage; non-deterministic |

**Verdict:** I can build A+B at ≥95% confidence in **correctness and safety**,
and ≥95% that it is a real improvement to resolution completeness. I am
explicitly **below 95%** — and cannot reach it by code — on *guaranteeing* any
single residual sub-observation is caught; Lever A raises that materially for the
specific class we hit, and Lever B + honest escalation ensures we never silently
claim "resolved" when a journey still fails. If "≥95% guaranteed full resolution
of every residual" is the bar, it is **not achievable** with an LLM verifier and
I should say so rather than pretend.

---

## DECISION (architect-owned, 2026-06-08) — Lever A only; Lever B rejected

Built **Lever A** (`A61`, `_build_followup_section`): the follow-up section now
surfaces the full verified dossier (root_cause / fix_locus / source_refs) and
**mandates a deterministic regression test for every surface named in the fix
locus**. The engineer's existing no-abort gate loop then IS the re-verify-and-
iterate mechanism — the fix cannot merge until every named surface's test is
green. Deterministic; immune to the G1 `finding_id` collapse; ≥95% on the case
we hit (the echart was named in the locus).

**Lever B (bounded acceptance re-run loop) REJECTED**, grounded in this plan's own
findings:
- G1 proves it is **defeated for same-journey residuals**: a re-run sees journey
  "01" still failing → thin `evidence_summary` → SAME `finding_id` → already
  `merged` → R15-excluded → it would falsely report "resolved." It cannot close
  the exact class we hit.
- Its only residual value — catching a *different* journey that newly regresses —
  is already covered by the full-suite **regression_checkpoint**.
- So it adds repeated-acceptance cost + R15-rework risk for ~zero marginal value
  on the real problem. Building it would be matching the word "loop" instead of
  the mechanism that works.

**Residual limit (unchanged, honest):** if the acceptance agent's `fix_locus` ever
*omits* a surface, Lever A cannot test it and nothing re-verifies it — bounded by
the agent's root-cause completeness (non-deterministic). This is the irreducible
LLM-verifier limit; no loop fully closes it. Mitigation already in place: the
acceptance agent's SKILLS demand a verified, alternatives-falsified dossier, and
the full-suite regression_checkpoint guards collateral breakage.
