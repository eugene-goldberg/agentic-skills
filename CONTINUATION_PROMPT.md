# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-06-03. This session implemented **ABL-0016
> Lessons-as-context** (cumulative learning, Stage 1) — code batches A–C —
> on a new branch `cumulative_learning`, on top of the ABL-0015
> auto-dispatch work that lives on `architect-prereqs`.
>
> **Two flag-OFF features now await an operator-gated calibration smoke:**
> ABL-0015 auto-dispatch (Batch E) and ABL-0016 lessons-as-context. The
> architect cannot run either.

---PROMPT START---

You are picking up the agentic-skills project. **You are the architect.**
Read `CLAUDE.md` first — especially **"Operating principle: quality over
speed"** (Rules 1–6, the **95% verified/tested certainty floor**, Rule 3
on **narrative momentum**).

## ⚠️ Priority 0 — Verify branch state (30 sec)

```bash
cd /Users/eugenegoldberg/dev/ai-projects/agentic-skills
git branch --show-current        # likely cumulative_learning
git status -s                    # MUST be clean
git log --oneline @{u}..HEAD     # MUST be empty (synced)
```

Two active feature branches:
- `architect-prereqs` — ABL-0015 auto-dispatch (A–D shipped, flag-OFF).
- `cumulative_learning` — branched off the above; adds ABL-0016 (A–C
  shipped, flag-OFF). **Current branch.**

## 1. Identity

**agentic-skills** — autonomous synthetic AI crew for brownfield feature
delivery. Operator: Eugene Goldberg. The main project is the *crew itself*;
brownfield targets and their `_brownfield/` derivatives are never committed
to this repo. We only commit/push/maintain agentic-skills.

## 2. State at hand-off

### ABL-0016 Lessons-as-context — cumulative learning Stage 1 (this session)

The mission's **cumulative** property ("what's learned on one target
carries forward") was its least-mature axis. ABL-0016 closes the
**read-path gap**: prior operator-confirmed findings now surface to every
brownfield role (PO/engineer/QA/scorer) as *advisory* context.

Code batches A–C, all on `cumulative_learning` (233/233 backend tests):

| Commit | What |
|---|---|
| `f259439` | cumulative-learning strategy roadmap |
| `e600044` | ABL-0016 Stage-1 plan |
| `29b9503` | whole-feature program plan (ABL-0016→0019) |
| `eb20d6f` | A — `lessons.py` reader (`list_lessons`, target-scoped union) + renderer (`render_lessons_block`, silent-empty) |
| `294f725` | B — `inject_lessons` flag through request→run_brief→3 flows; block wired into 4 brownfield builders at verified seams |
| `512a1c5` | C — `record_injection` provenance (`logs/lessons/<run_id>.jsonl`); Stage-2 hook |

Design: **Option A** (prompt injection, mirrors `_build_priors_block`),
**target-scoped** (union across `_brownfield/features/*/acceptance/findings_log.jsonl`),
advisory (falsification priors, not bans), **no new R-rule** (I-2
unaffected). Docs: `ABL-0016_LESSONS_AS_CONTEXT.md`,
`CUMULATIVE_LEARNING_IMPLEMENTATION_PLAN.md`, `CUMULATIVE_LEARNING_ROADMAP.md`.

### ABL-0015 auto-dispatch (on `architect-prereqs`, flag-OFF)

A–D shipped: ledger dispatch schema, `run_acceptance_followup` flag,
selector + dispatch block (R15 dispatch-at-most-once), closure coverage.
Reuses `_engineer_flow` unchanged (selector + invoker). See
`ABL-0015_AUTO_DISPATCH_DESIGN.md` + `arch_auto_dispatch.md` memory.

### Test posture

```
233/233 backend pass. Run scoped:
  cd webapp/backend && python3 -m pytest tests/ -q -p no:cacheprovider
```
Bare `pytest` from `backend/` recurses into the gitignored target repos
under `repos/` and errors on `sqlmodel` — invocation artifact, not a
failure.

## 3. The two open operator-gated smokes (architect cannot run these)

1. **ABL-0016 lessons calibration:** run one sprint with
   `inject_lessons=true` on a target carrying prior **confirmed** findings;
   confirm the "## Relevant prior lessons (advisory)" block renders into
   the role prompts, `logs/lessons/<run_id>.jsonl` is written, and no
   regression. Clean → architect proposes flipping the flag default.
2. **ABL-0015 auto-dispatch (Batch E):** operator-verdict the Journey 03
   `product_bug` (`sha256:6e533e84…`) `confirmed`, run one sprint with
   `run_acceptance_followup=true`, observe one clean follow-up dispatch +
   0 `followup_worktree` closure violations.

## 4. Highest-leverage next architect-doable work

**ABL-0017 — Stage 2: closed-loop doctrine efficacy** (the next stage of
the cumulative-learning program). It *closes* I-7: today doctrine-meta
proposes rules open-loop; Stage 2 measures whether an enforced rule
actually reduced its targeted failure class, and proposes retirement for
ones that don't help (operator-gated, never auto-retires). It consumes the
ABL-0016 provenance log + per-BL outcomes.

**Start with its Batch-0 verification gate** (per
`CUMULATIVE_LEARNING_IMPLEMENTATION_PLAN.md` §4): confirm the
outcome-persistence seam (`run_brief` summary / `.orchestrator-state/<run_id>.json`
/ terminal events), the doctrine-meta input/output contract, and how
enforced rules are recorded per run. No Stage-2 code before Batch 0 closes
those 🔎 items — the discipline that converted ABL-0016 from sketch to a
verified plan.

(Alternatively ABL-0019 Stage 4 pattern profile — lower risk; or ABL-0018
Stage 3 cross-target transfer — higher value, pairs with the §I.5 Django
multi-target smoke.)

## 5. Other open items

| ID | Status |
|---|---|
| ABL-0016 calibration smoke | open (operator) |
| ABL-0015 Batch E smoke | open (operator) |
| A39 | gate parser conflates baseline-broken vs engineer-regressed |
| A45 | B5 idle-timeout false-positive |
| A47 | ScheduleWakeup/Glob bypass `--allowedTools` |
| A48 | closeable pending operator review |
| doctrine-meta proposal | characterization-test ownership contradiction (R-CHAR proposed) |

## 6. Mandatory reading order

1. `CLAUDE.md` — architect role + "Operating principle"
2. `THESIS.md`, `ARCHITECTURE_INVARIANTS.md`
3. `CUMULATIVE_LEARNING_IMPLEMENTATION_PLAN.md` — the program you'd continue
4. `ABL-0016_LESSONS_AS_CONTEXT.md`, `ABL-0015_AUTO_DISPATCH_DESIGN.md`
5. This file's §3 (open smokes) + §4 (next work)

## 7. Don'ts (carried lessons)

1. Don't commit brownfield targets or their `_brownfield/` derivatives —
   only the main agentic-skills repo.
2. Don't run `docker … prune -af` without naming what to keep (wiped
   Milvus + a ledger once).
3. Don't auto-skip pre-flight (`PREFLIGHT.md`) after a clean cleanup.
4. Don't lose narrative-momentum awareness — read post_tail + gate fields
   carefully even when the pattern looks like prior runs.
5. Don't force-kill uvicorn mid-sprint — Ctrl+C (SIGTERM) so the shutdown
   handler reaps Docker stacks; worktrees only reap from `finally`.
6. No later cumulative-learning stage starts before its Batch-0 closes.

---PROMPT END---
