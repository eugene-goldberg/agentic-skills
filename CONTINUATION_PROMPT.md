# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-05-28 morning. Closes a session that delivered: A36 four-part fix (PO layer-coverage + engineer tablename/auto-fix rules + pre-merge validator) — closed; A35 fix #2 (graphify-out pre-merge cleanup) — closed; A37 (qa_merge_failed handler, engineer-symmetric abort) — closed; A40 (engineer auto-fix tooling) — closed; A38 withdrawn (subsumed by A36); A37, A39, A40, A41 filed in ledger; documents_2 full-8-BL sprint completed (~7h, 1 silent-degrade incident); documents_3 3-BL validation sprint completed clean (~2.5h, zero R10 retries); meta-agent produced its first novel proposal under our observation (rejected on operator review — see §7); 23 unit tests added across A35, A36, A37; doctrine_meta + closure_check confirmed implemented + operational (CLAUDE.md corrected).

---PROMPT START---

You are picking up the agentic-skills project. **You are the architect.**
Read `CLAUDE.md` §"Your role and accountability" first.

## 1. Identity

**agentic-skills** — autonomous synthetic AI crew that adds complex features to brownfield codebases with no human in the loop for the bulk of work.

**Operator:** Eugene Goldberg. **Repo:** `/Users/eugenegoldberg/dev/ai-projects/agentic-skills`. **Public GitHub:** https://github.com/eugene-goldberg/agentic-skills (default branch `architect-prereqs`).

## 2. State at hand-off

### Branches
- `architect-prereqs` @ `05e8451` — 11 new commits this session on top of `7ffad52`. **In sync with origin.**
- Target `agentic-skills-work` — last touched by documents_2 sprint (2026-05-27 evening, 8 BLs landed).
- Target `agentic-skills-work-documents_2` — preserved for A/B comparison.
- Target `agentic-skills-work-documents_3` — preserved for A/B comparison (3 BLs landed clean).

### Live processes
| | |
|---|---|
| uvicorn | **STOPPED** (PID 78696 killed during handoff cleanup) |
| milvus-standalone | UP (~23h, infra service, leave running) |
| docker stale stacks | cleared (6 containers + 2 volumes purged at handoff) |
| Active sprint | NONE |
| Live orchestrator state | empty |

### This session's commits on `architect-prereqs` (oldest → newest)

| Commit | What |
|---|---|
| `911d099` | docs: RUNBOOK_clean_brownfield_reset.md + CLAUDE.md governance pointer |
| `a093109` | docs(runbook): Step 1.5 harness cherry-pick + conditional push |
| `116cce4` | ledger(A36): PO retrieval covers count not layer-coverage |
| `bd00b34` | ledger(A37-A41): file 4 findings + A38 withdrawal |
| `16d148c` | docs(CLAUDE.md): mark doctrine_meta + closure_check as implemented |
| `6f0551c` | fix(A36.2): PO prompt requires layer-coverage, not just retrieval count |
| `1167300` | fix(A36.3 + A40): engineer prompt tablename rule + auto-fix tooling |
| `660efd0` | fix(A36.4): pre-merge SQLModel/migration tablename consistency check + 14 tests |
| `0cddb43` | fix(A35.2): pre-merge graphify-out symlink cleanup + 3 tests |
| `7faaf37` | fix(A37): emit qa_merge_failed and abort on QA-merge failure + 3 tests |
| `05e8451` | docs(runbook): note graphify-out gitignore in Step 1.5 |

### Sprints executed this session

| Sprint | Run ID | Outcome |
|---|---|---|
| documents_2 (full 8-BL) | `run-20260527T160519Z-9811fa` | All 8 BLs merged in ~7h; 2 silent QA-merge errors (BL-0002/BL-0007 — A35 trigger, A37 reaction) → root-caused and fixed |
| documents_3 (3-BL validation) | `run-20260528T013535Z-ed1a60` | All 3 BLs merged clean in ~2.5h; zero R10 retries; engineer wrote `fix(BL-0001): A36-compliant create_table guards` showing prompt-layer awareness reached subprocess; doctrine_meta produced 1 novel proposal (rejected, see §7) |

## 3. What works end-to-end now (delta from prior handoff)

Adds, on top of the May-24 handoff list:

- ✅ **A36** — three-layer defense against SQLModel/migration tablename mismatches (PO grounding requires migration-layer citation → engineer prompt explicit rule → pre-merge validator). Validated: documents_3 BL-0001 (same surface that broke documents_2 BL-0001) shipped clean with engineer adding explicit "A36-compliant" defensive commits.
- ✅ **A35** — graphify-out collision structurally eliminated via pre-merge symlink cleanup in `fast_forward_target` + .gitignore belt-and-suspenders in runbook Step 1.5.
- ✅ **A37** — QA-merge failures emit `qa_merge_failed` event and abort under `stop_on_failure=True`, symmetric with engineer-merge path. No more silent advancement past failed merges.
- ✅ **A40** — engineer prompt directs use of `biome --apply` / `ruff --fix` / etc. before manual edits on lint-class failures.
- ✅ **doctrine_meta + closure_check** — both confirmed operational in production. CLAUDE.md previously listed them as pending; corrected.
- ✅ **Layer-coverage retrieval requirement** — PO writes "Retrieval evidence by layer" block in every per-BL `codebase_context.md` covering {model, migration, test, route, dependency, frontend build}. Verified 6/6 citations per BL across documents_3.

## 4. Open ledger items

| ID | Class | Priority | Notes |
|---|---|---|---|
| A8 | enforcement-gap (R9 post-validator) | open | from prior |
| A9 | resource-leak (gate subprocess pgroup leak) | open | closes in Move 3 |
| A11 | enforcement-gap (R9 streaming-side) | open | depends on A8 |
| A27 | per-feature branch isolation | deferred | until parallel sprints |
| A28 | playwright --workers 4 | one-line | defer until green at scale |
| A29 | PRE-phase cache | medium | ~50% speedup post-1st-BL |
| A30 | Test Impact Analysis | medium | 5-20× reduction |
| A31 | tiered gate | large | restructures merge contract |
| A33 | `.latest` log symlink stale | minor | observability only |
| **A39** | regression_gate parser conflates build-failure with all-tests-regressed | medium | filed this session — engineers recover but R10 budget burned on noise |
| **A41** | meta-agent prompt git-instruction contradiction + 0-proposals observability gap | medium | filed this session |
| **A43 candidate** | meta-agent verify-before-claim discipline | medium | implicit from §7 below; not yet filed |

**Closed this session:** A36 (4-part fix shipped + validated), A35 fix #2 (pre-merge cleanup shipped), A37 (handler shipped + validated), A40 (engineer prompt rule shipped), A38 (withdrawn).

## 5. Mandatory reading order

1. `CLAUDE.md` — architect role; doctrine_meta + closure_check claims updated this session
2. `THESIS.md` — mission + done definition
3. `README.md` — reviewer-facing synthesis
4. `ARCHITECTURE_INVARIANTS.md` — the 7 rules
5. `DESIGN_SHORTCOMINGS.md` — audit ledger; A36-A41 added/closed this session
6. `RUNBOOK_clean_brownfield_reset.md` — fresh-fork procedure; Step 1.5 updated this session
7. `WORKFLOW.md` — pipeline map
8. `ARCHITECT_PLAN.md` + `ARCHITECT_TRACKER.md` — note that Batch B (doctrine_meta + closure_check) is OPERATIONAL despite tracker possibly listing it pending — CLAUDE.md is authoritative as of this session
9. `.claude/memory/MEMORY.md` and `arch_*.md` — especially `arch_active_branch.md` (rewritten this session)

## 6. First-turn protocol

### Turn 1 — orient

Read the 9 mandatory files. Restate: mission, branch tip, this session's defect-class closures, the rejected proposal (§7), open ledger items.

### Turn 2 — verify state

```bash
cd /Users/eugenegoldberg/dev/ai-projects/agentic-skills
git rev-parse HEAD                                          # should be 05e8451 or descendant
git status                                                  # clean
ls webapp/backend/.orchestrator-state/live/ 2>/dev/null     # empty (no active sprint)
docker ps                                                   # only milvus-standalone should be running
ls .planning/doctrine_proposals/*.md | grep -v README       # see §7 — pending operator decision
```

Target should show:
```bash
cd /Users/eugenegoldberg/dev/ai-projects/brownfield-targets/full-stack-fastapi-template
git branch | grep documents      # should show agentic-skills-work-documents_2 + documents_3
```

### Turn 3 — await direction

DO NOT start work without explicit operator approval.

## 7. Pending operator decision — meta-agent's first novel proposal

The doctrine-meta-agent autonomously generated a proposal at sprint close of documents_3:

**File:** `.planning/doctrine_proposals/run-20260528T013535Z-graph-retrieval-payload-gap.md`

**Architect's verification (this session):** the proposal's central evidence is **contradicted by its own citations**. It claims `graph_neighbors`, `graph_summary`, `graph_find_similar` log only `{ts, tool}` (no input, no result count). Verified against the actual retrieval.jsonl files: 100% of the 19 graph_* entries in documents_3 traces have both `n` (count) and `path|symbol` (input). The meta-agent's mistake was assuming `semantic_search`'s field-name convention (`n_hits`) applied to graph_* tools (which use `n`); it counted `with_n_results` literally and reported 0/N for every graph tool.

**Recommended operator action (deferred to next session for owner sign-off):**
1. Move proposal to `.planning/doctrine_proposals/rejected/` with operator note
2. File **A43**: "meta-agent generated false-evidence proposal — verify-before-claim discipline not enforced today"
3. Ship minimal Layer 1 fix: tighten existing `## Evidence Discipline` section in `skills/brownfield/brownfield-production-incremental-doctrine-meta/SKILLS.md` with:
   - worked failure example (this proposal)
   - schema-uniformity-assumption rule: *"When asserting a field is missing, do not generalize one tool's schema across tools. Read 3+ records per tool, confirm the field set you assert IS the field set present."*
4. **Skip** Layer 2 (mechanical claim-check) — accepted-proposal citation formats are too variable for regex extraction; absence-claims are hard to verify automatically; the existing `## Evidence Discipline` rule already worked at review time (operator caught the error).

Architect's confidence in this plan at session end: ~85% (full investigation in transcript).

## 8. Likely next moves (surface; await direction)

In approximate priority order:
- **Act on A43** (the meta-agent proposal-rejection + Layer 1 fix). Highest signal — exercises the operator-loop and teaches the meta-agent to verify before claiming.
- **Investigate closure_check docker scope** — documents_2 ended with 8 stale per-BL containers; closure_check reported 0 violations. Either closure_check doesn't scan docker, or its pattern doesn't recognize the per-BL container naming. Latent I-3 bug. ~15 min to verify.
- **A39** — regression_gate parser fix (BL-0008 documents_2 showed 161 false regressions when build failed; fix in `regression_gate.py`).
- **A41** — meta-agent SKILLS.md prompt contradiction + proposals event observability.
- **Extend documents_3 to all 8 BLs** to validate full-pipeline behavior under the new doctrine — but not urgent (3-BL pass already validated the changed paths).
- **A28** — playwright `--workers 4` (one-line).
- **Batches C + D** of ARCHITECT_PLAN — framework-reviewer + scheduled observer.

## 9. Don'ts (lessons from this session)

Carry-forward from prior + new this session:

1. **Don't claim a hang is a hang without checking the next test's PASSED line.** (prior)
2. **Don't kill a subprocess to "unblock" if you haven't read its output yet.** (prior)
3. **Don't auto-classify a bug to one layer.** Defense-in-depth wins. (prior)
4. **Don't commit framework changes on `sprint-2-orchestrator`.** Stay on `architect-prereqs`. (prior)
5. **Don't trust `webapp/backend/logs/orchestrator/.latest`** — use `<target>/_brownfield/features/<slug>/events.jsonl` for truth. (prior)
6. **Don't burn cache on speculative reads** — check `docker ps` + `docker logs --tail 20` first. (prior)
7. **Don't trust a meta-agent proposal's claims without spot-checking the literal cited lines.** This session: the R9 proposal sounded rigorous (10 citations, schema, rollback) but its evidence was directly contradicted by the files it cited. Operator verification is non-negotiable, and the existing `## Evidence Discipline` rule is the right reviewer-side tool.
8. **Don't ship behavioral framework fixes mid-sprint.** Doctrine-version contamination invalidates the experiment. Always wait for `sprint_complete` before changing prompts/validators/orchestrator.
9. **Don't POST to `/run-brief` from a client with a finite read timeout.** Use long-lived `curl -N` (or browser SSE); StreamingResponse cancellation kills the orchestrator silently (A34 still open). Backed by direct experience this session (the first documents_2 launch died from a Python urllib timeout).
10. **Don't conflate trigger with reaction.** documents_2's QA-merge failures were two distinct defects: A35 (the graphify-out collision) + A37 (orchestrator silently advancing past it). Both needed separate fixes. Always ask "is this the cause or the consequence?"

---PROMPT END---
