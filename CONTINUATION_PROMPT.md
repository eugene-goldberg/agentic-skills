# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-05-31 ~15:00Z. This session: **ABL-0014
> Acceptance Agent shipped, calibrated, flipped to default-ON, AND
> proven in production** — a real 2-BL sprint (`health-version`) hit
> `acceptance.done validator_ok=True` and surfaced **3 real
> `product_bug` findings** that per-BL QA had passed clean. The
> structural answer to A46 is working. Two new CLAUDE.md operating
> rules also landed (quality-over-speed + 95% verified-certainty
> floor).

---PROMPT START---

You are picking up the agentic-skills project. **You are the architect.**
Read `CLAUDE.md` first — note especially the new **"Operating
principle: quality over speed"** section (Rules 1–6, including the **95%
verified/tested certainty floor**). These rules govern every diagnosis,
recommendation, and commit you make this session.

## ⚠️ PRIORITY 1 — execute these BEFORE anything else

### P1.1 — Verify branch state (30 sec)
```bash
cd /Users/eugenegoldberg/dev/ai-projects/agentic-skills
git status -s              # MUST be clean
git log --oneline @{u}..HEAD   # MUST be empty (synced)
git log --oneline -1
```
Expected tip: `c069082` (handoff commit with A47 filed) or one further if this session added something.

### P1.2 — Review the operator's open decision: the 3 product_bug findings (5 min)
The `health-version` sprint shipped both BLs `merged_full`, but
**ABL-0014 found 3 real product bugs that per-BL QA missed**. Operator
needs to decide:

1. **Re-decompose into BL-0003** that builds `VersionPill.tsx`, mounts
   it in `frontend/src/routes/_layout.tsx`, drops `test.fixme` → re-run
   sprint via skip_po=true on the same brief
2. **Accept partial delivery** (backend endpoint alone is useful;
   document the missing pill as out-of-scope-for-now)
3. **File the missing pill as engineering-debt in a separate ticket**
   and move on to the next feature

Evidence preserved at
`webapp/backend/traces_archive/run-20260531T134012Z-dd4864/acceptance/`:
- `report.json` (rich per-journey diagnostics + product_bug classifications)
- `report.md` (human-readable)
- `journeys.yaml` (5 journeys exercised)
- `screenshots/` (10 PNGs across 4 journey dirs)

The agent's literal hypothesis (Journey 02):
> *"VersionPill.tsx was never created and is not mounted in
> `frontend/src/routes/_layout.tsx`; BL-0002 landed only its
> `test.fixme` spec."*

This is the precise mechanism A46 / BL-0007 REQ-0502 motivated. Surface
to operator with the 3 options above. Do not implement without explicit
operator direction.

### P1.3 — Review uvicorn + Docker state (30 sec)
uvicorn was restarted at PID 65773 mid-session (after ABL-0014 default
flip). It may still be running:
```bash
ps -p 65773 -o pid=,etime= 2>/dev/null || echo "uvicorn down"
docker ps --format "{{.Names}}" 2>/dev/null | head -5
```
If uvicorn died, restart from `webapp/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`.

---

## 1. Identity

**agentic-skills** — autonomous synthetic AI crew that adds complex
features to brownfield codebases with no human in the loop for the bulk
of work.

**Operator:** Eugene Goldberg.
**Repo:** `/Users/eugenegoldberg/dev/ai-projects/agentic-skills`.
**GitHub:** https://github.com/eugene-goldberg/agentic-skills (default
branch `architect-prereqs`).

## 2. State at hand-off

### Branches
- `architect-prereqs` @ `c069082` (or current handoff commit) — **in sync with origin.** 10 commits this session on top of `1fe4def`.
- Target `health-version` — fresh 2-BL feature shipped this session (both `merged_full`); ABL-0014 found 3 product_bug findings (awaiting operator triage).
- Target preserves: `agentic-skills-work` (documents_1), `agentic-skills-work-documents_2`, `agentic-skills-work-documents_3`, `intelligent_kanban` (7 BLs), `time-tracking` (14 BLs, 13 merged + aborted on BL-0014), **`health-version`** (NEW, 2 BLs both merged_full).

### Live processes (at hand-off)
| | |
|---|---|
| uvicorn | PID 65773 (restarted mid-session for default-flip load) |
| Docker daemon | restarted mid-session (was throwing HTTP 500s); now healthy |
| Milvus | up (auto-restarted by sprint's index_initial) |
| acceptance smoke processes | none active |
| curl SSE for health-version sprint | terminated cleanly at sprint_complete |

### This session's commits on `architect-prereqs` (oldest → newest)

| Commit | What |
|---|---|
| `4a5c108` | **ABL-0014 Batch A** — skill registration + acceptance_validator.py + _acceptance_flow skeleton + 14 tests |
| `f1bdb8b` | **ABL-0014 Batch B** — worktree + agent spawn + R10.1 retry + archive + closure_check ext + 11 new tests (25 total) |
| `c504e4f` | **ABL-0014 Batch C** — frontend checkbox + summary tile + 7 doc updates + ABL renumber (0010→0014, 0011→0015) |
| `f3b4a7a` | Drop retrieval-tools mention from SKILLS.md (contract gap fix) |
| `aa0e9ef` | **Smoke-1 calibration** — 5 validator gap fixes + smoke driver + /run-acceptance endpoint |
| `eb075ad` | **Smoke-2 calibration** — accept `status` as outcome synonym |
| `8499dd3` | **Default flipped `run_acceptance=True`** — ABL-0014 OPERATIONAL |
| `c343d87` | docs(CLAUDE.md): "Operating principle: quality over speed" — Rules 1-5 |
| `72e95d1` | docs(CLAUDE.md): Rule 6 — 95% verified/tested certainty floor |
| `514f181` | ledger(A39+A45) — 39b empty-extraction sub-mode + A45 idle-timeout |
| `fef3284` | ledger(A46) — per-BL isolation gap (RESOLVED by ABL-0014) |
| `c069082` | docs(handoff): A47 — ScheduleWakeup/Glob bypass --allowedTools |

### Sprints executed this session

| Sprint | Run ID | Outcome |
|---|---|---|
| smoke-1 (time-tracking) | `smoke-20260530T161537Z` | validator_ok=False (5 calibration gaps surfaced + fixed); 7 journeys, 5 passed |
| smoke-2 (time-tracking) | `smoke-20260531T022625Z` | validator_ok=True attempts=2 (1 gap fixed); 8 journeys, 5 passed, **2 product_bug + 1 test_bug** on time-tracking |
| smoke-3 (time-tracking) | `smoke-20260531T034747Z` | validator_ok=True attempts=1, ZERO new gaps; 7/7 passed (calibration complete) |
| **health-version (REAL)** | `run-20260531T134012Z-dd4864` | sprint_complete; both BLs merged_full; **acceptance found 3 product_bug findings**; closure 0/0 leaks |

## 3. What works end-to-end now (delta from prior handoff)

- ✅ **ABL-0014 Acceptance Agent OPERATIONAL by default.** `run_acceptance=True` on every new sprint unless explicitly opted out. Plumbed through RunBriefRequest, run_brief, AppV2 UI checkbox.
- ✅ **3-smoke calibration gate PASSED** — 6 calibration gaps surfaced across smokes #1-#2 and all fixed; smoke #3 ran clean on attempt 1.
- ✅ **Real-sprint proof point** — health-version sprint surfaced 3 product_bugs (missing VersionPill.tsx, missing click-copy, broken cross-actor e2e) that per-BL QA structurally couldn't catch. **A46 closed in practice.**
- ✅ **/run-acceptance standalone endpoint** — `POST /api/projects/{repo}/run-acceptance` with `RunAcceptanceRequest{run_id, feature_slug, acceptance_timeout}`. Mirrors /run-doctrine-meta pattern.
- ✅ **tools/run_acceptance_smoke.py** — direct `_acceptance_flow` invocation for calibration smokes without restarting uvicorn.
- ✅ **CLAUDE.md "quality over speed" doctrine** — 6 rules including 95% verified-certainty floor. Inherited by every future session.
- ✅ **closure_check D9 extension** — `scan_orphan_acceptance_containers` + `scan_stale_acceptance_worktrees`; honored cleanly in health-version sprint (0 leaks).

## 4. Open ledger items

| ID | Status | Notes |
|---|---|---|
| **A39** | open, HIGH, **5 worked examples** | regression_gate parser conflates build failure with test regressions. **5th example** surfaced this session: health-version BL-0001 retry-1 reported "61 regressions" when real issue was transient stack_healthy. Engineer self-recovered on retry 2. **Promote to immediate-fix.** Fix in `webapp/backend/app/services/regression_gate.py`. |
| **A45** | open, HIGH | B5 idle-timeout false-positive kills agents on silent waits. Filed this session (`514f181`). Causally coupled to A39. |
| **A46** | **RESOLVED** by ABL-0014 (`fef3284`) | per-BL isolation gap; closed in practice by health-version sprint's 3 product_bug findings |
| **A47** | open, LOW | `ScheduleWakeup` + `Glob` bypass `--allowedTools` restriction. 4 worked examples across all acceptance runs. Filed this session (`c069082`). Benign today; contract-honesty gap. |
| **A40** | open | engineer prompt `--apply` (biome 1.x) vs `--write` (biome 2.x). Recurs in builds. |
| **ABL-0015** | proposed/blocked | Auto-dispatch follow-up engineer on `product_bug` acceptance findings. Now that ABL-0014 demonstrably finds real product bugs (3 in health-version), this is the natural next step. |

## 5. Mandatory reading order for next session

1. `CLAUDE.md` — architect role + **NEW** "Operating principle: quality over speed" (Rules 1-6)
2. `THESIS.md` — mission + done definition
3. `ARCHITECTURE_INVARIANTS.md` — the 7 invariants
4. `HARNESS.md` — 5-layer model + flow diagram (includes ABL-0014 acceptance pass at §5.6.2)
5. `ABL-0014_ACCEPTANCE_AGENT_IMPLEMENTATION.md` — locked operator decisions in §E.1
6. `DESIGN_SHORTCOMINGS.md` — A39 (promote to immediate-fix), A45, A46 (resolved), A47
7. `.claude/memory/MEMORY.md` and `arch_acceptance_agent.md` (OPERATIONAL)

## 6. Likely next moves (after P1.1-P1.3 complete)

In approximate priority order:
- **Operator triage on the 3 product_bug findings** — see P1.2. Lowest cost, highest learning value.
- **A39 immediate fix** (5 worked examples) — `webapp/backend/app/services/regression_gate.py`. ~1 hr. Saves a retry cycle per sprint going forward.
- **ABL-0015 design** — auto-dispatch follow-up engineer on `product_bug` acceptance findings. Natural progression now that ABL-0014 has proven it can find real bugs.
- **Run a 2nd real sprint with run_acceptance=True** to keep building production evidence. Suggested target: a slightly larger feature (3-5 BLs).
- Batches C + D of `ARCHITECT_PLAN.md` (framework-reviewer + scheduled observer) — still pending from earlier sessions.

## 7. Don'ts (lessons from THIS session)

Carry-forward + new:

1. **(NEW, hard lesson)** **Never claim "FOUND IT" before running the falsification check.** I announced "FOUND THE BUG" twice this session based on:
   - (a) a `docker exec` output from the PRE-gate container (which by design carries baseline `target_ref` code, not the agent's branch) — the "missing health import" proved nothing
   - (b) the claim that A45 was already in DESIGN_SHORTCOMINGS.md (it wasn't; my Batch C commit's `git add` had missed the file)
   Both were violations of A43 Evidence Discipline applied to the architect role. The 95% certainty rule in CLAUDE.md (commit `72e95d1`) was added in direct response.
2. **(NEW)** **Don't `git commit` while assuming the file was staged.** Verify the file is in `git diff --stat HEAD~` BEFORE writing a commit message that claims it. My c504e4f commit message claimed to add A45 (per-BL isolation) to DESIGN_SHORTCOMINGS, but the actual diff didn't include the file. Caught and corrected as A46 in `fef3284`.
3. **(NEW)** **Don't POST to `/run-brief` from a finite-timeout client.** I burned 20 min of a sprint this session on exactly this — `urllib.request.urlopen(timeout=30)` closed the SSE stream, the orchestrator's StreamingResponse cancelled, the sprint died silently at `index_initial.start`. Use `curl -N`, the AppV2 UI, or a streaming-friendly client.
4. (Carry-forward) Don't trust Edit tool to persist on target-repo files without immediate verification.
5. (Carry-forward) Don't assume QA can fix cross-component bugs — that's what acceptance was built for.
6. (Carry-forward) Don't ship a "feature done" claim without acceptance evidence.
7. (Carry-forward) Don't conflate "tests exist" with "functionality is thoroughly tested."
8. (Carry-forward) Don't let A39 noise consume R10 retry budget.

---PROMPT END---
