# Proposal — Acceptance owns the mandatory real (non-mock) test, BINDING + auto-dispatch

> Operator directive 2026-06-12 (BINDING): *"Between the engineer, QA and acceptance
> agent one of them MUST conduct all real tests, not mocks."* Owner chosen: **Acceptance.**
> Teeth chosen: **full no-abort auto-dispatch fix loop.**

## Why acceptance (not engineer/QA)

Per-BL gates are mock-only by deliberate design (A55 scoping + briefs freeze write BLs
to "Moq, no DB"). Pushing real integration tests down to the engineer/QA per-BL layer
reintroduces the running-app/DB/auth dependency and the false-red surface A55 removed.
Acceptance already boots the real app, runs Playwright UI + API journeys against a real
DB with real auth, and **already caught** the reviews-sprint `401` (journey 03). The
capability exists; only the **enforcement** was missing.

## Root cause of the buried 401 (verified)

- `findings_ledger._extract_finding_from_journey` already produces a Finding per
  **failed** journey — **but only if that journey carries a `classification`** (+ evidence)
  in `report.json`.
- Reviews sprint journey 03 failed (`Could not save your review`) with **no
  classification** → 0 findings extracted → nothing to surface, nothing to dispatch.
- The general auto-dispatch path (`run_acceptance_followup`, ABL-0015) is calibration-gated
  OFF, so even a recorded finding would not have dispatched.

So the gap is: (1) SKILLS never *forced* every failed journey to carry a classification +
dossier, and (2) the dispatch trigger never fires for observed real-journey failures.

## Changes (branch `acceptance-anomaly-surfacing`, off `a4f6606`)

### 1. SKILLS — `brownfield-acceptance-agent/SKILLS.md`
- **Real-coverage mandate (strict):** every auth-gated **write** path (create/update/delete
  behind `[Authorize]`/login) MUST be exercised end-to-end through the **booted UI** with a
  **real authenticated session** (real JWT/cookie, real DB) — the actual UI submit, not a
  seeded API insert with a hand-injected token. This is the exact layer mock per-BL tests
  skip and where the 401 lived.
- **Finding-on-failure mandate:** every **failed / unshippable** journey MUST be recorded
  in `report.json` with `classification` + `evidence` + `confidence` + `root_cause` +
  `fix_locus` (the dossier `_build_followup_section` consumes). A failed journey with no
  classification is itself a doctrine violation.

### 2. Dispatch teeth — `_acceptance_flow`
- Auto-dispatch fires for **observed real-journey-failure findings** independent of the
  calibration-gated `run_acceptance_followup`. All acceptance findings are, by construction,
  observed failures (the ledger only extracts from failed/caveat journeys), so the gate
  becomes: *eligible candidates exist → dispatch*, keeping every existing safety rail.

### Zero-false-merge guarantee preserved
Auto-dispatch here cannot cause a bad merge because the rails are unchanged:
`classification == product_bug` gate · `confidence ≥ 0.90` (or operator-confirmed) ·
`cost_cap = 1` · R15 idempotency (`dispatch_state` filter) · **the dispatched fix must
itself clear the full doctrine+gate+merge bar** — a wrong/broken fix simply never merges.
Worst case of a misclassified finding is a wasted dispatch, not a false merge. This is why
acting on an *observed real failure* is safe even while general speculative auto-dispatch
stays calibration-gated.

### 3. Doctrine R-rule — R17 (I-2)
Register in `doctrine_spec.py` with enforcement point + resolvable check + meta-test:
> **R17** — Acceptance must execute real, non-mock E2E over every auth-gated write path;
> every failed/unshippable journey blocks "clean" and yields a classified `product_bug`
> finding that auto-dispatches the no-abort fix loop.
Mirror the row into the CLAUDE.md R-rule table + DOCTRINE.md.

### 4. Tests
- acceptance-flow: a `report.json` with a failed journey (classified) ⇒ `acceptance.anomaly`
  + `acceptance_clean=false` + finding recorded + dispatch attempted.
- `test_doctrine_spec.py` stays green with R17 added (prose↔registry consistency guard).

## Risk / test / rollback
- **Risk:** moderate — only behavior change is the dispatch trigger; SKILLS + R17 are
  additive. Contained to `_acceptance_flow` (post-`sprint_complete`; cannot un-merge shipped
  BLs — it dispatches a *new* follow-up fix BL through the normal bar).
- **Named test:** the acceptance-flow failed-journey test above + `test_doctrine_spec.py`.
- **Rollback:** revert the branch; R17 is registry-gated; nothing about already-merged BLs
  changes; the dispatch rail can be re-narrowed behind `run_acceptance_followup` in one line.

## Status
- [ ] SKILLS real-coverage + finding-on-failure mandate
- [ ] `_acceptance_flow` dispatch-on-observed-failure
- [ ] R17 in doctrine_spec + CLAUDE.md table + DOCTRINE.md
- [ ] tests green (full backend suite)
- [ ] operator merge approval → `development` + harness restart
