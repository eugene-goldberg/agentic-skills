# Proposal: Emit doctrine-check and gate phase events to the sealed trace

**Sprint:** run-20260523T212548Z-5bfff3
**Topic:** doctrine-phase-events-unobservable
**Invariant:** I-5
**Class:** observability-gap
**Direction:** new-rule
**Evidence count:** 6

## Summary

The R-rule enforcement points (doctrine_check, pregrounding, tier_15,
regression_gate, post_validation, scorer_grounding) are documented in
`CLAUDE.md` and `ARCHITECTURE_INVARIANTS.md` §I-2 as having observable
phase events. In this sprint's sealed traces, none of those phase events
are present in any agent's `stream.jsonl`. The only phase events the
harness writes into the per-agent stream are `phase=spawn` and
`phase=exit`. Doctrine and gate outcomes presumably exist in the
orchestrator's SSE stream and disk state (`.orchestrator-state/<run_id>.json`,
`logs/orchestrator/<ts>/run.log`), but they are **not co-located with the
artifact a reviewer would re-open to verify a claim about agent X**.
Result: a meta-agent (or a human reviewer) can observe *what tools the
agent called* and *that it spawned and exited*, but cannot observe *why
the orchestrator marked it complete vs. retry vs. give-up*. Concretely
this shows up as two engineer traces (BL-0004, BL-0005) that produced
zero or near-zero retrieval and zero Write/Edit tool use, yet the
orchestrator accepted them — and nothing in those agents' sealed trace
explains the disposition. This is an I-5 observability gap that blocks
the doctrine-meta-agent from doing its job and blocks any future
adversarial reviewer from auditing rule-firing frequencies.

## Evidence

- `traces_archive/run-20260523T212548Z-5bfff3/20260523T213515Z-engineer-BL-0004-39a07842eb91/stream.jsonl` — 24 total lines; only two `phase` events: line 1 `phase=spawn`, line 24 `phase=exit`. No `phase=doctrine_check`, no `phase=pregrounding`, no `phase=tier_15`, no `phase=regression_gate`. The trace dir has no `retrieval.jsonl` at all and no Write/Edit tool use detected.
- `traces_archive/run-20260523T212548Z-5bfff3/20260523T220351Z-engineer-BL-0005-12d0a7c1934d/stream.jsonl` — 30 total lines; only two `phase` events: line 1 `phase=spawn`, line 30 `phase=exit`. `retrieval.jsonl` is 107 bytes (one record: `tool=target_status`). No Write/Edit tool use detected. The doctrine check that *should* have either retried this agent (R5 floor) or marked it incomplete is invisible inside the trace.
- `traces_archive/run-20260523T212548Z-5bfff3/20260523T223104Z-engineer-BL-0006-25a87d49309c/stream.jsonl` — 309 lines; the only `phase` events are 4× `spawn`/`exit` pairs at lines 1, 125, 126, 158, 159, 193, 194, 309 (i.e., the harness re-invoked the same agent inside one trace dir as a retry loop). No `phase=doctrine_check`, no `phase=regression_gate` even though `meta.json.prompt` explicitly says "Your previous ENGINEER run for BL-0006 PASSED doctrine but FAILED the regression gate" — the gate outcome that triggered this retry is recorded *in the prompt to the next run* but not as a discrete event in the prior run's trace.
- `traces_archive/run-20260523T212548Z-5bfff3/20260523T213539Z-qa-BL-0004-36b05cc6662f/stream.jsonl` — phase scan returns the same `spawn`/`exit`-only pattern. `phase=qa_doctrine_failed` and `phase=post_validation` (both documented R-rule enforcement points) are not present.
- `traces_archive/run-20260523T212548Z-5bfff3/20260523T220006Z-scorer-BL-0004-ce51130eb126/stream.jsonl` — same. `phase=scorer_grounding` (Tier-1.5 R12) is not present in the sealed trace; the scorer's pass/fail per rubric axis is also not surfaced as a structured `phase` record.
- `traces_archive/run-20260523T212548Z-5bfff3/20260523T235547Z-qa-BL-0006-9b2fe89bcc67/stream.jsonl` — same. The `phase=regression_gate kind=…` event that the QA→gate handoff would emit is not present.

Six independent traces, three different roles, same pattern: the
agent-side stream contains lifecycle events only; the rule-enforcement
events live elsewhere and are not sealed *next to the artifact they
describe*.

## Proposed change

Add a new doctrine rule **R13 (sealed-trace observability)**:

> Every R-rule enforcement decision (`doctrine_check`, `pregrounding`,
> `tier_15`, `qa_doctrine_failed`, `post_validation`, `scorer_grounding`,
> `regression_gate`, `doctrine_retry`, `gate_retry`) MUST be appended to
> the corresponding agent's `stream.jsonl` (or `events.jsonl` per the
> companion proposal) as a `{"type":"_meta","phase":"<name>","kind":"<outcome>","run_id":"...","task_id":"...","ts":"..."}`
> record **before** the orchestrator marks that agent terminal. The
> orchestrator must not transition `agent → complete|retry|give_up`
> without first having written the corresponding `phase=<rule>` record
> into that agent's trace dir.

Enforcement point: orchestrator step transition handlers in
`webapp/backend/app/services/orchestrator_svc.py` (and equivalent under
`langgraph_engine/`). The check is a callable predicate:
`assert_phase_event_recorded(trace_dir, expected_phase, expected_kind)`.

Test: see below.

## Risk

- Doubles writes to `stream.jsonl` from the orchestrator process, which
  is a separate process from the agent that originally owns the file.
  Concurrent writers risk interleaved lines.
- Could be perceived as widening orchestrator responsibility (I-6
  scope-creep) — but the alternative is permanent unobservability of
  doctrine outcomes, which is a worse class.
- Some existing tooling may filter `stream.jsonl` on `type=="assistant"`
  or similar; adding more `_meta` records could surprise downstream
  consumers.

## Mitigations

- Use append-only `O_APPEND` writes with line-buffered flushing on both
  sides; POSIX guarantees atomic append for writes ≤ PIPE_BUF. Phase
  records are short JSON lines (well under 4 KB). No interleaving
  hazard in practice.
- Alternative writer-location: have the orchestrator write to a sibling
  file `phase_events.jsonl` in the same trace dir, owned exclusively by
  the orchestrator process. The meta-agent reads both. Eliminates the
  cross-process append concern at the cost of one extra file. **This is
  the recommended sub-option.**
- Add an integration test (below) that fails CI if any sealed trace
  lacks a phase-record for an outcome the orchestrator clearly took.

## Test

Test name: `test_phase_events_sealed_per_agent_trace`.
Location: `webapp/backend/tests/test_trace_phase_events.py` (new).

Procedure:

1. Run a synthetic brief (one CRITICAL BL, e.g. a minimal model-addition
   BL) end-to-end with `run_doctrine_meta=false` and `auto_merge=false`.
2. After sprint terminate, for each trace dir under
   `traces_archive/<run_id>/`:
   a. Load `meta.json.role`.
   b. Compute the **expected** set of phase events for that role:
      - engineer → at least one of {`doctrine_check`, `pregrounding`,
        `tier_15`} plus exactly one terminal of {`complete`, `retry`,
        `give_up`}.
      - qa → at least one of {`qa_doctrine_failed`, `post_validation`}
        plus exactly one terminal.
      - scorer → `scorer_grounding` + a rubric-emit phase.
   c. Assert each expected phase has a record in either `stream.jsonl`
      OR sibling `phase_events.jsonl`.
3. Test fails (red) on current main; passes (green) after R13 lands.

## Rollback

- Remove the `assert_phase_event_recorded` calls from the orchestrator
  step transitions. Delete the new R13 entry from
  `ARCHITECTURE_INVARIANTS.md §I-2`. Delete the new test file. The
  orchestrator returns to its pre-R13 behavior; meta-agent loses the
  observability but the system functions as before.
- If using `phase_events.jsonl` sub-option, additionally delete those
  files from `traces/` (they are gitignored).

## Cross-reference

This proposal is structurally adjacent to existing ledger entries A8
(R9 graph-grounding floor is advisory, not enforced) and A11 (R9
streaming-side gap deepens A8). Where A8/A11 ask "why was R9 not
*enforced*", R13 asks "why can we not *observe* whether any R-rule was
enforced." Both should be addressed; landing R13 first makes A8/A11
verifiable from sealed evidence rather than from operator memory. No
duplicate proposal is being filed for R9 itself.
