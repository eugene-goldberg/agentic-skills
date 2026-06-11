# Proposal — the crew's judgment gap → the **Architect** agent (ABL-0002)

> Architect proposal, 2026-06-11. Fulfils THESIS done-condition #3 ("a Triage agent
> resolves every `awaiting_review` into rewrite/defer/split/escalate") — the
> evaluation's named **"biggest autonomy gap."** Every mechanic below is grounded in
> the live code (file:line) at ≥95% confidence; corrections to earlier framing noted.
>
> **DIRECTION (operator, 2026-06-11):** the judgment gap is filled by a NEW crew role —
> the **Architect** — NOT by widening the Janitor (which stays in its env/merge lane).
> The Architect is a SUPERSET of the "triage/adjudicator" analysed below: it (1) reviews
> the PO's work breakdown before execution, (2) critiques engineer implementations
> against the codebase's patterns + invariants, and (3) **adjudicates** a stuck BL at
> gate-exhaustion (the §B verdict space). Its SKILLS is grounded in three reference
> ecosystems (codenamev/ai-software-architect review process + pragmatic enforcer +
> ADRs; SpillwaveSolutions/architect-agent directive-creation + decision tree;
> addyosmani/agent-skills five-axis review + severity labels + anti-rationalization),
> adapted to our brownfield doctrine. **SHIPPED:** `skills/brownfield/
> brownfield-production-incremental-architect/SKILLS.md` + role registered in
> `prompts_brownfield.SKILL_PATHS["architect"]`. Wiring map: §D below.

---

## Part A — The expanded issue (what the gap actually is, grounded)

### A.0 The one-line diagnosis
The orchestrator has rich per-BL **event emission** but **no crew judgment at failure
boundaries.** Every failure seam resolves to *halt-all*, *blunt-continue*, or
*log-and-move-on* — never to a senior-engineer decision (keep fixing / re-frame /
split / defer-with-rationale / re-spec / escalate). The engineer's own retry loop
**cannot** close this because it is structurally confined to one BL spec, one
worktree, one scope.

### A.1 Correction to the earlier "root-cause directive" framing (caught at 95%)
The Tier-1 sketch said "add a root-cause-first directive to the engineer." **That
already exists.** `build_gate_fix_prompt` (`doctrine_validator.py:862-921`) Step 1
(line 904) already mandates: *"Investigate to the actual root cause… OPEN and READ the
failing test AND the source… Trace the causal chain… State the root cause to a
specific file:line before you change anything."* So the gap is **not** the absence of
root-causing. The gap is that root-causing happens **inside a fixed frame** and there
is **no step-back authority** when the frame itself is the problem.

### A.2 The three failure seams (all confirmed in code)

**Seam 1 — per-BL code-gate exhaustion → halt the sprint.**
`_engineer_flow` runs the BL's own tests and retries (`orchestrator.py:557`):
```python
while not gate.get("ok") and gate.get("kind") in ("failed","no_tests") and gate_attempt < MAX_FIX_ATTEMPTS:
```
`MAX_FIX_ATTEMPTS = 6` (`orchestrator.py:1311`). Each retry re-spawns the engineer in
the **same worktree** with the **same BL spec** + test names + a stdout excerpt (no
diff). On exhaustion it builds a thin dossier (`644-654`) and emits `escalated`; with
`stop_on_failure=True` (the **default**, `2817`) the whole sprint **stops** (`return`,
`3164`). The Janitor cannot help — it *explicitly excludes* code kinds:
`JANITOR_NONCODE_KINDS = frozenset({"error","infra_fail"})` (`920`), comment: *"Code-
defect gate kinds (failed / no_tests / regressed / inconclusive) are OWNED by the
engineer/QA no-abort loop and must NOT route here."* → **No agent ever decides whether
this BL should be re-framed, split, deferred, or is a true wall. It just halts.**

**Seam 2 — acceptance regression_checkpoint = regressed → detected, never fixed.**
`orchestrator.py:3440-3454`: the full-suite checkpoint runs, and `rc` is unpacked into
an event and `yield`ed — **there is no branch on `kind=="regressed"`**, no engineer
re-spawn, no fix loop. The block's comment (`3435`): *"Advisory here… a red is surfaced
loudly for operator action."* Worse, it runs **after** `sprint_complete` (`3335`), so a
collateral regression to pre-existing behaviour **cannot even un-set success.** → **A
merged BL breaking the rest of the app is reported and left broken.** (Under the
current simple gating model — per-BL runs only the BL's *own* tests — this is the
*primary* place cross-cutting breakage surfaces, which makes the missing recovery more
serious, not less.)

**Seam 3 — `stop_on_failure=False` → silent abandonment.**
The "continue" path (`3168`) drops the BL: the dossier rides only the `bl.escalated`
SSE event, `bl_outcomes_compact` records a bare `{"outcome":"engineer_escalated"}` with
**no reason/dossier**, and the final `sprint_complete` summary has **no escalated/
deferred roll-up** — coverage math (`merged_ids`, `3347-3350`) keeps only
`startswith("merged")`, so dropped BLs **vanish** from the report. → **"Continue" today
means *silently abandon*, not *deliberately defer*.**

### A.3 Why the existing specialists don't cover it (so this isn't a duplicate)
- **Janitor** — environment/merge repair only (`{error, infra_fail}` + `merge_error`);
  excluded from code defects by design (`916-920`).
- **Acceptance-followup** (`_finding_dispatch_eligible`, `1906-1922`) — decides only
  whether to dispatch a fix for an **acceptance-agent `product_bug` finding**,
  **post-sprint**, cost-capped to 1. Not per-BL, not code-gate, not regression.
- **Doctrine-meta** (`_doctrine_meta_flow`) — **post-`sprint_complete` post-mortem**;
  writes R-rule *proposals*, never an in-sprint decision.
- **`stop_on_failure`** — a blunt binary (halt-all / abandon-all), not a per-failure
  judgment.

### A.4 Why the engineer's loop structurally cannot self-close this
The engineer is confined to: **one BL spec** (cannot conclude the PO mis-specified),
**one worktree** (cannot split into a foundation sub-BL + remainder), **one scope**
(cannot defer itself and let the sprint proceed cleanly), and a **gate of its own tests
only** (cannot even *see* a collateral regression — that's Seam 2). So however well it
root-causes, it can only "try the same frame harder." The missing capability is **meta
to the engineer**: a step-back adjudication with authority to change the frame.

### A.5 The canonical wall this predicts (Horizon)
Horizon (Team Calendar): a `CalendarEvent` foundation BL broke login; the engineer
chased symptom specs, exhausted retries, and the sprint walled. Under today's code that
is exactly Seam 1 (if the break is in the BL's own tests) or Seam 2 (if it surfaces at
acceptance) — and in both, **no judgment fires.** A senior engineer there would have
said "this BL is really *two* — land the auth-compatible foundation first, then the
feature." Nothing in the crew can make that call.

---

## Part B — The proposal: a per-BL Triage/Adjudicator agent

### B.1 Shape (mirrors the crew's own proven pattern)
A new specialist **role** (`triage`/`adjudicator`) with a `SKILLS.md`, spawned **at a
failure seam** exactly like the Janitor/acceptance-followup are — a full Claude
subprocess that investigates with retrieval + read access, then returns a **structured
verdict**. It is **operator-gated** (flag, default OFF), **no-abort** (its fallback is
always an honest `escalate` dossier — never silent), and **bounded** (cost/segment
caps). It is the missing specialist at the *code-failure* seam, completing the set
{engineer, QA, scorer, Janitor, acceptance, doctrine-meta, triage}.

### B.2 Inputs (all already exist in the trace/state)
At Seam 1 exhaustion (`orchestrator.py:634`, before the escalate), spawn triage with:
the dossier (`last_failing_tests`, `gate_attempts`, `first_failure_signature`), the
engineer's sealed trace, the **PO's BL spec** (the backlog section), the failed attempt
branch (`agent/<task_id>`, so it can read the actual diff the engineer produced), and
the retrieval tools (grounding). It answers the question the engineer cannot:
***"why is the engineer stuck, and what should change?"***

### B.3 The verdict space (the judgment)
| Verdict | Meaning | Action | Stage |
|---|---|---|---|
| `RETRY_REFRAMED` | Engineer was close but mis-framed (wrong file, missed a prereq the triage sees in the trace). | Hand the engineer a **corrected, specific directive** (a better fix prompt than its own loop produced) + a bounded budget of fresh attempts. | **1** |
| `DEFER` | Genuinely blocked on something out of scope (a product decision; a pre-existing defect like FIND-01; an unstated dependency on a later BL). | Record a **structured deferral** (reason + what's needed) and **continue the sprint** with remaining BLs. Surfaced in the summary. | **1** |
| `ESCALATE` | A true wall a senior engineer would also hit. | Emit the rich dossier (the no-abort honest terminal). | **1** |
| `SPLIT` | The BL is really N BLs (a foundation piece must land first — the Horizon case). | Inject an **ordered sub-sequence** into the backlog ahead of the remainder; execute it. | **2** |
| `RESPEC` | The PO's spec conflicts with the codebase / is infeasible as written. | Produce a **corrected BL spec** (mini-PO step) and re-run the engineer against it. | **2** |

### B.4 Staged delivery (each behind a flag, each independently provable)

- **Stage 0 — summary truthfulness (prerequisite, cheap).** Add an `escalated`/
  `deferred` roll-up to the `sprint_complete` payload, and fix the coverage math so
  dropped BLs don't vanish (pairs with ledger **A2/A5**). Without this, no triage
  decision is *visible*. ~30 LOC + a test. **This is worth doing even if nothing else
  ships** — it closes a real *honest*-property hole (Seam 3 / A2 / A5).

- **Stage 1 — the triage core (the headline).** `triage` role + `_triage_flow`,
  spawned at Seam 1 exhaustion behind `run_triage` (default OFF). Verdicts
  `RETRY_REFRAMED` / `DEFER` / `ESCALATE`. Converts "halt the sprint" into "make a
  judgment": re-frame & retry, defer-and-continue (recorded), or escalate honestly.
  This **alone** removes the single biggest mid-sprint human dependency.

- **Stage 2 — re-scoping authority.** Add `SPLIT` + `RESPEC`. Requires the per-BL loop
  (`for it in ordered:`, `2984`) to support **dynamic insertion** of sub-BLs and a
  re-spec'd section. Higher risk (mutates the ordered backlog mid-loop) — bounded by a
  max-sub-BL cap + a global split budget. **This is the piece that directly answers the
  Horizon foundation-BL wall.**

- **Stage 3 — acceptance-regression recovery (Seam 2).** On
  `regression_checkpoint == regressed`, run triage to identify the culprit merged BL
  (rank by the failing tests × per-BL diffs) and dispatch a **fix loop** (re-spawn an
  engineer scoped to the regression) — the regression analog of the acceptance-followup
  dispatch. Also move the checkpoint **before** terminal success (or let a red un-set
  it), so a collateral regression can't ship under a green `sprint_complete`.

### B.5 Guardrails (architect discipline, grounded in existing doctrine)
- **No-abort preserved**: every triage path that can't resolve ends in `ESCALATE` +
  dossier — never silent. `DEFER` is a *recorded, surfaced* decision, the opposite of
  today's silent `stop_on_failure=False` abandonment.
- **Operator-gated authority**: `run_triage` flag default OFF; all verdicts logged +
  in the summary; `SPLIT`/`RESPEC` bounded by caps. The architect/operator can audit
  every judgment after the fact.
- **R13 / I-1 backstops apply unchanged** (triage is a normal agent: streaming git-kill,
  worktree isolation, pgroup cleanup).
- **Bounded cost**: a per-sprint triage budget (e.g. ≤1 triage per BL, ≤K splits/
  sprint) so a pathological BL can't loop forever — exhausting the budget → `ESCALATE`.

### B.6 Invariant classification (I-6 audit lens)
This is a **structural** capability (not a per-instance patch): it fulfils **ABL-0002**
(the THESIS Triage done-condition) and closes the **I-5** (truthful aggregation — Seam 3
silent drop) and autonomy gaps. New decision points register in the **I-2** doctrine
sense (each verdict is a defined, logged, bounded action with a test).

---

## Part C — Proof & calibration

**How it's proven (the headline):** re-run a **Horizon-class hard feature** (a brief
with a deliberate foundation BL that breaks existing behaviour) on a real target, flag
OFF then ON. Flag OFF reproduces the wall (Seam 1 halt or Seam 2 silent regression).
Flag ON: triage fires, the crew **self-recovers** (RETRY_REFRAMED or, in Stage 2,
SPLIT off the foundation) where it previously walled — or `DEFER`s/`ESCALATE`s with a
*structured, surfaced* rationale instead of halting/silently-dropping. That A/B is the
capability proof.

**Risk:** Medium. The variable is **judgment quality** — a wrong `DEFER`/`RETRY` wastes
a cycle (bounded by caps) and a wrong `SPLIT` mutates the backlog (Stage 2, the highest-
risk piece — gated separately, capped, default OFF). Mitigated by: default-OFF flags,
the no-abort `ESCALATE` fallback, full logging, and staged rollout (Stage 0/1 are low-
risk and independently valuable before any backlog mutation).

**Named test that proves benefit:** the Horizon-class A/B above (self-recover where it
previously walled) **+** a unit test that a synthetic exhausted-dossier drives the
triage seam to each verdict, **+** the Stage-0 test that the summary reports
escalated/deferred BLs (Seam 3 closed).

**Named rollback:** `run_triage` default OFF restores today's exact behaviour
(retry→escalate→halt). Stage 2/3 are independent flags. Stage 0 (summary roll-up) is
pure-additive observability and can ship/stay regardless.

**Honest caveats (no-overclaim):**
- Judgment quality can only be *proven* on a feature that actually hits a wall —
  additive features won't exercise it. The proof requires a deliberately hard brief.
- Stage 2 (backlog mutation mid-loop) is genuinely the riskiest change in the crew's
  control flow to date; it should not ship until Stage 1 is live-proven.
- This does not make the engineer *smarter* at code — it gives the crew a *step-back
  decision* the engineer structurally lacks. A defect that no senior engineer could fix
  in-budget still (correctly) escalates.

See [[arch_horizon_run]], `EVALUATION_2026-05-28.md` (ABL-0002), `THESIS.md` §3 #3,
`DESIGN_SHORTCOMINGS.md` A2/A5 (Seam-3 truthfulness).

---

## Part D — Architect wiring map (modes → exact seams → flags → staged)

The Architect role + SKILLS are SHIPPED. Wiring spawns it (mirroring `_janitor_flow`:
spawn a Claude subprocess, read its deterministic JSON sidecar verdict, act) at three
seams. Each behind its own default-OFF flag; rolled out in stages, lowest-risk first.

| Mode | Seam (file:line) | Flag | Verdict → orchestrator action |
|---|---|---|---|
| **Mode 3 — adjudicate** | engineer gate-exhaustion, `orchestrator.py:634` (before the `escalated` dossier is built) | `run_architect` | `retry_reframed`→re-spawn engineer with the directive + a bounded fresh budget; `defer`→record structured deferral + `continue` the sprint; `escalate`→today's dossier path; (`split`/`respec`→Stage 2) |
| **Mode 1 — plan_review** | after PO, before the BL loop (`if not skip_po:` `:2919` → `for it in ordered:` `:2984`) | `run_architect_plan_review` | `approve`→proceed; `flag`→record + proceed; `revise`/`split`→apply corrected breakdown (Stage 2 backlog mutation) |
| **Mode 2 — impl_review** | in `_engineer_flow` after the BL's own tests are green, around `merge_to_target` | `run_architect_impl_review` | `approve`→merge; `request_changes`→re-spawn engineer with the per-BLOCK directives (bounded). Scope to *high-risk* BLs (those Mode 1 flagged) to bound cost. |

**Staged rollout (each flag default OFF):**
- **Stage 0 — summary truthfulness** (Part B): `escalated`/`deferred` roll-up in
  `sprint_complete` + fix coverage math (`:3347`). Makes every Architect decision
  visible; closes the Seam-3 honesty hole (A2/A5). Prerequisite; ~30 LOC.
- **Stage 1 — Mode 3 adjudicate** with `retry_reframed`/`defer`/`escalate` only (NO
  backlog mutation). Converts "halt the sprint" into a judgment. Highest value, lowest
  structural risk. The headline. `_architect_flow` + sidecar read + the three actions.
- **Stage 2 — backlog mutation**: Mode 1 plan_review + the `split`/`respec`/`revise`
  verdicts. Requires the `for it in ordered:` loop to support dynamic sub-BL insertion +
  a re-spec'd section; bounded by a global split/respec budget → `escalate` on exhaust.
  The riskiest control-flow change to date — ships only after Stage 1 is live-proven.
- **Stage 3 — Mode 2 impl_review gate** (scoped to high-risk BLs) + acceptance-
  regression adjudication (Seam 2: on `regression_checkpoint==regressed`, run Mode 3 to
  find the culprit BL + dispatch a fix; move the checkpoint before terminal success).

**Backstops (all modes):** the Architect is a normal agent — R13 streaming git-kill,
worktree isolation, pgroup cleanup apply unchanged. It WRITES only review docs /
directives / ADRs (never feature code or refs). No-abort: every unresolved path ends in
`escalate` + dossier. Bounded: per-sprint caps on adjudications/splits → escalate on
exhaust. The `_load_skill` cache holds the new role (`maxsize` covers all 8).

**Proof:** the same Horizon-class A/B (Part C) — flag OFF reproduces the wall; Stage-1
`run_architect` ON → the Architect `retry_reframed`s or `defer`s (or Stage-2 `split`s)
where the crew previously halted, with a grounded, surfaced decision.
