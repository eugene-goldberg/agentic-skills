---
name: arch_cumulative_loop_closed
description: 2026-06-08 cumulative push — A62/A63 + ABL-0016 Stage1.5 (semantic lessons) + ABL-0019 (pattern profile) shipped; ABL-0016 smoke CLEAN PASS (flag-flip justified); dev=main @ 92f8ff5
metadata: 
  node_type: memory
  type: project
  originSessionId: 2e5f9f20-4741-447b-a861-01b614d3485d
---

2026-06-08 cumulative-learning push (primary mission frontier). dev=main @ `92f8ff5`.
SHIPPED THIS SESSION (all tested, effectiveness confirmed on real bge-m3):
- **A62** self-resolved fixes self-record verdict=confirmed on merge.
- **A63** lessons render the verified A61 dossier, not the `{"status":"fail"}` blob.
- **ABL-0016 Stage 1.5** (`lessons_index.py`): SEMANTIC problem→lesson pull via
  per-target Milvus `lessons_<md5>` (bge-m3, floor 0.55, embed retry); `search_lessons`
  MCP tool + allowlist + stable `RETRIEVAL_LESSONS_REPO`; write-through on A62.
- **ABL-0019 Stage 4** (`pattern_profile.py`): per-target PATTERN PROFILE — consolidates
  per-BL `eng_patterns.md` (was written-but-never-read-back) into `patterns_<md5>`,
  `search_patterns` MCP tool, refresh hook at sprint_complete.
- **ABL-0016 smoke `run-20260608T162952Z-ed37bc` CLEAN PASS** (beaverhabits, inject_lessons=true):
  lessons injected into ALL roles (7 provenance records), regression green (126 passed,
  2/2 merged_full). → **`inject_lessons` flag-flip is evidence-justified (next operator step).**

Original (still valid) — the two structural seams lighting the read-path surfaced:

**A62 — write-TRIGGER seam.** A60/A61 self-resolution auto-confirms+merges a
`product_bug` but never wrote a ledger verdict (only the operator triage UI
did), so the crew's own autonomous fixes stayed `verdict=None` forever and the
lessons reader (filter `{confirmed,deferred}`) never surfaced them. Fix:
`_should_self_confirm(finding, merged)` in `orchestrator._dispatch_one_followup`
writes `set_verdict("confirmed", note=<crew provenance+sha>)` + emits
`acceptance.followup.self_confirmed` when a self-confirmed (verdict-None) fix
merges through the full doctrine+gate bar. Merge bar = trust gate; operator
verdicts never overwritten; advisory (I-2 unaffected); sprint-safe.

**A63 — content-QUALITY seam.** Lessons rendered the thin `evidence_summary`
(a `{"status":"fail"}` JSON blob from `_extract_evidence_summary`'s fallback)
while the SAME finding carried a rich verified A61 dossier (`root_cause`,
`fix_locus`) that sat unused. Fix: `Lesson` carries root_cause/fix_locus;
`_lesson_body()` prefers the verified dossier (cap 600 chars), falls back to
summary. Connects A61 dossiers → ABL-0016 lessons. Verified live: real
beaverhabits lesson now reads the causal chain, not the status blob.

**Live validation (smoke `run-20260608T162952Z-ed37bc`, beaverhabits,
inject_lessons=true):** PO prompt trace contained the rendered advisory lessons
block verbatim; provenance written to `logs/lessons/<run_id>.jsonl` (role=po,
count=1, the Rest-Days lesson). Read-path #1 (renders) + #2 (provenance)
CONFIRMED live. #3 (no regression via acceptance checkpoint) was pending at
hand-off. Builders read `repo_dir`=MAIN checkout (worktree created AFTER
build_*), so the untracked confirmed ledger is visible — lessons inject.

**Remaining to make ABL-0016 fully ON:** the `inject_lessons` flag is still
default-OFF; flip it after the smoke completes clean (the calibrated proposal).
Then Stage 2 (ABL-0017 closed-loop doctrine efficacy / outcome attribution).

**STAGE 2 STARTED (2026-06-08, dev=main @ `8db9d60`) — closed-loop doctrine efficacy:**
- **A13 COMPLETE** (`0d1be88`): every rule firing now seals into the per-agent
  `phase_events.jsonl` — 16 `_ptag` enforcement/disposition sites forward
  `trace=trace` (bl_tests/regression_gate/merge_*/awaiting_review), + streaming
  kills seal with `rule_id` (R8 budget, Tier1.5 pre-grounding, R13 forbidden-git);
  `_schema_version` header + `traces.read_phase_events()` reader. CI-pinned:
  `test_phase_events_sealing.py` AST-scans orchestrator, fails on ANY `_ptag`
  without `trace=`. Reframed A13 ledger from "partial" to a tested contract.
- **Efficacy aggregator** (`8db9d60`, `app/services/doctrine_efficacy.py`, ABL-0017
  Batch A): joins sealed firings × `doctrine_manifest` × `bl_outcomes` → per-rule
  fire-rate + HONEST split `never_fired_review_candidates` (observed-but-no-catch;
  a review candidate NOT a verdict — guardrail-never-tripped may = clean crew) vs
  `unobserved_rules` (phase never appeared → unassessable). Validated on real
  pre-A13 archives: emits ZERO false retirement signals (correctly buckets
  unsealed-pre-A13 rules as unobserved). n-aware confidence; failure-class causal
  attribution scaffolded but flagged (needs enforcement variation / longer series).
- **Meta-agent wiring CLOSED THE LOOP** (`015f12c`): `_doctrine_meta_flow` now
  computes the efficacy report (this run + recent archived), writes
  `traces_archive/<run>/doctrine_efficacy.json`, emits `doctrine_meta.efficacy`,
  and injects report + `retire` guidance into the agent prompt. SKILLS.md gains
  the `retire` Direction with a strict bar (eligible only from
  `never_fired_review_candidates`, NEVER `unobserved_rules`; ≥5 citations;
  "guardrail-never-tripped ≠ dead rule"). I-7 preserved (operator-gated). So
  self-hardening is now closed-loop in code.
- **Stage 2 REMAINING:** (a) optional read endpoint to surface efficacy to the
  operator; (b) accumulate POST-A13 runs so failure-class trend + real retire
  signals emerge (data, not code — pre-A13 runs under-report). **Harness restart
  needed** for the Stage-2 instrumentation (A13 sealing + meta efficacy) to go
  live in PID 9191 (predates it); only matters at the next sprint run.

**Open follow-ups (noted in ledger):** (1) `_extract_evidence_summary` JSON-blob
fallback should be improved so dossier-less findings still get prose. (2) A56
retrieval_warmup.timeout fires on cold targets (3×25s) — non-adaptive; PO still
grounds. (3) A58–A61 ledger entries were code-shipped but never filed in
DESIGN_SHORTCOMINGS.md — backfill owed. See [[arch_self_resolution_arc]],
[[arch_cumulative_learning]], [[feedback_improve_crew_not_accommodate]].
