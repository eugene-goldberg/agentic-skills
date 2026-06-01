# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-06-01 ~10:00Z. This session shipped **Items 1+2
> (API-acceptance + UI-coverage check) + A48 #1–#3 + §I production-ready
> roadmap** across 8 commits. The acceptance agent is now "fully
> functional for sprints with arbitrary UI/backend mix" — but **§I
> tracks 5 TIER-A items required to claim 95% production-readiness.**

---PROMPT START---

You are picking up the agentic-skills project. **You are the architect.**
Read `CLAUDE.md` first — note especially the **"Operating principle:
quality over speed"** section (Rules 1–6, including the **95%
verified/tested certainty floor**). These rules govern every diagnosis,
recommendation, and commit you make this session.

## ⚠️ TOP PRIORITY THIS SESSION

**Execute the §I production-ready roadmap for the acceptance agent.**

Read this section **in full** before doing anything else:

```
ABL-0014_ACCEPTANCE_AGENT_IMPLEMENTATION.md §I
```

That section is the canonical, calibrated record of what remains to
make the acceptance agent legitimately production-ready under
CLAUDE.md Rule 6. Headline: **current confidence ~70%, below 95%
floor.** Reaching 95% requires landing all 5 TIER-A items. §I has
the cost estimates, owners, risks, named rollbacks, and the **hard
sequencing constraint** (I.4 cannot land before I.3 because
ABL-0015 auto-dispatch needs the verdict ledger).

### Recommended execution sequence (per §I.6)

```
1. I.2  Acceptance trace observability gaps           (~2 days)
2. I.3  Findings feedback ledger + AppV2 triage UI    (~3 days; GATES I.4)
3. I.5  Multi-target validation (Django smoke)        (~1 day)
4. I.1  Two more API-acceptance calibration smokes    (~1–2 days)
5. I.4  ABL-0015 auto-dispatch                        (~3–4 days)
```

**Start with I.2 (observability) or I.3 (findings ledger) depending
on operator's preference.** §I.0 explicitly flags I.3 as the
single non-negotiable item — without it, classifier accuracy is
structurally unbounded and confidence plateaus at ~85% regardless
of other work.

### Before writing any §I code

Per CLAUDE.md "Calibrated proposals" discipline:
1. Read §I in full (576-line file; §I starts at line 343)
2. Propose batch breakdown to operator before code (same pattern as
   Items 1+2 used Batches A/B/C/D)
3. Each batch ships with: named risk, named verification test,
   named rollback
4. Operator approves batch by batch — do not bundle

---

## ⚠️ Priority 1.5 — Verify branch state (30 sec)

```bash
cd /Users/eugenegoldberg/dev/ai-projects/agentic-skills
git status -s                  # MUST be clean
git log --oneline @{u}..HEAD   # MUST be empty (synced with origin)
git log --oneline -1
```

Expected tip: `181edd8` (§I addition). If this session added work,
the tip may be one or more commits further.

---

## 1. Identity

**agentic-skills** — autonomous synthetic AI crew that adds complex
features to brownfield codebases with no human in the loop for the
bulk of work.

- **Operator:** Eugene Goldberg
- **Repo:** `/Users/eugenegoldberg/dev/ai-projects/agentic-skills`
- **GitHub:** https://github.com/eugene-goldberg/agentic-skills
- **Active branch:** `architect-prereqs` (in sync with origin)

## 2. State at hand-off

### Branch

`architect-prereqs` @ `181edd8` — synced to origin. 8 commits this
session on top of `36fa328`.

### Commits this session (oldest → newest)

| Commit | What |
|---|---|
| `2282c69` | **Item 1 Batch A** — API-acceptance validator + SKILLS.md (dormant, backward-compat) |
| `3cc52ca` | **Item 1 Batch B** — orchestrator computes `backend_bls`, threads through prompt + validator |
| `25a8d33` | **Item 2 Batch C** — UI-coverage check at `sprint_complete` |
| `5716f1c` | **Items 1+2 Batch D** — AppV2 surface + HARNESS.md + memory + plan doc §G/§H |
| `40840b6` | **A48 fix #1** — pre-flight disk-free check at `/run-brief` |
| `f527c93` | **A48 fix #2** — per-BL + acceptance anonymous-volume reaper |
| `8b23409` | **A48 fix #3** — DiskFull-aware regression-gate classifier |
| `181edd8` | **§I production-ready roadmap** — added to ABL-0014 plan doc |

### Test posture

```
127/127 backend pass (was 64 pre-session)
  +29  acceptance_validator + compute_backend_bls + compute_ui_coverage
  +10  disk_preflight
  +13  volume_reaper
  +10  disk_full_classifier
```

Frontend rebuilt cleanly (`npm run build` 494ms, 0 errors). UI ships
the Coverage tile + acceptance tile's backend_bls line + the
`min_ui_coverage_ratio` input.

### Live processes (at hand-off)

| | |
|---|---|
| uvicorn | PID 30286 (restarted mid-session for Batch B load) |
| Docker daemon | up; healthy |
| Milvus | up (auto-restarted) |
| Batch B proof-point | **COMPLETED CLEAN** — `accept-rerun-batch-b-20260601T134813Z` validated all 9 backend BLs with 12 api_journeys, validator_ok=true attempts=1 |

### Sprints / smokes executed this session

| Run | Outcome |
|---|---|
| `accept-rerun-batch-b-20260601T134813Z` | **CLEAN** — UI: 5/5 passed; API: 12/12 passed; 100% backend BL coverage |

That run is **smoke #1 of 3** for the API-acceptance calibration
discipline (see §I.1). Two more clean runs against different sprint
shapes required before flipping any default.

## 3. What works end-to-end now

- ✅ **Item 1 (API-acceptance) LIVE** — every merged backend BL exercised
  via authenticated api_journeys; validator enforces coverage; R10.1
  retry on gaps. Proven on Client_Portal sprint shape.
- ✅ **Item 2 (UI-coverage) LIVE** — `orchestrator.coverage_check` event
  + `sprint_complete.coverage_subtype`; operator-tunable threshold
  (default 0.0 = informational).
- ✅ **A48 disk-creep defense LIVE at 3 layers** — submission-time
  pre-flight (#1), per-BL anonymous-volume reaper (#2), DiskFull-
  aware classifier (#3). Fix #4 (tmpfs override) deferred.
- ✅ **All Item 1+2 docs canonical** — HARNESS.md §5.6.2.{1,2},
  ABL-0014 plan doc §G+§H+§I, arch_acceptance_agent.md, AppV2 UI.

## 4. The §I roadmap — top priority

**Read `ABL-0014_ACCEPTANCE_AGENT_IMPLEMENTATION.md §I`** for the
authoritative version. Brief summary follows; **do not rely on this
summary for execution detail — read §I**:

### TIER A — blocks ≥95% production-ready (all 5 required)

| ID | Item | Cost | Notes |
|----|------|------|-------|
| I.1 | 2 more API-acceptance calibration smokes (n=1 → n=3) | ~1–2 days | Same discipline that gated 2026-05-31 UI flip |
| I.2 | Acceptance trace observability gaps (retrieval.jsonl, phase_events.jsonl, tool_use in stream.jsonl) | ~2 days | Read-only additions; system-diagnosability blocker |
| I.3 | Findings feedback ledger + AppV2 triage UI | ~3 days | **Non-negotiable.** Gates I.4. Without it, classifier accuracy unbounded |
| I.4 | ABL-0015 auto-dispatch on `product_bug` findings | ~3–4 days | **Hard prereq: I.3 must exist.** Closes find→fix loop |
| I.5 | Multi-target validation (Django smoke) | ~1 day | Repo-configurable globs untested on non-FastAPI |

### TIER B / C / Unknowns

§I.7–§I.9 catalog 4 high-confidence improvements, 7 medium-confidence
deferrals, and 4 explicit unknowns the architect cannot estimate. Do
not rediscover these — read them.

### A48 cross-references (§I.10)

A48 fixes #1+#2+#3 substantially close the disk-creep failure mode
that threatens acceptance runs. Fix #4 deferred and likely
unnecessary.

## 5. Open ledger items

| ID | Status | Pri |
|----|--------|-----|
| **A39** | open, **5 worked examples** | HIGH — regression_gate parser conflates build failure with regressions. CONTINUATION_PROMPT prior session flagged "promote to immediate-fix." |
| **A45** | open | HIGH — B5 idle-timeout false-positive kills agents on long sync waits. Causally coupled to A39. **Risk to acceptance** — see §I.7.b. |
| **A46** | RESOLVED by ABL-0014 (extended end-to-end this session) | — |
| **A47** | open | LOW — ScheduleWakeup/Glob bypass `--allowedTools` |
| **A48** | **#1+#2+#3 of 4 SHIPPED** this session; #4 deferred | — |
| **A40** | open | engineer prompt biome `--apply` vs `--write` |
| **ABL-0015** | proposed / blocked on I.3 | HIGH — see §I.4 |

## 6. Mandatory reading order for next session

1. `CLAUDE.md` — architect role + "Operating principle: quality over speed" (Rules 1–6)
2. `THESIS.md` — mission + done definition
3. `ARCHITECTURE_INVARIANTS.md` — the 7 invariants
4. **`ABL-0014_ACCEPTANCE_AGENT_IMPLEMENTATION.md` §I** — the production-ready roadmap (top priority)
5. `HARNESS.md` §5.6.2 + §5.6.2.1 + §5.6.2.2 — current acceptance contract
6. `DESIGN_SHORTCOMINGS.md` — A39 (promote), A45 (acceptance risk), A47, A48 (#1–#3 shipped, #4 deferred)
7. `.claude/memory/MEMORY.md` + `arch_acceptance_agent.md` (comprehensive Item 1+2 history)

## 7. Likely next moves

In approximate priority order **per §I.6 sequence**:

- **Start §I.2 or §I.3** — operator's call. §I.3 is the non-negotiable
  one; §I.2 is the prerequisite for diagnosing §I.3 calibration drift.
- **Don't start §I.4 (ABL-0015) until §I.3 ships** — see §I.4's
  "Hard prereq" note.
- **§I.5 (Django smoke)** is parallelizable with §I.2/§I.3.
- **§I.1 (2 more smokes)** requires sprint runs; can be triggered
  any time after §I.2 lands.

## 8. Don'ts (lessons from prior sessions)

1. **Never claim "FOUND IT" before running the falsification check.**
   95% verified/tested certainty floor (CLAUDE.md Rule 6) is a hard
   floor, not a target.
2. **Don't `git commit` while assuming a file was staged.** Verify
   via `git diff --stat HEAD~`.
3. **Don't POST to `/run-brief` from a finite-timeout client.** Use
   `curl -N`, AppV2 UI, or a streaming-friendly client. (Prior
   session burned 20 min on `urllib timeout=30` closing the SSE
   stream.)
4. **Don't assume QA can fix cross-component bugs** — that's what
   acceptance is for; that's why Items 1+2 exist.
5. **Don't ship a "feature done" claim without acceptance evidence.**
6. **Don't conflate "tests exist" with "functionality thoroughly
   tested"** — see §I.3 for why classifier accuracy needs a verdict
   ledger.
7. **Don't bundle Batch C of any new ABL with Batch B** — per
   ABL-0014 history, each batch should land with its own rollback
   so calibration gaps surface against a small surface.
8. **Don't auto-flip new default flags without 3 clean smokes**
   (the discipline that gated the 2026-05-31 UI flip; §I.1 applies
   the same standard to the API-acceptance default).

## 9. Where the proof-point evidence lives

The Batch B proof-point (smoke #1 of 3 for API-acceptance) artifacts:

```
webapp/backend/traces_archive/accept-rerun-batch-b-20260601T134813Z/acceptance/
  report.md
  report.json
  journeys.yaml
  api_journeys.yaml          ← all 9 backend BLs covered (12 journeys)
  fixtures/seed_log.txt
  fixtures/api_logs/          ← per-journey req/resp logs
  screenshots/                ← UI journey evidence
  tests/
```

When operator wants to verify the contract works as documented,
this is the canonical example.

---PROMPT END---
