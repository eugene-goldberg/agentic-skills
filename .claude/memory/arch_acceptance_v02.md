---
name: arch-acceptance-v02
description: "2026-06-05 — acceptance agent elevated to verified root-cause INVESTIGATOR (SKILLS v0.2, commit b0c9b19) + made BINDING by two enforcement companions. Operator directive: only fully verified factual intelligence, never a one-sentence hypothesis; the agent fully diagnoses so the harness routes the right fixer. Plus the ABL-0015 Calibration Campaign plan (close the triage→dispatch loop unattended)."
metadata:
  node_type: memory
  type: project
  originSessionId: 326d1623-34a0-4f02-8c13-b7359c64685d
---

Builds on [[arch-acceptance-agent]] (the operational ABL-0014 agent). This is
the **v0.2 paradigm shift**: from "report an observation + a one-sentence
hypothesis" to "ship a source-grounded, falsified root-cause dossier."

## Why (operator directive 2026-06-05)
"We are only and always interested in fully verified factual intelligence." The
acceptance agent's role is to **fully identify** each issue (root cause to the
exact source line, competing causes falsified) so the harness can invoke the
**correct fixer** (product_bug→engineer, test_bug→re-author test,
data_bug→fix seeding, infra→operator, uncertain→escalate). A one-sentence
hypothesis is no longer an acceptable output. Diagnosis ≠ capability gap — the
acceptance agent already has `Bash,Read,Write,Edit` + retrieval and the same
model; the gap was contract + schema + enforcement, all of which we control.

## SKILLS.md v0.1 → v0.2 (`skills/brownfield/brownfield-acceptance-agent/SKILLS.md`)
- Identity reframed: the crew's **diagnostic investigator** (no time pressure,
  only correctness pressure).
- New **Root-Cause Investigation Protocol** (mandatory per failure): capture
  symptom → enumerate ALL candidate causes → state each falsifier → **read the
  actual source** to trace the causal chain → falsify alternatives → conclude
  with a source-cited root cause OR an *earned* `uncertain` (full investigation
  record). Includes a routing table (classification → fix locus → fixer).
- **Evidence Discipline** now two-layer: black-box (symptom) AND white-box
  (source-traced cause). Black-box alone proves something failed, not whose
  fault it is.
- **Failure Mode Reporting** requires a verified dossier (symptom · class ·
  root_cause file:line quoted · alternatives_falsified · fix_locus · confidence).

## Binding enforcement (a SKILLS.md only demands; these make it mandatory)
1. **`acceptance_validator.py`** — a `product_bug`/`test_bug`/`data_bug` finding
   missing its dossier (a `source_refs`/`root_cause` `file:line` AND
   `alternatives_falsified`) is flagged `missing` → R10.1 retry with the gap
   named. `uncertain` must carry an investigation record; `infra_bug` exempt.
   Applies to UI journeys + api_journeys. Helpers: `_finding_field`,
   `_has_source_location`, `_validate_finding_dossier`; const
   `CODE_FAULT_CLASSIFICATIONS`, regex `_FILE_LINE_RE`.
2. **`findings_ledger.Finding`** gained `root_cause, source_refs,
   alternatives_falsified, fix_locus, confidence` (all nullable/defaulted →
   pre-v0.2 ledgers load unchanged; NOT in `_compute_finding_id` so identity is
   stable). Mapped via `_extract_dossier(primary, secondary)` in
   `_extract_finding_from_journey`. The verified intelligence now persists into
   the triage UI, the dispatch fixer's prompt, and the calibration priors —
   not truncated into `evidence_summary`.

Tests: `test_acceptance_validator.py` (7 new dossier cases + 2 fixtures made
v0.2-compliant). **Shakedown** on the completed search feature → clean
(`validator_ok`, 0 findings — but note: 0 failures means the dossier *rejection*
path is unit-tested, not yet exercised live; first live exercise = next real
product_bug).

## Calibration Campaign (`ABL-0015_CALIBRATION_CAMPAIGN.md`, governance entry 24)
The phased, evidence-gated path to close the triage→dispatch loop **unattended**
— the single highest-leverage move toward "walk away." Key facts:
- Trust signal = **per-classification precision prior** (`confirmed/(confirmed
  +refuted)` from the ledger) — there is NO per-finding confidence field.
- Dedup-deferrals (e.g. the search api_07 duplicate) excluded from precision.
- Phase 0 instrument (deferral-reason hygiene + a precision report) → Phase 1
  flip `inject_acceptance_priors` (lower risk) → Phase 2 flip
  `run_acceptance_followup` (precision-gated: product_bug ≥0.90, N≥10; zero
  false-merge halt).
- **Crucial nuance:** even ABL-0015 auto-dispatch ON still gates on
  `verdict=='confirmed'` (operator-set). Full autonomy needs **auto-confirm**
  (precision-gated), which is unbuilt — so "walk away" is more than a flag flip.
- Status: NOT started (N≈2 — search smart-views confirmed + dedup-deferred).
  Data accrues from forward sprints (acceptance is default ON).

The v0.2 investigator depth is also what RAISES product_bug precision (requiring
a falsified source-cited cause before the label), so it's the lever, not just a
measurement — and the same depth is what the *engineer* lacked in the Horizon
BL-0001 auth-break ([[arch-horizon-run]]).
