# Agentic Skills — Project Backlog

> **Scope:** This is the **agentic-skills project's own backlog** — the work needed to deliver the autonomous-team thesis defined in [`THESIS.md`](THESIS.md). It is distinct from any brownfield target's `.agile-v/BACKLOG.md`, which describes work the team performs *on* a target repo.
>
> **ID prefix:** `ABL-####` (Agentic Backlog item) to distinguish from `BL-####` used inside target repos.
>
> **State legend:** `Ready` (deps met) · `Blocked` (deps open) · `In Flight` · `Done` · `Parked`

---

## Sprint 0 (historical — already delivered)

Foundational work that exists today, restated as ABLs for completeness:

| ID | Title | State |
|---|---|---|
| ABL-0000a | LangGraph harness + A/B comparison runs | Done |
| ABL-0000b | Webapp execution surface (PO / Engineer / QA / Scorer endpoints) | Done |
| ABL-0000c | Doctrine validator + regression gate v3 + ff merge pipeline | Done |
| ABL-0000d | R5b / R7 / R8 / R9 / R10 / R10.1 / R10.2 / R11 / R12 / Tier 1.5 enforcement | Done |
| ABL-0000e | Retrieval MCP server (semantic_search + graph_*) + Milvus + Ollama bge-m3 | Done |
| ABL-0000f | Sprint 1 dogfood: Team Collaboration Module on `full-stack-fastapi-template` | Done |

Sprint 1 was the validation that the worker layer (Engineer/QA/Scorer) can run unattended for one feature on one target. Everything below is what's required to make that true for *any* feature on *any* target.

---

## Sprint 2 — Autonomy & orchestration

> **Goal:** Eliminate the operator's role as orchestrator. After Sprint 2, BLs flow from Ready → Merged without a human shell-launching them or deciding what to retry.
>
> **Success criterion:** Re-run a Sprint-1-scale feature on a fresh brownfield target, and the operator's only interactions are (a) kicking off the sprint and (b) answering precisely-framed escalation questions if any.

### ABL-0001 — Orchestrator agent (sprint conductor)
**Priority:** CRITICAL · **Effort:** 5 · **Dependencies:** none · **State:** Ready

**Story:** As the framework, I want an agent that owns the sprint's BL queue so that no human shell scripts are needed to move work forward.

**Acceptance:**
1. New endpoint `POST /api/projects/{repo}/run-sprint` accepts `{sprint: "C1"}` and runs all BLs in that sprint to merged-or-escalated, returning a final summary.
2. Orchestrator reads `BACKLOG.md`, builds a dependency DAG, picks the next BL whose deps are all merged, and dispatches Engineer → QA → Scorer in sequence.
3. On a `regressed`/`incomplete` outcome that exhausts retry budget, orchestrator delegates to the Triage agent (ABL-0002) — does NOT halt the sprint.
4. On `no_op` outcome (R11), orchestrator marks the BL done and moves on.
5. SSE event stream surfaces orchestrator decisions (`_meta phase=orchestrator_pick`, `_meta phase=orchestrator_skip`, etc).
6. Replaces all current `chain launcher` shell loops.

**Risk level:** Medium (touches the main router; concurrent-modification of `BACKLOG.md` state)

---

### ABL-0002 — Triage agent for `awaiting_review` outcomes
**Priority:** CRITICAL · **Effort:** 4 · **Dependencies:** ABL-0001 · **State:** Blocked

**Story:** As the framework, I want an agent that resolves stuck BLs into one of four explicit outcomes so that the operator is never asked "can you look at this branch?"

**Acceptance:**
1. Triage agent reads the failing BL's full SSE trace + worktree state + scorer rubric expectations.
2. Outputs exactly one of: `RETRY_REWRITE` (re-spawn engineer with a meta-prompt explaining the impasse), `DEFER` (mark BL parked with written justification, unblock dependent BLs if any), `SPLIT` (decompose into N smaller BLs with full PO doctrine), `ESCALATE` (write a focused human question — single decision, framed concretely).
3. Decision committed to `_brownfield/<BL>/triage.md` with reasoning.
4. Escalations go to the Escalation Bridge (ABL-0007) when implemented; until then, they print to stdout + write a file.

**Risk level:** Medium (the SPLIT path requires PO-level judgment)

---

### ABL-0003 — Doctrine agent (meta)
**Priority:** HIGH · **Effort:** 4 · **Dependencies:** ABL-0001 · **State:** Blocked

**Story:** As the framework, I want an agent that observes recurring failure patterns across BLs and proposes new R-rules so that doctrine hardens itself.

**Acceptance:**
1. After each sprint, doctrine agent reads every BL's trace dir + SSE stream + scorer rubric findings.
2. Identifies recurring failure modes (e.g., "in 9 of 13 BLs the engineer omitted citations on first commit and R5b had to retry").
3. Drafts a PR against `webapp/backend/app/services/doctrine_validator.py` and the relevant prompt builders, proposing an R-rule change.
4. The PR is opened as a real git branch on the agentic-skills repo (not the target) for operator review — this is meta-work, so a human approves doctrine changes.
5. Produces `.planning/doctrine_proposals/<sprint>-<topic>.md` with motivation, evidence count, and proposed change.

**Risk level:** Low (output is a PR, not a live patch — operator approves)

**Why operator-reviewed:** doctrine changes affect every future BL. The doctrine agent earns trust over many sprints before it merges directly.

---

### ABL-0004 — Escalation Bridge (Slack / Linear)
**Priority:** HIGH · **Effort:** 3 · **Dependencies:** ABL-0002 · **State:** Blocked

**Story:** As an operator, I want triage-escalated questions to reach me on Slack so that I can answer asynchronously without watching SSE streams.

**Acceptance:**
1. Triage agent's `ESCALATE` outcome posts to a configured Slack channel with: BL ID, the specific question (one sentence), 2-3 option choices (`A`/`B`/`C`/free-text), and a link to the trace dir.
2. Operator answer (Slack thread reply) is routed back to the framework via webhook.
3. Orchestrator resumes the BL with the operator answer fed into the agent's next prompt.
4. Fallback: if Slack isn't configured, write to `.planning/escalations/<timestamp>-<BL>.md` and pause.

**Risk level:** Low

---

### ABL-0005 — Convert Sprint 1's chain launchers to orchestrator-driven
**Priority:** MEDIUM · **Effort:** 1 · **Dependencies:** ABL-0001 · **State:** Blocked

**Story:** As the framework, I want the shell `chain launcher` scripts that ran Sprint 1 to be retired so that there's exactly one path through the system.

**Acceptance:**
1. Delete `/tmp/bl*_chain.log` patterns and `nohup bash -c '...'` wrappers from session scripts.
2. Document the orchestrator endpoint as the only entry point for multi-BL runs.
3. CLAUDE.md updated to reference `POST /run-sprint` instead of any per-BL recipe.

**Risk level:** Trivial

---

## Sprint 3 — Planning & sprint kickoff

> **Goal:** Take product-level intent ("add billing", "ship SSO") and produce a complete grounded BACKLOG.md without human authoring.
>
> **Success criterion:** Operator types one feature description, gets back a sprint-ready backlog + per-BL contexts within ~30 minutes, then walks away.

### ABL-0006 — Sprint Planner agent (PO-from-spec)
**Priority:** CRITICAL · **Effort:** 5 · **Dependencies:** ABL-0001 · **State:** Blocked

**Story:** As an operator, I want to provide a product-level feature description and the brownfield target, and have an agent produce a complete BACKLOG.md plus per-BL `codebase_context.md` files.

**Acceptance:**
1. New endpoint `POST /api/projects/{repo}/plan-sprint` accepts `{requirement: "..."}` and runs an autonomous PO session.
2. Sprint planner grounds in the target codebase (≥10 retrieval calls — higher floor than per-BL PO because scope is bigger), reads existing BACKLOG.md if present, and writes a new sprint section.
3. Output BLs have: ID, Story, REQ mapping, Codebase Context Reference, Impacted Components, Compatibility & Migration Notes, Risk Level, Spike Tasks, Acceptance criteria, Effort, Dependencies, Status — matching the schema Sprint 1 BLs used.
4. Per-BL `codebase_context.md` files generated and pass `validate_po`.
5. Operator reviews the BACKLOG.md + can edit / reject before kicking off the sprint via orchestrator. (Eventually this review becomes optional.)

**Risk level:** High — bad decomposition cascades into every downstream BL

---

### ABL-0007 — Cross-project memory layer
**Priority:** HIGH · **Effort:** 4 · **Dependencies:** ABL-0006 · **State:** Blocked

**Story:** As the framework, I want lessons learned on one brownfield target (failure modes, gotchas, useful patterns) to flow into future sprints on other targets so that the team accumulates expertise rather than restarting from zero each time.

**Acceptance:**
1. New `cross-project-memory/` directory at the repo root, with per-domain markdown files (e.g., `fastapi-conventions.md`, `react-tanstack-router-patterns.md`, `sqlmodel-alembic-migrations.md`).
2. Retrospective agent (ABL-0009) writes entries here at sprint close.
3. Sprint Planner and per-BL PO query this layer during grounding (extends retrieval surface).
4. Memory entries cite source: which sprint, which BL, which target.

**Risk level:** Medium (avoid the memory layer becoming stale lore)

---

### ABL-0008 — Requirements-doc ingester
**Priority:** MEDIUM · **Effort:** 3 · **Dependencies:** ABL-0006 · **State:** Blocked

**Story:** As an operator, I want to point the planner at a Linear/Notion/Markdown requirements doc instead of a single sentence so that real product specs work as input.

**Acceptance:**
1. Sprint Planner accepts `{requirement_url: "..."}` or `{requirement_file: "path"}` in addition to inline text.
2. For Linear: read epic + child issues via API; treat each issue as a candidate BL boundary (or merge/split as the planner sees fit).
3. For Notion / Markdown: parse headings as feature boundaries.
4. Planner explicitly notes when it merges or splits source-doc items, with reasoning.

**Risk level:** Low (additive input adapter)

---

## Sprint 4 — Self-improvement & meta

> **Goal:** The team learns from its own runs without operator intervention.

### ABL-0009 — Retrospective agent
**Priority:** HIGH · **Effort:** 3 · **Dependencies:** ABL-0003, ABL-0007 · **State:** Blocked

**Story:** As the framework, I want an agent that runs at sprint close, writes institutional learnings to `cross-project-memory/`, and seeds the next sprint with relevant context.

**Acceptance:**
1. Runs automatically when orchestrator reports `sprint_complete`.
2. Reads all per-BL traces, scorecards, doctrine proposals from the sprint.
3. Outputs `_brownfield/SPRINT_RETRO_<id>.md` with: what worked, what didn't, recurring failure modes, score-trajectory analysis, recommendations for next sprint's planner.
4. Updates `cross-project-memory/*.md` with newly-learned patterns.
5. Outputs are read by the next sprint's planner during its grounding phase.

**Risk level:** Low

---

### ABL-0010 — Meta-rubric (scoring the process, not just the output)
**Priority:** MEDIUM · **Effort:** 3 · **Dependencies:** ABL-0003, ABL-0009 · **State:** Blocked

**Story:** As the framework, I want a rubric that scores the *team's process* per sprint (retry rate, escalation rate, doctrine-rule trigger counts, time-to-merge variance) so that improvements are visible across sprints.

**Acceptance:**
1. New rubric `rubrics/team_process_scorecard.md` covering dimensions: Self-correction (R10.1 success rate), Grounding (citations-on-first-try rate), Throughput (mean time-to-merge), Escalation efficiency (% of escalations the operator actually had to answer vs could have been auto-resolved).
2. Computed by the Retrospective agent at sprint close.
3. Posted to `cross-project-memory/team_health_<sprint>.md` and rendered as a trend chart over sprints.

**Risk level:** Trivial

---

## Sprint 5 — Scale

> **Goal:** The team handles concurrent BLs, multiple target repos, and real cost-visibility.

### ABL-0011 — Concurrent BL execution
**Priority:** MEDIUM · **Effort:** 5 · **Dependencies:** ABL-0001 · **State:** Blocked

**Story:** As the framework, I want to run multiple independent BLs in parallel so that sprint throughput scales with API capacity rather than serial agent runs.

**Acceptance:**
1. Orchestrator dispatches up to N concurrent Engineer/QA/Scorer sessions where BL dependency graph permits.
2. Worktree isolation already supports this (each agent gets its own worktree); orchestrator coordinates Milvus + graph index concurrency, gate scheduling (one gate at a time on shared Docker resources), and merge serialization (still ff-only, queued).
3. Configurable concurrency limit per role; defaults: 2 engineers, 2 QAs, unlimited scorers (cheap, fast).
4. SSE stream prefixes events with task-id so concurrent runs are distinguishable on the UI side.

**Risk level:** High (resource contention, race conditions on shared state)

---

### ABL-0012 — Multi-target operations
**Priority:** LOW · **Effort:** 4 · **Dependencies:** ABL-0007, ABL-0011 · **State:** Blocked

**Story:** As an operator, I want the team to work on multiple brownfield targets simultaneously so that one set of agents serves many projects.

**Acceptance:**
1. Multi-tenant repo registration in webapp config; each target gets its own `agent_branch` and gate config.
2. Orchestrator round-robins or priority-schedules across active targets.
3. Cross-project memory remains shared (that's the point).
4. Telemetry partitions per-target.

**Risk level:** Medium

---

### ABL-0013 — Cost + telemetry layer
**Priority:** HIGH · **Effort:** 3 · **Dependencies:** ABL-0001 · **State:** Blocked

**Story:** As an operator, I want to see $ per BL, $ per sprint, time-to-merge distribution, and R-rule trigger frequencies so that I know what the team costs and where it's wasteful.

**Acceptance:**
1. Each agent SSE result event already carries `total_cost_usd` — aggregate per BL, per sprint, per role.
2. New endpoint `GET /api/telemetry/sprint/{id}` returns aggregated metrics.
3. Frontend dashboard (could ride on Sprint 1's dashboard work) renders trend charts.
4. Per-R-rule trigger counts surface which rules are catching real bugs vs adding overhead.

**Risk level:** Low

---

## Backlog summary

| Sprint | BLs | Themes | Operator-time impact |
|---|---|---|---|
| Sprint 2 | ABL-0001 → 0005 | Autonomy, orchestration, triage, escalation | ~10h/feature → ~3h/feature |
| Sprint 3 | ABL-0006 → 0008 | Sprint planning from product intent | ~3h/feature → ~1.5h/feature |
| Sprint 4 | ABL-0009 → 0010 | Self-improvement, meta-rubric | ~1.5h/feature → ~1h/feature |
| Sprint 5 | ABL-0011 → 0013 | Concurrency, multi-target, telemetry | Sub-linear scaling beyond ~1h/feature |

---

## Out of scope (explicit non-goals)

- Replacing the operator's judgment on doctrine changes (ABL-0003 deliberately stops at "open a PR").
- Real-time UI for watching agents work — the SSE stream is enough; we are async by design.
- Greenfield-from-scratch project generation. The thesis is brownfield only.
- Architectural-level rewrites within a target repo. The team adds *features*; structural reorgs need a human.

---

## How to start Sprint 2

1. Read `THESIS.md` for the why.
2. Pick `ABL-0001` (Orchestrator) — it unblocks the rest.
3. Run it through the existing PO → Engineer → QA → Scorer pipeline on this repo (yes, the team builds itself).
4. When ABL-0001 merges, kick off ABL-0002 + ABL-0003 in parallel; both depend only on the orchestrator existing.
