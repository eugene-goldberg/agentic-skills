# Proposal: Bake retrieval-citation template into engineer/qa/scorer SKILLS.md to eliminate systemic first-attempt R5b failures

**Sprint:** run-20260524T014937Z-e74aff
**Topic:** r5b-prompt-doctrine-drift
**Invariant:** I-2 (doctrine contract — documented rule lacks pre-emptive prompt support)
**Class:** enforcement-gap (the rule fires; the prompt doesn't teach the rule)
**Direction:** tighten (tighten the SKILLS.md prompts so first attempts pass; R5b itself is unchanged)
**Evidence count:** 10

## Summary

R5b ("citations in QA/engineer artifacts ≥3 references to `mcp__retrieval__*` tools or `[retrieval: ...]` markers") fired `incomplete` on attempt=1 for **10 of 17 traces** in this sprint, including every engineer trace and 5 of 6 QA traces. Every single one recovered in ≤1 retry, so the rule works — but the cost is +30-90s per BL plus a context-bloating second invocation. The structural issue is that engineer/qa/scorer SKILLS.md describe artifacts and rubrics but don't include a citation template that satisfies R5b by construction. Agents are learning the rule by failing it. That's wasted budget on a known-shape problem.

## Evidence

All `phase=doctrine_check kind=incomplete attempt=1` events in this sprint whose `missing` field included a `<retrieval citations ... need ≥3>` string:

- `webapp/backend/traces_archive/run-20260524T014937Z-e74aff/20260524T015912Z-engineer-BL-0001-adc17221a39f/phase_events.jsonl`, line 2 — engineer BL-0001, missing citations in eng_patterns.md
- `webapp/backend/traces_archive/run-20260524T014937Z-e74aff/20260524T020943Z-qa-BL-0001-7abbc7462e43/phase_events.jsonl`, line 2 — qa BL-0001, missing citations in qa_impact.md
- `webapp/backend/traces_archive/run-20260524T014937Z-e74aff/20260524T022538Z-engineer-BL-0002-f090440d76f4/phase_events.jsonl`, line 2 — engineer BL-0002
- `webapp/backend/traces_archive/run-20260524T014937Z-e74aff/20260524T023400Z-qa-BL-0002-6c19f69569e6/phase_events.jsonl`, line 2 — qa BL-0002
- `webapp/backend/traces_archive/run-20260524T014937Z-e74aff/20260524T025219Z-engineer-BL-0004-e13009cc847c/phase_events.jsonl`, line 2 — engineer BL-0004
- `webapp/backend/traces_archive/run-20260524T014937Z-e74aff/20260524T030123Z-qa-BL-0004-4cc7d4f3d5a3/phase_events.jsonl`, line 2 — qa BL-0004 (3 missing items including citations)
- `webapp/backend/traces_archive/run-20260524T014937Z-e74aff/20260524T031858Z-engineer-BL-0005-68610653a024/phase_events.jsonl`, line 2 — engineer BL-0005, only-citations gap
- `webapp/backend/traces_archive/run-20260524T014937Z-e74aff/20260524T033926Z-qa-BL-0005-b3e90c1eb34a/phase_events.jsonl`, line 2 — qa BL-0005
- `webapp/backend/traces_archive/run-20260524T014937Z-e74aff/20260524T035646Z-engineer-BL-0006-2fe19f99b147/phase_events.jsonl`, line 2 — engineer BL-0006
- `webapp/backend/traces_archive/run-20260524T014937Z-e74aff/20260524T040711Z-qa-BL-0006-c72432e44b4f/phase_events.jsonl`, line 2 — qa BL-0006 (3 missing items including citations)

Per-rule frequency table (this sprint, derived from above):

```json
{
  "R5b_first_attempt_incompletes": 10,
  "total_post-PO_traces": 16,
  "first_attempt_pass_rate": 0.375,
  "R5b_recovery_rate": 1.0
}
```

## Proposed change

In each of `skills/eng/<doctrine>/SKILLS.md`, `skills/qa/<doctrine>/SKILLS.md`, `skills/scorer/<doctrine>/SKILLS.md`, add a **mandatory artifact footer template** under the artifact-spec section:

```markdown
## Required citations footer

The last section of your artifact MUST be titled `## Retrieval evidence` and MUST contain at least three bullets in the form:

- `[retrieval: <tool_name>]` — <one-sentence summary of what you learned and from which file/symbol>

…where `<tool_name>` is one of: `mcp__retrieval__semantic_search`, `mcp__retrieval__graph_find_similar`, `mcp__retrieval__graph_neighbors`, `mcp__retrieval__graph_summary`, `mcp__retrieval__target_status`. The orchestrator's doctrine_check parses this footer; missing or fewer than three bullets → incomplete, retry with delta-fix.
```

Additionally, in the engineer/qa role's grounding-protocol section, add: "Before writing the artifact, you MUST have made ≥3 grounded retrieval calls AND ≥1 graph_* call. The footer must cite from those exact calls."

(The graph_* requirement here is R9 cross-pollination; R9 enforcement is a separate proposal — A8/A11 in the ledger. The point here is to fix R5b in isolation by teaching the artifact template.)

## Risk

1. **Template gaming** — agents could write three bullets without having made the calls. Mitigation: the streaming-side R5/Tier-1.5 already counts actual grounded calls; the template change only addresses the citation-in-artifact half.
2. **Over-prescriptive artifact shape** — agents might omit substantive analysis in favor of the footer. Mitigation: keep the rest of the artifact-spec unchanged; the footer is additive.
3. **Brownfield vs greenfield divergence** — only brownfield doctrine currently enforces R5b. Mitigation: apply the template change only to `*/brownfield/SKILLS.md` (and `*/lg-SKILLS.md` where the current doctrine lives).

## Mitigations

- Template wording explicitly says "cite from those exact calls" to discourage fabrication.
- A follow-up framework-reviewer check could compare the cited tool names against `retrieval.jsonl` to detect drift.
- Roll out to engineer first (highest frequency), measure first-attempt pass rate on next sprint, then qa, then scorer.

## Test

Synthetic smoke: re-run the engineer role on BL-0005 with the updated SKILLS.md. Expected: `phase_events.jsonl` shows `doctrine_check kind=complete attempts=1` (not `attempts=1` after an `incomplete attempt=1`). Compare retrieval-call count: should still be ≥3, with at least one graph_* call. Repeat for one QA invocation.

Acceptance criterion: across the next full sprint, R5b first-attempt pass rate rises from current 6/16 ≈ 38% to ≥80%. If it doesn't, the template wording is wrong (not the structural premise).

## Rollback

Remove the "Required citations footer" section from the three SKILLS.md files. The R5b rule and its enforcement point are unchanged, so no orchestrator-side rollback is needed. Agents simply revert to learning R5b by failing it.
