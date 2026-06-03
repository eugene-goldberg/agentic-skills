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

### ABL-0014 — Acceptance Agent (end-to-end UAT pass)
**Priority:** HIGH · **Effort:** 4 · **Dependencies:** ABL-0001 · **State:** IMPLEMENTING (Batches A+B shipped, Batch C in flight)

**Story:** As the framework, I want a sprint-close role that exercises the *assembled feature as a whole* against the *brief as a whole* — seeding realistic multi-user state, walking each end-to-end journey via playwright with full-page screenshots, and producing a calibrated report — so that the operator sees what per-BL QA structurally cannot (cross-BL handoffs, cross-component bugs, framing-bias defects).

**Acceptance:**
1. New skill `skills/brownfield/brownfield-acceptance-agent/SKILLS.md` defining the role's inputs (brief.md, BACKLOG.md, merged agent_branch), outputs (`_brownfield/features/<slug>/acceptance/`), constraints (read-only on code, one honest pass, classification enum), and hard caps (≤8 journeys × ≤15 steps).
2. Validator + flow + R10.1 retry + archive + closure_check extension landed and tested.
3. Wired into `run_brief` between `sprint_complete` and `doctrine_meta` as advisory-only (failure becomes an event, never aborts the sprint).
4. Frontend checkbox + summary tile.
5. Default `run_acceptance=False` for the first 3 calibration sprints; flip after FP-rate calibration.

**Reference:** [`ABL-0014_ACCEPTANCE_AGENT_IMPLEMENTATION.md`](ABL-0014_ACCEPTANCE_AGENT_IMPLEMENTATION.md), commits `4a5c108` (A), `f1bdb8b` (B).
**Risk level:** Medium (cost ceiling enforced; advisory only)

---

### ABL-0015 — Auto-dispatch follow-up engineer on `product_bug` acceptance findings
**Priority:** MEDIUM · **Effort:** 3 · **Dependencies:** ABL-0014 · **State:** Implemented (flag-OFF, pending live calibration smoke)

**Story:** As the framework, once the Acceptance Agent classifies a journey failure as `product_bug` and the operator has confirmed acceptance is reliable, I want the orchestrator to auto-spawn a follow-up engineer to attempt the fix — so the feedback loop closes without an operator round-trip for unambiguous bugs.

**Acceptance:**
1. New flag `run_acceptance_followup: bool` (default False until calibrated). ✅
2. On `product_bug` findings, the orchestrator constructs a focused remediation BL referencing the acceptance report + screenshots and spawns an engineer in a fresh worktree. ✅
3. Cost cap: max 1 follow-up per sprint to start; revisit after calibration. ✅ (`FOLLOWUP_COST_CAP=1`)
4. Acceptance Agent re-runs (or doesn't) per operator policy. ✅ (v1 = no auto re-run, §9 D3)

**Risk level:** High (crosses two new invariant boundaries — acceptance becomes a writer; engineer gets non-PO-decomposed work)

**Status (2026-06-02):** Code batches A–D shipped on `architect-prereqs`
(design `d7b1088`; A `912f21e`; B `29f5ac6`; C `df0e4ff`; D `b45919d`).
Design + grounding in [`ABL-0015_AUTO_DISPATCH_DESIGN.md`](ABL-0015_AUTO_DISPATCH_DESIGN.md).
Operator-approved v1 policy: conservative verdict gate (`verdict ==
"confirmed"` only), cost cap 1, no auto re-run, gate-fail → manual review.
New doctrine rule **R15** (dispatch-at-most-once) enforced by the
selector's `dispatch_state is None` filter. closure_check covers the
follow-up worktree (`scan_stale_followup_worktrees`). Reuses
`_engineer_flow` unchanged (selector + invoker, not a new executor).
208/208 backend tests pass. **Batch E** (live calibration smoke on the
real Journey 03 `product_bug`) is operator-gated and remains the only
open step before the flag can flip ON.

---

### ABL-0016 — Lessons-as-context (cumulative learning, Stage 1)
**Priority:** MEDIUM · **Effort:** 2 · **Dependencies:** ABL-0014 §I.3 · **State:** Implemented (flag-OFF, pending live calibration smoke)

**Story:** As the framework, I want every brownfield role (PO, engineer, QA, scorer) to see prior operator-confirmed lessons for the target as advisory context, so the crew's hard-won findings become inputs to future work — "what's learned on one target carries forward" (the mission's *cumulative* property, its least-mature axis).

**Acceptance:**
1. A target-scoped lessons reader unions confirmed/deferred findings across all feature ledgers in the repo. ✅
2. A shared advisory block (silent when empty) is injected into all four brownfield role prompts at the verified seams. ✅
3. Flag `inject_lessons: bool` (default OFF until calibrated). ✅
4. Injection provenance recorded per run/role/bl_id (the Stage-2 efficacy hook). ✅

**Risk level:** Low (advisory context, no new R-rule, no subprocess/closure impact; lessons are falsification priors, not binding rules).

**Status (2026-06-03):** Code batches A–C shipped on `cumulative_learning`
(roadmap `f259439`; ABL-0016 plan `e600044`; program plan `29b9503`;
A `eb20d6f`; B `294f725`; C provenance `512a1c5`). Design + grounding in
[`ABL-0016_LESSONS_AS_CONTEXT.md`](ABL-0016_LESSONS_AS_CONTEXT.md); whole-
feature program in [`CUMULATIVE_LEARNING_IMPLEMENTATION_PLAN.md`](CUMULATIVE_LEARNING_IMPLEMENTATION_PLAN.md).
v1 = Option A (prompt injection), target-scoped. 233/233 backend tests
pass. The **live calibration smoke** (one sprint with `inject_lessons=true`
on a target with prior confirmed findings) is operator-gated and is the
only open step before the flag can flip ON. This is **Stage 1 of a 4-stage
program** — ABL-0017 (closed-loop doctrine efficacy), ABL-0018 (cross-target
transfer), ABL-0019 (pattern profile) follow.

---

### ABL-0020 — Doctrine-spec registry (I-2 fulfillment + per-run manifest)
**Priority:** HIGH · **Effort:** 2 · **Dependencies:** none (discharges I-2) · **State:** Implemented (complete)

**Story:** As the framework, I want a single in-code doctrine-spec data structure naming every R-rule, its enforcement point, and a resolvable check — the standing I-2 mandate — plus a per-run snapshot of which rules were active, so doctrine is machine-readable and ABL-0017 Stage-2 efficacy can attribute outcomes to rules.

**Acceptance:**
1. `doctrine_spec.py` registry of all canonical rules (enforcement_point, enforced flag, resolvable check_ref, targeted_failure_class). ✅
2. I-2 meta-test: enforced→resolvable check; unenforced→declared gap; registry covers the canonical set. ✅
3. Per-run `doctrine_manifest` snapshotted into A7 run state. ✅
4. Consistency guard: registry ↔ CLAUDE.md prose table drift fails CI. ✅

**Risk level:** Low (pure data + test + a nullable state field; no agent-facing behavior change).

**Status (2026-06-03):** Complete on `cumulative_learning` (A `624886f`,
B `016ef5c`, C `db7d8d7`). Plan: [`ABL-0020_DOCTRINE_SPEC_REGISTRY.md`](ABL-0020_DOCTRINE_SPEC_REGISTRY.md).
Discharges the long-standing I-2 architectural mandate (marked FULFILLED in
ARCHITECTURE_INVARIANTS.md) and is the **keystone** unblocking ABL-0017
Stage 2 — emerged from ABL-0017's Batch-0 verification gate, which found
Stage 2 couldn't attribute outcomes to rules without it. 248/248 tests.
R9 remains the one declared gap (A8); full per-rule synthetic-harness tests
are follow-up.

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
| Mid-stream | ABL-0014 → 0015 | Acceptance pass + auto-dispatch follow-up | Closes per-BL-isolation gap; lower false-merge rate |

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
