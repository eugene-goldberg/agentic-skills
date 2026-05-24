# Proposal: Forbid agent-initiated git rebase / reset --hard / push -f

**Sprint:** run-20260524T014937Z-e74aff
**Topic:** agent-initiated-rebase
**Invariant:** I-1 (resource lifecycle — agent must not mutate refs the orchestrator owns) and I-7 (self-hardening — structural changes outside operator-gated boundary)
**Class:** scope-creep + silent-failure
**Direction:** new-rule (R13: agent tool-budget hard-blocks `git rebase`, `git reset --hard`, `git push --force`, `git push -f`, `git filter-branch`, `git commit --amend` on the agent's own branch after first commit)
**Evidence count:** 4

## Summary

Two QA agents (BL-0004, BL-0006) hit `doctrine_check incomplete attempt=2` not because their artifacts were wrong, but because they had run `git rebase agentic-skills-work-v3` from inside their own Claude session. The rebase rewrote the commit SHAs the orchestrator was tracking, and the FF-merge check then failed with `HEAD is not a descendant of agentic-skills-work-v3 (agent rebased or reset history); merge would be non-ff`. The orchestrator caught the symptom (string-match in `missing`), but no R-rule prevents the cause. The agent should never mutate orchestrator-owned refs.

## Evidence

- `webapp/backend/traces_archive/run-20260524T014937Z-e74aff/20260524T030123Z-qa-BL-0004-4cc7d4f3d5a3/phase_events.jsonl`, line 3 — `phase=doctrine_check kind=incomplete attempt=2 missing=["<fast-forward to agentic-skills-work-v3: HEAD is not a descendant of agentic-skills-work-v3 (agent rebased or reset history); merge would be non-ff>"]`
- `webapp/backend/traces_archive/run-20260524T014937Z-e74aff/20260524T040711Z-qa-BL-0006-c72432e44b4f/phase_events.jsonl`, line 3 — identical non-FF incomplete on attempt=2, same root cause
- `webapp/backend/traces_archive/run-20260524T014937Z-e74aff/20260524T030123Z-qa-BL-0004-4cc7d4f3d5a3/phase_events.jsonl`, line 2 — attempt=1 failed only on artifact + citation gaps; rebase happened between attempt 1 and attempt 2, so the agent's retry behavior introduced the non-FF state
- `webapp/backend/traces_archive/run-20260524T014937Z-e74aff/20260524T040711Z-qa-BL-0006-c72432e44b4f/phase_events.jsonl`, line 2 — same pattern for BL-0006 (attempt-1 missing artifact+citations, attempt-2 only non-FF)

The two-trace pattern (different BLs, identical sequence: artifact-fix-attempt followed by rebase-induced non-FF) is the structural signal — this is not a one-off agent quirk; the role prompt or some shared instruction is teaching the agent to rebase when it sees a delta-fix prompt.

## Proposed change

Add R13 to the doctrine spec (I-2 enforcement-point table):

| Rule | Floor | Enforcement point |
|---|---|---|
| R13 | agent MUST NOT run `git rebase`, `git reset --hard`, `git push --force[/-f]`, `git filter-branch`, `git commit --amend` (after first commit), or any other history-rewriting git command on `agent/<task_id>` | streaming (Tier 1.5-style pre-execution kill on the tool_use, matching the regex on the `Bash` tool `command` field) |

Add a hard-limit clause to engineer/qa/scorer `SKILLS.md` Forbidden Tools sections: "NEVER run history-rewriting git commands on your agent branch. The orchestrator owns ref lineage. If your branch needs to be brought current, exit and let the orchestrator handle it via its A1 non-FF auto-rebase path."

Tighten I-1 commentary in `ARCHITECTURE_INVARIANTS.md`: subprocess agents own only the files in their worktree, never the refs.

## Risk

1. **False positives on benign git use** — agents might legitimately run `git log`/`git diff` and the regex misclassifies. Mitigation: anchor regex on the mutation verbs only.
2. **Engineer agents that need to amend during initial uncommitted work** — `commit --amend` before the first push is sometimes useful. Mitigation: scope the ban to *after* the first commit on the branch, or simpler: ban unconditionally and require agents to use new commits.
3. **Loss of agent ability to recover from a failed test** — Mitigation: the recovery path is "new commit on top," not rewrite history; this is already the orchestrator's preferred shape.

## Mitigations

- Regex anchored: `^git\s+(rebase|reset\s+--hard|push\s+(--force|-f)|filter-branch|commit\s+--amend)`
- Streaming-kill emits a `_meta` event with `phase=forbidden_git_op kind=killed` so the trace explains the agent's exit.
- Delta-fix prompt template (engineer/qa retries) updated to explicitly say "Do NOT rebase or reset; only add commits."

## Test

Synthetic smoke: launch one engineer agent with a prompt that includes the line "after writing your artifact, run `git rebase main` to ensure your branch is current." Expected: streaming-kill fires on the rebase tool_use; `phase_events.jsonl` records `phase=forbidden_git_op kind=killed`; no rebase occurs on disk; orchestrator surfaces the kill to the operator.

## Rollback

Revert the regex check in the streaming layer; remove the SKILLS.md clauses; remove R13 from the doctrine table. No persistent state affected because R13 is purely a runtime guard.
