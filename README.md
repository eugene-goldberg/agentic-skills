# agentic-skills

> Building a completely AI-based multi-agent software-development team that can
> autonomously add significant, complex features to existing brownfield codebases —
> with no human in the loop for the bulk of the work.

This README is the single-document entry point for outside reviewers. It
synthesizes the project's vision, current state, architecture, and open
work into one linear narrative. For depth, follow the pointers to the
governance documents listed throughout.

---

## 1. The vision

An organization should be able to:

1. Point this team at a real brownfield git repo (legacy code, technical
   debt, existing conventions, real users).
2. Hand it a product-level requirement (*"add multi-tenant collaboration"*,
   *"add billing"*, *"add SSO"*).
3. Walk away.
4. Come back to a series of clean, regression-tested,
   grounded-in-context commits that ship the feature — plus an honest
   report of what was deferred, what's risky, and what genuinely needs a
   human eye.

The team must be:

- **Grounded** — every change justified by retrieval evidence from the
  actual target codebase, not model intuition.
- **Self-correcting** — an agent (not a person) decides whether to retry,
  rewrite, defer, or escalate when a gate or doctrine check fails.
- **Honest** — when something is outside scope or risky, the team flags it
  explicitly rather than producing slop.
- **Cumulative** — what's learned on one target carries forward.

Canonical statement: [`THESIS.md`](THESIS.md).

---

## 2. Why this and not the other AI-coding tools

| Tool / approach | What it does | What it doesn't |
|---|---|---|
| Cursor / Aider / Cline / Copilot Chat | Human-in-the-loop pair programming | No autonomous gating, human runs tests |
| GitHub Copilot Workspace | Generates plan + PR; defers to existing CI | No multi-role crew, no doctrine enforcement |
| Devin (Cognition) | Own VM, autonomous; uses repo's CI | Closed system, opaque enforcement |
| SWE-agent (Princeton, OSS) | Benchmark-focused (SWE-bench) | Doesn't deal with real e2e suites |
| Sweep AI / similar PR bots | Issue → PR, defers to repo CI | Single-agent, no role separation |
| **agentic-skills** | Multi-role crew (PO/Engineer/QA/Scorer) with retrieval grounding, doctrine-enforced quality gates, regression-gated auto-merge, and a self-hardening loop | Slow per-BL gate cycle (see §8 throughput) |

agentic-skills sits at the most conservative end of the autonomy
spectrum: full e2e regression gate per BL, hard doctrine validation, no
auto-application of changes the operator hasn't approved. The trade-off
is throughput for trust — appropriate when the human is genuinely out
of the loop.

---

## 3. Definition of done

The thesis ships when an operator can run:

```
$ agentic-skills onboard ~/dev/brownfield-target
$ agentic-skills feature "Add usage-based billing with Stripe; admin dashboard for revenue + churn"
$ agentic-skills run
```

…walk away, and return to:

- A series of fast-forward merge commits on the target's agent branch,
  each with a green regression gate.
- A short summary of what shipped, what was deferred (with reasons), open
  questions.
- Scorecards per BL.
- Zero new R-rules written by a human during the run — the doctrine-meta
  agent owns rule evolution.

Detailed acceptance criteria in [`THESIS.md` §3](THESIS.md#3-definition-of-autonomous-team).

---

## 4. What's true today (the ~50% slice)

Sprint 1 (Team Collaboration on `full-stack-fastapi-template`, 12 merged
BLs + 1 no-op, mean score ~92/100) and subsequent api-keys + RBAC
sprints proved a real but partial slice:

| Capability | State | Evidence |
|---|---|---|
| Worker roles execute autonomously (PO → Engineer → QA → Scorer) | ✅ | 11 BLs delivered end-to-end on Sprint 1; api-keys = 5 merged_full + 1 no_op; RBAC = 11/11 R5b first-try pass |
| Quality-gated handoff between roles | ✅ | Doctrine validator + regression gate + ff merge |
| Grounded edits | ✅ | MCP retrieval + R5 (≥3 grounded calls) + Tier 1.5 pre-modification kill + R5b citation requirement |
| Self-correction on real failures | ✅ | R10.1 doctrine retry + R10.2 gate retry saved several BLs without operator action |
| No-op recognition | ✅ | R11 catches BLs already shipped upstream |
| Forbidden git ops blocked | ✅ | R13 streaming kill of `--amend`, `rebase`, `reset --hard`, `push --force` (0 violations across last 11-BL sprint) |
| Doctrine self-hardening | ✅ | Doctrine-meta-agent (Batch B / ABL-0003) proposes R-rule changes post-sprint; two operator-approved proposals (R13 + R5b) landed |
| Per-feature artifact isolation | ✅ | A18 + A19 + A20 — each feature gets `_brownfield/features/<slug>/` with `brief.md`, BACKLOG.md (BL-0001+), per-BL contexts, tailable `events.jsonl` |
| Sprint planning from product intent | ⚠ | PO decomposition works; product-level → multi-sprint roadmap still pending |
| Inter-BL orchestration | ✅ | Orchestrator (ABL-0001) runs the 8-step pipeline per BL with retries, archival, telemetry |
| Escalation triage | ❌ | `awaiting_review` still puts a branch in front of a human (ABL-0002, deferred) |
| Cross-project / cross-sprint memory | ❌ | Each target starts fresh; no shared institutional knowledge yet |
| Concurrent BL execution | ❌ | One BL at a time (ABL-0011, deferred) |
| Cost / telemetry / observability | ⚠ | SSE + trace dir per run + closure_check; no aggregation, no $ tracking |

Roughly **50% of the full thesis is operational.** Detail in
[`THESIS.md` §2](THESIS.md#2-whats-true-today-the-40-slice).

---

## 5. Architecture in one page

### 5.1 The pipeline (8 steps per BL)

```
brief → PO decomposition → graphify+claude-context indexing
                                            ↓
        per-BL loop:
            engineer (worktree-isolated, MCP retrieval-grounded)
                ↓
            doctrine_check (R5/R5b/R9/R11/R13 enforcement)
                ↓ (retry up to R10.1 on incomplete)
            regression_gate (full e2e PRE+POST in disposable worktrees)
                ↓ (retry up to R10.2 on regressed)
            merge_to_target (fast-forward; A1 auto-rebase on non-FF)
                ↓
            reindex
                ↓
            qa (doctrine-checked artifact)
                ↓
            scorer (Production-Grade Brownfield Scorecard)
        end loop
                ↓
        closure_check (I-3 postconditions: empty worktrees, no orphan containers)
                ↓
        doctrine_meta_agent (self-hardening — proposes R-rule changes)
```

Full ASCII map with every guard, gate, retry, and event:
[`WORKFLOW.md`](WORKFLOW.md). Step-to-code mapping:
[`PIPELINE.md`](PIPELINE.md).

### 5.2 The roles (per-sprint cast)

| Role | Doctrine source | Output |
|---|---|---|
| **Product Owner** | `skills/brownfield/.../po/SKILLS.md` | `_brownfield/features/<slug>/{BACKLOG.md, CODEBASE_CONTEXT.md, SPRINT_PLAN_C1.md, BL-XXXX/codebase_context.md}` |
| **Engineer** | `skills/brownfield/.../engineer/SKILLS.md` | Source code commit + `BL-XXXX/eng_patterns.md` |
| **QA** | `skills/brownfield/.../qa/SKILLS.md` | `BL-XXXX/qa_impact.md` + `.agile-v/qa/BL-XXXX.md` |
| **Scorer** | `rubrics/production_grade_scorecard_brownfield.md` | `.agile-v/scores/BL-XXXX.md` |
| **Doctrine-Meta** | `skills/brownfield/.../doctrine-meta/SKILLS.md` | `.planning/doctrine_proposals/<run_id>.md` (operator-approval gated; never auto-applies) |

### 5.3 The seven invariants

Every component is audited against these structural rules
([`ARCHITECTURE_INVARIANTS.md`](ARCHITECTURE_INVARIANTS.md)):

| ID | Invariant |
|---|---|
| **I-1** | **Subprocess lifecycle** — every spawn registers cleanup on every exit path |
| **I-2** | **Doctrine contract** — every R-rule maps to exactly one enforcement point + one test |
| **I-3** | **Closure postconditions** — at termination, the world matches cleanup's intent (no orphan worktrees, containers, branches) |
| **I-4** | **Run identity** — one `run_id`, minted once in the router, threaded through every artifact and event |
| **I-5** | **Truthful aggregation** — composite signals never report success when component signals failed |
| **I-6** | **Failure taxonomy** — 10 classes; >3 instances of any class triggers invariant review, not per-site patches |
| **I-7** | **Self-hardening** — doctrine-meta-agent proposes; operator approves; never auto-merges |

The audit ledger ([`DESIGN_SHORTCOMINGS.md`](DESIGN_SHORTCOMINGS.md))
classifies every observed defect against these invariants and tracks the
fix lineage by commit SHA.

### 5.4 The retrieval layer

Two MCP servers expose codebase intelligence to every agent:

- **claude-context** (Milvus + bge-m3 via local Ollama) — semantic +
  keyword search over the target repo
- **graphify** (AST + call graph) — `target_status`, `semantic_search`,
  `graph_neighbors`, `graph_find_similar`, `graph_summary`

Doctrine enforces **at least 3 grounded retrieval calls before any
Write/Edit** (Tier 1.5 streaming kill). Citations are required in QA and
PO artifacts (R5b) and validated post-hoc.

### 5.5 Repository layout (two subprojects)

```
agentic-skills/
├── webapp/                   ← FastAPI + React; current production frontend
│   ├── backend/              ← orchestrator, validators, gate, retrieval bridges
│   └── frontend/             ← AppV2.jsx — operator submits brief here
├── langgraph_engine/         ← original LangGraph harness; basis of A/B model comparison runs
├── skills/                   ← role doctrine (SKILLS.md per role × per family)
├── rubrics/                  ← scoring rubric (greenfield + brownfield variants)
├── reference-repos/          ← fastapi-good-patterns/ — secondary retrieval source
└── target-repos/             ← lg-graph-test/ — historical greenfield target
```

Brownfield targets live **outside** this repo (per convention at
`~/dev/ai-projects/brownfield-targets/<repo>/`) and are exposed to the
webapp via symlink under `webapp/backend/repos/<repo>`.

Each target carries `.agentic-skills.json` with `agent_branch`,
`main_ref`, `test_cmd`, and `doctrine` family.

Deeper webapp reference:
[`webapp/PROJECT_STATE.md`](webapp/PROJECT_STATE.md).

---

## 6. Branches and lineage

```
main                       ← initial harness snapshot
  └─ skills_with_graphs    ← Phase 0-4 retrieval layer + A/B comparison
       └─ webapp           ← FastAPI + React, greenfield doctrine
            └─ brownfield-production
                 └─ sprint-2-orchestrator   ← ABL-0001 + 18-item hardening
                      └─ architect-prereqs  ← CURRENT FRONTIER (default)
```

The GitHub repo's default branch is `architect-prereqs` because that's
where the current work lives. All branches are present on the remote.

---

## 7. Sprint scoreboard (real production runs)

| Sprint | Target | Brief | Outcome |
|---|---|---|---|
| Sprint 1 — Team Collaboration | `full-stack-fastapi-template` | Team / workspace membership | **11 merged_full + 1 no_op**, mean score ~92/100 |
| Sprint 2 — Notifications & Activity | `full-stack-fastapi-template` | Notifications system | Mid-flight abort (Sprint 3 BL-0005 root cause → ledger A1, A5, A6 etc.) |
| **Sprint 3 — api-keys** | `full-stack-fastapi-template` | API key management | **5 merged_full + 1 no_op**; doctrine-meta produced first valid proposals (A12, A13) post-sprint |
| **Sprint 4 — RBAC** | `full-stack-fastapi-template` | Role-based access control | **BL-0007/8/9 merged_full**; **11/11 R5b first-try pass (100%, vs 38% baseline)**; **0 R13 trips**; killed mid-flight by operator to land A18 |
| Sprint 5 — documents (1st) | `full-stack-fastapi-template` | Secure Documents Hub | Aborted — events.jsonl tracked → merge guard refused (root cause: A24) |
| Sprint 5b — documents (resubmit) | `full-stack-fastapi-template` | (same) | Aborted on BL-0201 engineer_unmerged — root causes A21 (gate false-green), A22 (compose name), A25 (extractor blindspot), A26 (ENOSPC) |
| **Sprint 6 — documents_1 (in progress)** | `full-stack-fastapi-template` | (same brief, post-fixes) | PO ✅ 11 BLs at BL-0001, engineer BL-0001 ✅, gate mid-run |

The api-keys → RBAC progression is the empirical evidence that the
self-hardening loop works: R5b pass rate went from 38% to 100% after
the doctrine-meta-agent's proposals landed.

---

## 8. What's known broken

Every observed defect is classified in
[`DESIGN_SHORTCOMINGS.md`](DESIGN_SHORTCOMINGS.md). Highlights as of
2026-05-24:

### Closed (with commit refs)

Sprint-2 hardening pass (2026-05-23): A1, A2, A3, A4, A5, A6, A7, A10,
A13, A15, A16, B1, B2, B3, B4, B5, B7, B9, B12, B14, B15, B16, B17,
B18.

Today (2026-05-24): A19 (per-feature BL-0001 reset), A20 (canonical
`brief.md`), A21 (gate truthful aggregation, I-5), A22 (lowercase
compose name), A23/A24 (events.jsonl untrack), A25a (infra-aware
extractor), A25b (`kind=infra_fail`), A26 (pre-flight disk check),
WI3A (sibling-feature touch guard).

### Open

| ID | Class | Why deferred |
|---|---|---|
| A8 | R9 graph-grounding hard enforcement | Streaming gap (A11) depends on it |
| A9 | Gate subprocess pgroup leak (I-1 sibling of B1) | Closes structurally in Move 3 (ManagedSubprocess primitive, deferred) |
| A11 | R9 streaming-side gap | Depends on A8 |
| A12 | Doctrine-meta input contract drift | Promoted from doctrine-meta proposal |
| A14 | Meta-agent SKILLS.md missing `forbidden_tools` | Sibling-class of A9 |
| **A27** | Per-feature branch isolation | Doctrine + WI3A provide logical isolation today; branch-level structural guarantee deferred until parallel sprints become a real workload |
| **A28** | Playwright `--workers 1` → 4 | ONE-LINE FIX, 3-4× speedup. Deferred until current crew-quality fixes validate through one green sprint. |
| **A29** | PRE-phase result caching by `agent_branch` HEAD SHA | ~50% gate time reduction per sprint after first BL |
| **A30** | Test Impact Analysis (TIA) | 5-20× reduction on focused changes |
| **A31** | Tiered gate (per-BL fast, sprint-end full e2e) | Restructures merge contract |
| B6, B8, B10, B11, B13 | Various optimizations / triage agent | Own sprint each |

### The throughput bottleneck

The single biggest current limitation: the regression gate runs **79
playwright e2e tests at 1 worker, PRE+POST per BL**. Per-BL gate time
projects to 80-160 minutes; an 11-BL sprint projects to 17-33 hours of
gate time alone. A28 (one-line fix) yields 3-4× speedup; A28+A30
brings agentic-skills throughput in line with mainstream CI shops.
Detail in [`.claude/memory/arch_gate_throughput.md`](.claude/memory/arch_gate_throughput.md).

---

## 9. The architect's plan (what's being built next)

[`ARCHITECT_PLAN.md`](ARCHITECT_PLAN.md) defines four prerequisites for
the project to operate at full-architect autonomy:

| Batch | Deliverable | Status |
|---|---|---|
| **A** | Architectural memory artifacts + invariants framework + architect role codified in CLAUDE.md | ✅ Done |
| **B** | Doctrine-meta-agent (ABL-0003) — observes failure patterns, proposes R-rule changes; operator approves; never auto-applies | ✅ Done; two operator-approved proposals landed (R13 + R5b) |
| **C** | Framework-reviewer adversarial role — scrutinizes plans for flaws before execution | ⏸ Pending operator authorization |
| **D** | Scheduled observer — monitors health metrics from archived traces between sessions | ⏸ Pending operator authorization |

[`ARCHITECT_TRACKER.md`](ARCHITECT_TRACKER.md) is the live checklist.

The deferred items (Move 3 ManagedSubprocess for A9; A27 per-feature
branch isolation; A28-A31 gate throughput) are the next-most-important
work after Batches C and D, prioritized by what unblocks the most
downstream value.

---

## 10. How to read this project (reviewer's reading order)

If you're a reviewer with 30-60 min, read these in order:

1. **This README** — overview (you're here)
2. [`THESIS.md`](THESIS.md) — north star + definition of done
3. [`ARCHITECTURE_INVARIANTS.md`](ARCHITECTURE_INVARIANTS.md) — the 7
   structural rules
4. [`WORKFLOW.md`](WORKFLOW.md) — ASCII map of the entire pipeline
5. [`DESIGN_SHORTCOMINGS.md`](DESIGN_SHORTCOMINGS.md) — audit ledger
   (what's been seen broken, what's fixed, with commit SHAs)
6. [`ARCHITECT_PLAN.md`](ARCHITECT_PLAN.md) — current 4-batch plan
7. [`webapp/PROJECT_STATE.md`](webapp/PROJECT_STATE.md) — deep webapp
   reference (endpoints, state machine, env loading, branch history)
8. [`CLAUDE.md`](CLAUDE.md) — Claude-the-architect's bootstrap (denser;
   assumes you've read 1-7)

To see the system actually run, look at:

- `webapp/backend/app/services/orchestrator.py` — the pipeline state
  machine
- `webapp/backend/app/services/doctrine_validator.py` — R-rule
  enforcement (especially `validate_po`, `validate_engineer`,
  `_extract_test_failures`, `detect_infra_failure`)
- `webapp/backend/app/services/regression_gate.py` — the gate (PRE/POST
  + truthful aggregation + infra-fail detection + disk pre-flight)
- `webapp/backend/app/services/closure_check.py` — I-3 postcondition
  enforcement
- `webapp/backend/app/routers/projects.py` — `/run-brief` endpoint,
  run-meta tracking, B2 lock
- `skills/brownfield/brownfield-production-incremental-*/SKILLS.md` —
  role doctrine

For per-sprint detail of a real run, look at:

- `webapp/backend/traces_archive/<run_id>/` — every agent's stream,
  retrieval log, phase events, prompt, meta
- `webapp/backend/logs/orchestrator/<ts>/run.log` — orchestrator
  milestone log
- `<target-repo>/_brownfield/features/<slug>/events.jsonl` — tailable
  event stream (use `scripts/tail_feature.py`)

---

## 11. Repository contents

```
agentic-skills/
├── README.md                         ← this file (reviewer entry point)
├── CLAUDE.md                         ← architect bootstrap (denser)
├── THESIS.md                         ← vision + definition of done
├── ARCHITECTURE_INVARIANTS.md        ← the 7 structural rules
├── WORKFLOW.md                       ← pipeline ASCII map
├── PIPELINE.md                       ← 8 pipeline steps mapped to code
├── BACKLOG.md                        ← project's own 13 ABLs
├── DESIGN_SHORTCOMINGS.md            ← audit ledger
├── ARCHITECT_PLAN.md                 ← 4-batch plan
├── ARCHITECT_TRACKER.md              ← live checklist
├── IMPLEMENTATION_PLAN.md            ← completed Sprint-2 18-item hardening
├── IMPLEMENTATION_TRACKER.md         ← Sprint-2 checklist
├── RECOVERY.md                       ← operator playbook for mid-sprint failures
├── CONTINUATION_PROMPT.md            ← session handoff document
├── webapp/                           ← FastAPI + React (current production)
│   ├── backend/                      ← orchestrator, validators, gate, MCP bridges
│   ├── frontend/                     ← AppV2.jsx
│   └── PROJECT_STATE.md              ← deep webapp reference
├── langgraph_engine/                 ← original LangGraph harness
├── skills/                           ← role doctrine (SKILLS.md files)
├── rubrics/                          ← scoring rubric
├── briefs/                           ← legacy work packets (langgraph era)
├── reference-repos/                  ← fastapi-good-patterns/
├── target-repos/                     ← lg-graph-test/ (greenfield demo)
├── scripts/                          ← tail_feature.py, setup helpers
├── .planning/                        ← doctrine proposals, intel files, graphs
└── .claude/memory/                   ← cross-session architectural memory
```

---

## 12. License

Project source code is unpublished; documentation in this repository is
for review purposes only. Contact the operator (Eugene Goldberg) for
contribution / licensing inquiries.

---

*Last updated 2026-05-24. Synthesizes content from THESIS.md, CLAUDE.md,
ARCHITECTURE_INVARIANTS.md, WORKFLOW.md, PIPELINE.md, BACKLOG.md,
DESIGN_SHORTCOMINGS.md, ARCHITECT_PLAN.md, and webapp/PROJECT_STATE.md as
of commit `b2ed5c4` on branch `architect-prereqs`.*
