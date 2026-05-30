# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-05-30 ~15:00Z (mid-day). This session: A43 Layer 1
> shipped; A44 (StreamReader 64 MiB) shipped; `/init-feature` endpoint +
> UI shipped (operator no longer needs to know the runbook exists);
> EVALUATION_2026-05-28.md filed; HARNESS.md teaching doc written;
> `tools/ui_tour/` operator-side visual inspection tool built + validated;
> Acceptance Agent SKILLS.md drafted (ABL-0010, pending wiring); time-
> tracking sprint **in flight** on BL-0014 (last BL) after operator hand-
> patches rescued BL-0007 + BL-0012 from auto-aborts.

---PROMPT START---

You are picking up the agentic-skills project. **You are the architect.**
Read `CLAUDE.md` §"Your role and accountability" first.

## ⚠️ PRIORITY 1 — execute these BEFORE anything else in the new session

These actions are time-sensitive and grounded in evidence the operator
needs immediately. Do not skip, defer, or re-prioritize without operator
override.

### P1.1 — Check the time-tracking sprint terminal state (1 min)
The sprint was running BL-0014 (Settings) when this prompt was written.
Either it finished cleanly, aborted, or is still running. Run:

```bash
EV=/Users/eugenegoldberg/dev/ai-projects/brownfield-targets/full-stack-fastapi-template/_brownfield/features/time-tracking/events.jsonl
python3 -c "
import json
events = [json.loads(l) for l in open('$EV') if l.startswith('{')]
meta = [e for e in events if e.get('type')=='_meta']
print('terminate:', [e['phase'] for e in meta if 'sprint_complete' in e['phase'] or 'aborted' in e['phase']])
print('BL outcomes:')
for e in meta:
    if e.get('phase')=='orchestrator.bl.done':
        print(f'  {e[\"bl_id\"]}: {e.get(\"outcome\",\"?\")}')
"
```
Then report the operator:
- If `sprint_complete`: total BLs landed, what doctrine_meta proposed
- If `aborted`: which BL, what failure class — triage options
- If still running: current BL, how many BLs to go

### P1.2 — Verify all artifacts pushed and sync clean (30 sec)
```bash
cd /Users/eugenegoldberg/dev/ai-projects/agentic-skills
git status -s              # MUST be clean
git log --oneline @{u}..HEAD   # MUST be empty (no unpushed)
```
Current expected tip: `3528cad docs(harness): HARNESS.md + tools/ui_tour + Acceptance Agent SKILLS.md draft`.
If anything is uncommitted/unpushed from your work, commit + push before
doing anything else.

### P1.3 — Run the acceptance UI tour against the final time-tracking state (~5 min wall-time)
After P1.1 confirms whether the sprint is done, run:
```bash
./tools/ui_tour/ui_tour.sh time-tracking
```
This captures full-page screenshots of every important UI route the sprint
delivered. Print the absolute paths to the operator. They asked for
empirical evidence of what was built — this is the cheapest answer.
If sprint aborted mid-BL, run against whatever state IS on the branch.

### P1.4 — Surface the Acceptance Agent proposal for operator decision
The `skills/brownfield/brownfield-acceptance-agent/SKILLS.md` draft sits
uncommitted to orchestrator wiring. The operator agreed in principle to
ABL-0010 (Acceptance Agent role that runs after sprint_complete and
exercises end-to-end user journeys). Pending decisions:
1. Wire it into `orchestrator.run_brief` behind a `run_acceptance: bool=True`
   flag in RunBriefRequest?
2. Build the prompt builder + validator + tests next?
3. Smoke-run it against the time-tracking sprint as first real test?

Ask the operator which of (1)/(2)/(3) to start with.

---

## 1. Identity

**agentic-skills** — autonomous synthetic AI crew that adds complex features
to brownfield codebases with no human in the loop for the bulk of work.

**Operator:** Eugene Goldberg.
**Repo:** `/Users/eugenegoldberg/dev/ai-projects/agentic-skills`.
**Public GitHub:** https://github.com/eugene-goldberg/agentic-skills (default branch `architect-prereqs`).

## 2. State at hand-off

### Branches
- `architect-prereqs` @ `3528cad` — **in sync with origin.** 5 commits this session on top of `0b8f79d`.
- Target `time-tracking` — last touched by the in-flight 14-BL sprint (see P1.1).
- Target preserves: `agentic-skills-work` (documents_1), `agentic-skills-work-documents_2`, `agentic-skills-work-documents_3`, `intelligent_kanban` (7 BLs), **`time-tracking`** (≥13 BLs).

### Live processes (at hand-off time)
| | |
|---|---|
| uvicorn | UP (PID 47379, started ~7h ago for time-tracking sprint) |
| milvus-standalone | UP ~3 days |
| Ollama bge-m3 | UP |
| frontend vite | UP (PID 42941) on localhost:5173 |
| Time_Tracking sprint | LIVE on `run-20260530T133341Z-f97e8c` — was on BL-0014 |

### This session's commits on `architect-prereqs` (oldest → newest)

| Commit | What |
|---|---|
| `b25cf2b` | fix(A43): meta-agent verify-before-claim discipline (Layer 1) |
| `c3a8014` | fix(A44): raise StreamReader limit to 64 MiB; surface api_error events |
| `59445cb` | docs(arch): EVALUATION_2026-05-28 + ARCHITECT_PLAN Batch E + memory updates |
| `b54586b` | feat(init-feature): automate clean-baseline branch + harness install |
| `3528cad` | docs(harness): HARNESS.md + tools/ui_tour + Acceptance Agent SKILLS.md draft |

### Sprints executed this session

| Sprint | Run ID | Outcome |
|---|---|---|
| intelligent_kanban (resume) | `run-20260528T144444Z-e4ba3d` → `run-20260529T000736Z-447213` | 7/7 BLs merged_full (4 in first attempt + 3 after A44 fix saved BL-0004 from LimitOverrunError abort) |
| Time_Tracking initial | `run-20260529T133015Z-04da86` | 7/14 BLs merged + 1 aborted at BL-0007 QA (REQ-0502 dialog/aria-hidden architectural bug; QA's reinforcement tests caught a real UX defect) |
| Time_Tracking resume #1 (BL-0008+) | `run-20260529T235530Z-00754e` | 5 BLs landed clean (BL-0008..0011) + aborted at BL-0012 (engineer's biome+routeTree issues; A39 in production) |
| Time_Tracking resume #2 (BL-0013+) | `run-20260530T133341Z-f97e8c` | LIVE — see P1.1 |

### Operator hand-patches this session

| Patch | What |
|---|---|
| BL-0007 (time-tracking) | Merged QA's branch (3 commits incl. real main.tsx 403 bug fix); added refetch-wait to REQ-0502; **skipped REQ-0502 test** with documented engineering follow-up (Radix Dialog aria-hidden + ReviewTimesheet stays-open-on-error needs engineer-side change) |
| BL-0012 (time-tracking) | Merged engineer's branch; fixed biome import-sort + JSX/const formatting in `ReportChart.tsx`; verified gate-lint exit 0 |

## 3. What works end-to-end now (delta from prior handoff)

- ✅ **`/init-feature` endpoint + UI button** — operator types feature name in webapp UI, backend bootstraps clean-baseline branch + applies harness templates + creates feature dir. Replaces the manual `RUNBOOK_clean_brownfield_reset.md` procedure. 6 backend tests pass.
- ✅ **A44 StreamReader fix** — 64 MiB readline buffer; large-file Read no longer SIGTERMs the engineer subprocess. Validated on intelligent_kanban BL-0004 (previously aborted 3× with this bug).
- ✅ **A43 Layer 1 (meta-agent Evidence Discipline)** — schema-uniformity-assumption rule + worked failure example committed to meta-agent SKILLS.md. Doctrine-meta on next sprint should be tested against this.
- ✅ **HARNESS.md** — comprehensive teaching document for harness engineering as a discipline (11 sections, 5-layer model, full annotated flow, 10 principles, worked example).
- ✅ **tools/ui_tour/** — operator-side visual inspection (boots isolated docker stack, runs playwright with screenshot:on, preserves PNGs). Validated end-to-end (9/9 tests).
- ✅ **Acceptance Agent SKILLS.md (DRAFT)** — `skills/brownfield/brownfield-acceptance-agent/SKILLS.md`. Pending: orchestrator wiring, prompt builder, validator, tests.

## 4. Open ledger items (DESIGN_SHORTCOMINGS.md)

Active gaps surfaced this session:
| ID | Status | Notes |
|---|---|---|
| **A39** | open, **promoted to high priority** | regression_gate parser conflates build-failure with all-tests-regressed. **3 worked examples now**: documents_2 BL-0008, intelligent_kanban BL-0006, time-tracking BL-0012. Engineers waste retries chasing phantom test regressions. Fix in `webapp/backend/app/services/regression_gate.py`. |
| **A40** | open (incomplete) | engineer prompt says `--apply` (biome 1.x) but biome 2.x is `--write`. One-line prompt update. |
| **A4x candidate** | not yet filed | "Per-BL isolation prevents cross-component bug recovery" — worked example: BL-0007 REQ-0502. **Acceptance Agent (ABL-0010) is the proposed structural answer.** |
| **A4x candidate** | not yet filed | "Gate is regression detector, not coverage prover" — no code coverage, no visual regression, no mutation testing. |
| **ABL-0010** | proposed | Acceptance Agent — SKILLS.md drafted this session, awaiting operator decision on wiring. |

## 5. Mandatory reading order for next session

1. `CLAUDE.md` — architect role
2. `THESIS.md` — mission + done definition
3. `HARNESS.md` — **NEW** teaching doc; if you've not read it, read it first — it defines the vocabulary
4. `ARCHITECTURE_INVARIANTS.md` — the 7 invariants
5. `DESIGN_SHORTCOMINGS.md` — audit ledger; A39 needs promotion
6. `EVALUATION_2026-05-28.md` — calibrated 40% completion audit
7. `skills/brownfield/brownfield-acceptance-agent/SKILLS.md` — **NEW** draft pending operator review
8. `.claude/memory/MEMORY.md` and `arch_*.md`

## 6. Likely next moves (after P1.1-P1.4 complete)

In approximate priority order:
- **Decide ABL-0010 Acceptance Agent wiring** (P1.4) — orchestrator + prompt builder + validator + tests. ~1-2 days of build. Highest-leverage architecture work.
- **A39 fix** — regression_gate.py parser. Promote to high priority based on 3 worked examples. Should ship before the next sprint.
- **A40 fix** — one-line prompt update for biome --write.
- **File the deferred A4x candidates** in `DESIGN_SHORTCOMINGS.md` with full forensic detail.
- **Run `./tools/ui_tour/ui_tour.sh time-tracking`** after sprint close to capture the visual record of the assembled feature.
- **closure_check docker scope verification** — still latent from prior handoff.
- **Batches C + D of ARCHITECT_PLAN** — framework-reviewer + scheduled observer.

## 7. Don'ts (lessons from this session)

Carry-forward + new this session:

1. **Don't trust Edit tool to persist on target-repo files without immediate verification.** This session encountered file reverts; safer to commit immediately after editing on target.
2. **Don't assume QA can fix cross-component bugs.** BL-0007 REQ-0502 needed an engineer-side dialog-close-on-error change; QA's 3 retries couldn't resolve it. Per-BL isolation forces this asymmetry — ABL-0010 is the proposed answer.
3. **Don't ship a "feature done" claim without acceptance evidence.** This session's user critique: regression-clean ≠ functionality-tested-as-user-would. Acceptance Agent or hand-run ui_tour bridges this.
4. **Don't conflate "tests exist" with "functionality is thoroughly tested."** 102 playwright tests + 1 skip + 1 TODO ≠ proof of correctness. The gate is a regression detector.
5. **Don't let A39 noise consume R10 retry budget.** When the parser shows 100+ regressions but the real cause is `tests/gate::build FAILED`, the engineer chases phantoms. This bit BL-0012 hard.
6. (Carry-forward) Don't claim a hang is a hang without checking the next test's PASSED line.
7. (Carry-forward) Don't trust meta-agent proposal claims without spot-checking literal cited lines.
8. (Carry-forward) Don't POST to /run-brief from a finite-timeout client. Use `curl -N` or browser SSE.
9. (Carry-forward) Don't commit framework changes mid-sprint — wait for `sprint_complete`.

---PROMPT END---
