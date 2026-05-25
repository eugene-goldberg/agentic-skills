# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-05-24 EOD. Closes a session that delivered: A19/A20/A21/A22/A24/A25a/A25b/A26/WI3A + A32 fixes; public GitHub launch; README synthesis for outside reviewers; complete target-repo wipe + re-clone to vanilla; first BL ever merged through the full A18+R14 stack; root-causing and fixing a 30-min gate hang via defense-in-depth (framework + doctrine).

---PROMPT START---

You are picking up the agentic-skills project. **You are the architect.**
Read `CLAUDE.md` §"Your role and accountability" first.

## 1. Identity

**agentic-skills** — autonomous synthetic AI crew that adds complex features to brownfield codebases with no human in the loop for the bulk of work.

**Operator:** Eugene Goldberg. **Repo:** `/Users/eugenegoldberg/dev/ai-projects/agentic-skills`. **Public GitHub:** https://github.com/eugene-goldberg/agentic-skills (default branch `architect-prereqs`).

## 2. State at hand-off

### Branches
- `architect-prereqs` @ `7ffad52` — 45+ commits ahead of `sprint-2-orchestrator`. Pushed to GitHub.
- Target `agentic-skills-work` @ `c7ea13e` (fresh re-clone today + A32 fix + BL-0001 merge at `801847d`).

### Live processes
| | |
|---|---|
| uvicorn | port 8000, PID 98752 |
| vite | port 5173 |
| docker | torn down clean |
| Active sprint | NONE |

### Today's commits on `architect-prereqs`
1. `9142263` gate(A21/A22/A25b/A26) — truthful aggregation, lowercase compose, infra_fail kind, disk pre-flight
2. `58d9468` brownfield(A25a/A19/A20/WI3A) — infra-aware extractor, per-feature BL-0001 reset, canonical brief.md, sibling guard
3. `b2ed5c4` docs(ledger+memory) — A19-A26 closed; A27-A31 filed; arch_gate_throughput.md
4. `839cc67` chore(lg-SKILLS) — pre-existing dirty SKILLS/briefs committed
5. `d0d33d9` docs(README) — reviewer entry synthesizing 8 governance docs
6. `3c64b43` docs(README §2) — added "The team" section
7. `7ffad52` doctrine(qa) — R14 test design constraints (R14.1 TestClient, R14.2 Alembic DDL, R14.3 timeout)

### Today's commit on target `agentic-skills-work`
- `c7ea13e` gate(A32) — pytest --timeout=120 + shell timeout 900 backstop

### Sprints executed today (newest first)
1. **documents_1 (clean)** `run-20260524T220528Z-f56070` — BL-0001 MERGED at `801847d`; QA-side gate hung on `test_alembic_upgrade_downgrade_upgrade_round_trip` → A32 found + fixed
2. documents_1 (1st) `run-20260524T200334Z-1b6c40` — aborted on QA gate inconclusive (3 baseline failures)
3. documents resubmit `run-20260524T180834Z-3bbf81` — aborted, root causes A21/A22/A25/A26
4. documents (1st) `run-20260524T173501Z-653b2f` — aborted on events.jsonl tracking (A24)

## 3. What works end-to-end now

- ✅ A18 per-feature isolation (`_brownfield/features/<slug>/`)
- ✅ A19 BL numbering resets to BL-0001 per feature
- ✅ A20 canonical `brief.md` at feature root
- ✅ A21 gate never falsely green (verified 3× live)
- ✅ A22 compose names lowercased (verified live)
- ✅ A24 events.jsonl untracked, no merge blocker
- ✅ A25a/b infra-aware extractor + infra_fail kind
- ✅ A26 5GB disk pre-flight
- ✅ WI3A sibling-feature touch guard
- ✅ A32 pytest --timeout=120 prevents hangs
- ✅ R14 doctrine forbids hang-prone patterns
- ✅ Doctrine-meta self-hardening loop (R13, R5b proposals already landed via this loop)

## 4. Open items

| ID | Class | Notes |
|---|---|---|
| A8 | R9 post-validator gap | open |
| A9 | gate subprocess pgroup leak | closes in Move 3 |
| A11 | R9 streaming-side | depends on A8 |
| A27 | per-feature branch isolation | deferred until parallel sprints |
| A28 | playwright --workers 4 | one-line, defer until green sprint validated |
| A29 | PRE-phase cache | ~50% speedup post-1st-BL |
| A30 | Test Impact Analysis | 5-20× reduction |
| A31 | tiered gate | restructures merge contract |
| A33 | `.latest` log symlink stale | minor observability |

## 5. Mandatory reading order

1. `CLAUDE.md` — architect role
2. `THESIS.md` — mission + done definition
3. `README.md` — reviewer-facing synthesis (~400 lines, current)
4. `ARCHITECTURE_INVARIANTS.md` — the 7 rules
5. `DESIGN_SHORTCOMINGS.md` — audit ledger (today's A32 + A33 + A19-A31)
6. `WORKFLOW.md` — pipeline map
7. `ARCHITECT_PLAN.md` + `ARCHITECT_TRACKER.md` — 4-batch plan (A/B done, C/D pending)
8. `.claude/memory/MEMORY.md` and the `arch_*.md` files — especially `arch_active_branch.md` (state), `arch_gate_throughput.md` (A28-A31), `arch_test_hygiene.md` (A32 case study)

## 6. First-turn protocol

### Turn 1 — orient

Read all 8 mandatory files. Restate: mission, branch tip, today's commits, A32 root cause + fix, open ledger items.

### Turn 2 — verify state

```bash
git rev-parse HEAD                                    # should be 7ffad52 or descendant
ps -p 98752 -o pid,etime,comm                         # uvicorn
lsof -iTCP:5173 -sTCP:LISTEN -nP                      # vite
ls webapp/backend/.orchestrator-state/                # active runs (empty = no sprint)
git -C webapp/backend/repos/full-stack-fastapi-template log --oneline -3 agentic-skills-work
```

Target should show: `c7ea13e gate(A32)...` → `801847d BL-0001...` → `077b54a po: import...`

### Turn 3 — await direction

DO NOT start work without explicit operator approval.

## 7. Likely next moves (surface; await direction)

- **Validate A32 end-to-end:** submit another `documents_X` sprint, watch for pytest --timeout=120 firing if a hang-prone test slips through (or running clean if R14 prevented it)
- **A18-followup cleanup:** migrate two `<agentic-skills>/sprint_briefs/` files into target, delete `sprint_briefs/`
- **Move 3** (ManagedSubprocess for A9)
- **Batches C + D** of ARCHITECT_PLAN — framework-reviewer + scheduled observer
- **A28** one-line — playwright `--workers 4` post-A32-validation

## 8. Don'ts (lessons from this session)

1. **Don't claim a hang is a hang without checking the next test's PASSED line** — earlier in this session I declared a 10-min gate run "hung" when it was at 83% making progress; the REAL hang was at the next test (`test_alembic_upgrade_downgrade_upgrade_round_trip`).
2. **Don't kill a subprocess to "unblock" if you haven't read its output yet** — killing the pytest at 83% reset the gate retry budget and consumed more time than waiting for the real hang.
3. **Don't auto-classify a bug to one layer** — A32 had crew-code AND framework defenses. Both needed fixing. Defense-in-depth wins.
4. **Don't commit framework changes on `sprint-2-orchestrator`** — work continues on `architect-prereqs`.
5. **Don't trust `webapp/backend/logs/orchestrator/.latest`** — symlink is stale; use `<target>/_brownfield/features/<slug>/events.jsonl` for truth.
6. **Don't burn cache on speculative reads** — when a hang is suspected, check `docker ps` + `docker logs --tail 20` first; takes 5 seconds vs 10 minutes of waiting.

---PROMPT END---
