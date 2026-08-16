# The Harness — what it is, what it does, why we hand-built one

> **Audience.** Engineers and architects new to agentic-skills who need to
> understand what "the harness" is, why it exists, and how it shapes the
> flow of a sprint from brief submission to merged feature. Also a primer
> on **harness engineering** as a discipline: when LLM-based agents are
> doing real work in a real codebase, the harness is the structural
> machinery that turns "an LLM with tools" into "a crew that ships."
>
> **Scope.** Conceptual and architectural. Code references point to
> `webapp/backend/app/services/` for the canonical implementations.
> Doctrine details belong in `ARCHITECTURE_INVARIANTS.md` and
> `DESIGN_SHORTCOMINGS.md`; this document references them but does not
> duplicate them.
>
> **Reading order.** If you read top-to-bottom you'll understand the
> harness via the flow it runs. If you need a reference for a specific
> mechanism (gates, retries, validators), jump to §6.

---

## 1. The mission, in one paragraph

The agentic-skills project builds an autonomous, synthetic AI crew that
takes a feature narrative (a brief) for a real brownfield codebase and
delivers a merged, regression-tested, conventions-respecting
implementation — with no human in the loop for the bulk of the work. The
crew is composed of role-specialized LLM agents: a **Product Owner**
that decomposes the brief into baseline items (BLs); an **Engineer** that
implements each BL; a **QA** agent that adds reinforcement tests; a
**Scorer** that grades against a brownfield rubric. A separate
**doctrine-meta-agent** runs after each sprint to propose hardening of
the rules the crew operates under. **The harness is the code, contracts,
and conventions that turn these agents from "LLMs in a loop" into a crew
that can actually be left alone for hours and trusted to come back with
something real.**

---

## 2. What "harness" means in this project

The term is used multiply in commits, docs, and chat. Pin it down:

| Layer | Lives at | Role |
|---|---|---|
| **1. Doctrine** | `ARCHITECTURE_INVARIANTS.md`, `DESIGN_SHORTCOMINGS.md`, R-rules table | Rules and invariants. *Not harness — but enforced by it.* |
| **2. Agent contracts** | `skills/brownfield/*/SKILLS.md` (PO, Engineer, QA, Scorer, doctrine-meta) | Per-role prompts that translate doctrine into instructions agents read. *Not harness — but delivered by it.* |
| **3. Host harness** | `webapp/backend/app/` | Control plane: orchestrator, validators, stream parser, gate parser, worktree manager, trace writer, closure check. **`harness_sha` in `meta.json` refers to this.** |
| **4. Target harness** | Inside each agent_branch: `.agentic-skills.json`, `scripts/regression_gate.sh`, `compose.gate.yml`, gitignore additions, `_brownfield/features/<slug>/` layout | Files the host harness writes into the target repo so the target can be tested by the gate. **`POST /init-feature` automates installing this.** |
| **5. External deps** | Milvus, Ollama, graphify, claude-context, claude CLI, Docker | Infrastructure the harness orchestrates. *Not harness.* |

When someone says "the harness," they almost always mean **layer 3 +
layer 4**: the agentic-skills-side control plane and the per-target
scaffolding it installs. Layers 1 and 2 are *what the agents must do*;
the harness is *what makes them actually do it*.

### Why the host/target split matters

Code in the **host harness** affects ALL future sprints the moment it's
committed to the agentic-skills repo. Code in the **target harness**
only affects the branch it's committed to. That's why the canonical
target-harness files live as templates at
`webapp/backend/app/templates/` — every new feature branch the
`/init-feature` endpoint creates gets a fresh copy of the current
canonical target harness, so a target-harness bug fix propagates by
re-init, not by mass-cherry-pick.

---

## 3. The crew and what each agent owns

Each role's prompt is in `skills/brownfield/<role>/SKILLS.md`. The
harness reads these at sprint time and embeds them verbatim into the
subprocess prompt.

| Role | Input | Output |
|---|---|---|
| **Product Owner (PO)** | The brief + indexed codebase | `CODEBASE_CONTEXT.md`, `SPRINT_PLAN_C1.md`, `BACKLOG.md` (N baseline items with per-BL `codebase_context.md`) |
| **Engineer** | One BL's spec + per-BL codebase context | Source code changes + `eng_patterns.md` artifact, committed on an isolated agent worktree |
| **QA** | The engineer's merged BL + per-BL context | Reinforcement tests + `qa_impact.md` artifact, committed on a sibling worktree |
| **Scorer** | All artifacts for the BL | A rubric-scored verdict against `rubrics/production_grade_scorecard_brownfield.md` |
| **Doctrine-meta** (per sprint, not per BL) | Sealed trace archive of the run | Markdown proposals in `.planning/doctrine_proposals/` recommending changes to doctrine or harness — operator-gated, never auto-merged |

These are LLM subprocesses, not microservices. They run as `claude
--print` invocations with stream-json output. The host harness spawns
them, watches their output, and decides what to do with it.

---

## 4. The two harnesses, in detail

### 4.1 Host harness (`webapp/backend/app/`)

The control plane. The pieces that matter:

| Module | Responsibility |
|---|---|
| `routers/projects.py` | HTTP/SSE entrypoints (`POST /run-brief`, `POST /init-feature`, `POST /merge-branch`, `GET /branches`, `GET /traces`) |
| `services/orchestrator.py` | The `run_brief` coordinator: index → PO → for each BL (engineer → reindex → QA → reindex → scorer) → sprint_complete → doctrine_meta → closure_check |
| `services/claude_agent.py` | Spawns `claude` as a subprocess, reads its stream-json output line-by-line, emits `_meta` phase events. **A44 lives here:** raises the StreamReader buffer to 64 MiB so large file reads don't kill the subprocess mid-read. |
| `services/doctrine_validator.py` | Validates each role's artifacts against contracts: artifacts present (≥120 bytes), retrieval citations counted, layer-coverage satisfied (A36), SQLModel/migration tablename consistency (A36 fix #4). Returns kind ∈ {`complete`, `incomplete`, `give_up`}. |
| `services/regression_gate.py` | Runs the target's `test_cmd` twice (PRE and POST) in disposable docker stacks, parses pytest output, classifies the result kind ∈ {`green`, `regressed`, `inconclusive`, `error`, `skipped`}. |
| `services/git_worktree.py` | Creates per-agent isolated worktrees, `fast_forward_target` merges them onto the agent_branch. **A35 fix #2 lives here:** strips untracked `graphify-out` before merge. |
| `services/closure_check.py` | At `sprint_complete`, asserts no orphaned worktrees / agent branches / docker containers / state files remain. Emits violations. |
| `services/traces.py` | Per-agent `TraceWriter` writes `stream.jsonl`, `phase_events.jsonl`, `meta.json`, `retrieval.jsonl` under `traces/<repo>/<ts>-<role>-<bl>-<task_id>/`. |
| `services/indexing.py` | Wraps the graphify + claude-context subprocess invocations that index the target before each phase. |
| `services/prompts_brownfield.py` | Builds per-role prompts from SKILLS.md + brief + per-BL context. The doctrine retry prompt (`build_fix_prompt`) names exact missing artifacts. |
| `services/repo_config.py` | Reads `.agentic-skills.json` from the target. |
| `services/run_state.py` | Disk-persisted run state under `.orchestrator-state/{live,done}/` (A7). |
| `app/templates/regression_gate.sh` + `compose.gate.yml` | Canonical target-harness templates that `/init-feature` writes into new branches. |

Three properties characterize the host harness:

- **Owns refs.** Per R13, agents are forbidden from running
  history-rewriting git commands. The host harness owns all
  fast-forwards, rebases, and reset operations. Streaming-side
  enforcement kills any agent subprocess that tries.
- **Owns retries.** The harness, not the agent, decides when to give up.
  R10/R10.1/R10.2 are budget constants the orchestrator enforces; agents
  are simply re-spawned with focused fix prompts when their last
  attempt's artifacts were incomplete or their gate regressed.
- **Owns observability.** Every per-agent run writes a sealed trace dir
  the doctrine-meta-agent can read after sprint close. The host harness
  also emits `_meta phase=...` events that flow as SSE to the operator
  and as `events.jsonl` lines in the target repo's
  `_brownfield/features/<slug>/`.

### 4.2 Target harness (committed into each agent branch)

What the host harness writes into the target so the target can be tested:

| File | Purpose |
|---|---|
| `.agentic-skills.json` | Per-target config: `agent_branch`, `main_ref` (usually `master`), `doctrine` (`brownfield`), `test_cmd` (default: `["sh", "scripts/regression_gate.sh"]`) |
| `scripts/regression_gate.sh` | The 3-stage test runner — frontend lint+typecheck+build, backend pytest, playwright e2e — emitting synthetic pytest-format lines so the host parser treats each stage uniformly |
| `compose.gate.yml` | Docker-compose overlay that brings up a disposable test stack: db, backend, frontend, mailcatcher, playwright runner |
| `.gitignore` additions | `graphify-out` (A35 fix #1), `_brownfield/features/*/events.jsonl` |
| `_brownfield/features/<slug>/` | Per-feature artifact tree (A18 isolation): brief.md, BACKLOG.md, CODEBASE_CONTEXT.md, per-BL contexts, the tailable events.jsonl |

The target harness is small (~200 lines total) but architecturally
significant — it's what lets the host harness treat any FastAPI+SQLModel
repo as testable without per-target code.

---

## 5. The full flow, annotated

This is the canonical sprint flow as a brief goes from submission to a
merged feature. Each numbered step calls out which harness facet acts.

### 5.1 Pre-sprint — feature bootstrap

**5.1.1 Operator types a feature name and clicks "Start clean baseline"
in the webapp UI.**
The webapp posts `{feature_name}` to `POST /api/projects/<repo>/init-feature`.

**5.1.2 The host harness installs the target harness on a new branch.**
`init-feature` (in `routers/projects.py`):

1. Slugifies the name (`_slugify`).
2. Refuses to act if the target's working tree is dirty (409) or the
   branch already exists (409). *I-3 closure invariant: don't clobber.*
3. `git checkout <main_ref> && git checkout -b <slug>` against the
   target repo at `webapp/backend/repos/<repo>`.
4. Appends `graphify-out` and `_brownfield/features/*/events.jsonl` to
   `.gitignore` (idempotent merge).
5. Writes `scripts/regression_gate.sh` and `compose.gate.yml` from the
   canonical templates at `webapp/backend/app/templates/`.
6. Writes `.agentic-skills.json` pointing `agent_branch` at the new slug.
7. Creates `_brownfield/features/<slug>/` with `.gitkeep`.
8. Commits the lot as a single `chore(<slug>): bootstrap feature branch`.

The endpoint returns the path where the operator should drop the brief
(`_brownfield/features/<slug>/REQUIREMENTS.md`) and the new branch SHA.

> This replaces the manual `RUNBOOK_clean_brownfield_reset.md`
> procedure — the operator no longer needs to know what a cherry-pick is.

### 5.2 Submission — `POST /run-brief`

**5.2.1 Request acceptance.**
The webapp posts `{brief, project_name, stop_on_failure, run_doctrine_meta, …}`.
The router (`routers/projects.py:run_brief`):

- Mints `run_id = run-<UTC-ts>-<rand6>`. *I-4 run identity: one ID,
  threaded through every artifact.*
- Acquires a per-repo lock to dedupe concurrent submissions (B2).
- Returns a `text/event-stream` SSE response that the orchestrator
  generator yields events into.
- **A34 caveat:** the orchestrator runs in the SSE generator; if the
  client closes the stream, the orchestrator dies. Operators use
  long-lived clients (`curl -N`, browser SSE).

**5.2.2 Run-level setup (orchestrator.py).**

- Persists the brief to two locations in the target worktree:
  `<target>/_brownfield/features/<slug>/sprint_briefs/<run_id>-<slug>.md`
  and the canonical `<target>/_brownfield/features/<slug>/brief.md` (A17).
- Writes a disk state file at `.orchestrator-state/live/<run_id>.json`
  (A7), so a crash-restart can recover.
- Opens a `events.jsonl` stream at the per-feature directory; every
  `_meta` phase event lands here (the "truth log" for operators and the
  doctrine-meta-agent).
- Pre-flights Milvus and Ollama. If either is unreachable, abort early
  with a clear error.

### 5.3 Initial indexing

Two short-lived subprocesses run in parallel against the target repo:

- **graphify** — AST-based code graph extraction. Cached at
  `~/.cache/agentic-skills/graphify/<sha256(repo)[:16]>/`; the target
  carries only a symlink to it (which is why `graphify-out` is
  gitignored — A35).
- **claude-context** — semantic chunk extraction into a Milvus
  collection keyed by feature slug.

Both must succeed before the PO is spawned. The host harness emits
`orchestrator.index_initial.{start,done}` events.

### 5.4 PO phase — decomposition

**5.4.1 Worktree fork.**
`git_worktree.create_worktree` forks `agent/<task_id>` off `target_ref`.
Worktree isolation (I-1) means the PO can read/write freely without
affecting the canonical checkout or any other agent worktree.

**5.4.2 Subprocess spawn.**
`claude_agent.stream_agent_task` invokes `claude --print --output-format
stream-json` with:

- The brief
- PO SKILLS.md verbatim
- Allowed tools: `Bash`, `Read`, `Write`, `Edit`, and the
  `mcp__retrieval__*` family (semantic_search, graph_summary,
  graph_neighbors, graph_find_similar)
- A retrieval log path so every grounding call is observable

**5.4.3 Streaming enforcement (Tier 1.5).**
While the subprocess runs, the host harness reads its stream-json line
by line. Two streaming-side enforcement rules fire:

- **Pre-modification grounding (R5):** the harness counts `mcp__retrieval__*`
  tool calls. If the agent tries to `Write` or `Edit` source code before
  it has ≥3 grounded calls, the host kills the subprocess and emits
  `phase=pregrounding_violated kind=insufficient`.
- **Forbidden git operations (R13):** if the agent attempts
  `git rebase`, `git reset --hard`, `git push --force`,
  `git filter-branch`, `git commit --amend`, etc., the host kills the
  subprocess. The orchestrator owns refs.

These are kill-on-detect — not retry-on-warning. They prevent the agent
from producing work the post-validation would have rejected anyway,
saving cycles and gate time.

**5.4.4 Post-validation (doctrine_validator).**
After the subprocess exits, `validate_po` checks the required artifacts
exist with substantive content (≥120 bytes) on disk:

- `_brownfield/features/<slug>/_codebase_context/CODEBASE_CONTEXT.md`
- `_brownfield/features/<slug>/SPRINT_PLAN_C1.md`
- `_brownfield/features/<slug>/BACKLOG.md`
- For each BL the PO declared: `_brownfield/features/<slug>/<BL-id>/codebase_context.md`

A36 layer-coverage check: the BACKLOG-declared layers (model, migration,
test, route, dependency, frontend build) each have at least one cited
chunk in the per-BL context.

Result kind ∈ {`complete`, `incomplete`, `give_up`}.

**5.4.5 Doctrine retry (R10.1).**
On `incomplete`, the harness re-spawns the PO in the SAME worktree with
a focused fix prompt naming exactly which artifacts are missing or
under-cited. Up to 2 R10.1 retries. After the third `incomplete`,
`give_up` fires and the orchestrator aborts the sprint with
`reason="po did not deliver doctrine artifacts"`.

> This is the central pattern of the harness: **the validator names what
> is missing in machine-readable form; the harness assembles a delta
> prompt; the agent gets exactly one more chance focused on the gap.**

**5.4.6 BACKLOG parse.**
On `complete`, the orchestrator reads `BACKLOG.md` and emits
`orchestrator.backlog_parsed` with the BL list. This is the contract
between the PO phase and the BL loop.

### 5.5 The per-BL loop

For each BL in BACKLOG order, the orchestrator runs the same pipeline:

```
engineer → reindex → QA → reindex → scorer → bl.done
```

#### 5.5.1 Engineer phase

- Fresh worktree fork `agent/eng-<bl>-<task_id>` off the agent_branch
  (now including all prior BLs' merged code).
- Subprocess spawn with engineer SKILLS.md + per-BL context.
- **Tier 1.5 streaming kills** for R5, R13 as in PO phase.
- Post-validation: `validate_engineer` checks `eng_patterns.md`
  artifact, retrieval citations, **and that source code actually
  changed** (no doc-only commits).
- **A36 fix #4 pre-merge validator:** SQLModel/migration tablename
  consistency.
- R10.1 doctrine retry budget (up to 2).
- `regression_gate.run_gate` executes the target's `test_cmd` twice:
  PRE on `agent_branch`, POST on `agent_branch + engineer commit`.
  Computes the diff in failing tests; classifies kind ∈ {`green`,
  `regressed`, `error`, `inconclusive`}.
- On `regressed`: **R10 gate retry** with a focused prompt naming the
  specific failing tests. Up to 2 R10 retries.
- On `green`: `fast_forward_target` merges the engineer's commit onto
  `agent_branch`. **A35 fix #2 strips untracked graphify-out
  pre-merge.** A1 auto-rebase handles non-FF (operator-side commits).
- On `error` (gate infrastructure failure, not test failure): operator
  escalation.

#### 5.5.2 Reindex

After the engineer's merge, `indexing.py` reindexes incrementally so
the QA agent's retrieval sees the new code. Emits
`orchestrator.reindex_after_engineer.<BL>.{start,done}`.

#### 5.5.3 QA phase

Same shape as engineer: fork worktree, spawn, Tier 1.5, post-validate,
R10.1 retry, gate, R10 retry, fast-forward merge.

The QA agent's job is to **add reinforcement tests for the BL** — both
characterization tests (codifying current behavior so future BLs can't
silently regress it) and edge-case coverage the engineer didn't write.

A37 handler: if the QA merge fails despite the gate being green, the
harness emits `qa_merge_failed` and aborts under `stop_on_failure=true`.
**No silent advancement past a failed merge.** This was the documents_2
BL-0002/BL-0007 lesson — without A37 the orchestrator would have shipped
engineer code without QA tests and called it "merged."

#### 5.5.4 Reindex (again)

After the QA merge, incremental reindex so the scorer's retrieval sees
the full BL state.

#### 5.5.5 Scorer phase

- Subprocess spawn with scorer SKILLS.md + the full per-BL artifact
  tree + `rubrics/production_grade_scorecard_brownfield.md` verbatim.
- Post-validation: `validate_scorer` checks that a scorecard with ≥3
  retrieval citations was produced.
- The brownfield rubric enforces five axes (Pattern Fidelity, Regression
  Coverage, Characterization Tests, Invariant Preservation, Blast
  Radius). **Any axis ≤2 forces a Fail verdict regardless of total
  (R7).** This prevents "passing on average" while breaking a specific
  brownfield principle.

#### 5.5.6 `bl.done`

The orchestrator computes the BL outcome:
- `merged_full` — engineer + QA + scorer all on agent_branch
- `merged_no_qa` — engineer merged, QA gave up
- `merged_no_score` — engineer + QA merged, scorer crashed
- `engineer_unmerged` — engineer never merged (sprint aborts under
  `stop_on_failure=true`)
- `no_op` — engineer correctly identified the BL as already-done (R11)

### 5.6 Sprint close

**5.6.1 `orchestrator.sprint_complete`** fires when the BACKLOG is
exhausted.

**5.6.2 Acceptance Agent (ABL-0014, advisory-only).** If
`run_acceptance=True` (default ON since 2026-05-31 after 3 clean
calibration smokes), the orchestrator forks a detached worktree off
`agent_branch`, spawns the acceptance agent there, and lets it exercise
end-to-end user journeys against the *assembled* feature with seeded
multi-user state. Read-only on code. Outputs land at
`<target>/_brownfield/features/<slug>/acceptance/` (`journeys.yaml`,
`api_journeys.yaml`, `report.md`, `report.json`, `tests/_acceptance/*.spec.ts`,
`screenshots/`, `fixtures/seed_log.txt`, `fixtures/api_logs/`) and are
copied to `traces_archive/<run_id>/acceptance/` at sprint close. R10.1
retry (max 2) applies to the *artifact contract*, not to journey failures
(which are classified, not retried). Hard caps: ≤8 UI journeys × ≤15
steps; ≤20 api_journeys × ≤25 requests. Defensive pre-flight skips with
`acceptance.skipped reason=gate_stack_still_up` if a regression-gate
docker stack survives past `sprint_complete`. **The acceptance pass NEVER
aborts the sprint** — exceptions become `acceptance.error` events;
doctrine_meta + closure_check still run. Full design in
`ABL-0014_ACCEPTANCE_AGENT_IMPLEMENTATION.md`; closes A46 (per-BL
isolation prevents cross-component bug recovery; BL-0007 REQ-0502 worked
example).

**5.6.2.1 API Acceptance (Item 1, Batches A+B, 2026-06-01).** The agent
exercises *every merged backend BL* via API journeys, not just whatever
the UI can reach. The orchestrator computes the backend-BL list by
walking `target_ref..agent_branch` commits and matching touched paths
against `RepoConfig.api_route_globs` (defaults cover FastAPI/Flask;
overridable per-target in `.agentic-skills.json`). Each backend BL must
have ≥1 `api_journey` with a matching `backend_bl:` field; the validator
fails the run (triggering R10.1) on coverage gaps. Each api_journey is a
list of HTTP requests against the seeded gate stack as a portal-
authenticated client, with `method`, `path`, `auth_actor`,
`assert_status` (int or `[int, int]`), and optional `body` /
`assert_json` (jq-style). Failures are classified with the same taxonomy
as UI journeys (`product_bug | test_bug | data_bug | infra_bug |
uncertain`). Request/response logs land under
`fixtures/api_logs/<journey_id>.jsonl`. Closes the structural gap where
backend BLs with no UI surface were assured only by per-BL QA — exactly
the assurance ABL-0014 was created to backstop. Operator may pin the BL
list via `POST /run-acceptance` with `backend_bls_override: [...]`.

**5.6.2.2 UI-coverage check (Item 2, Batch C, 2026-06-01).** Just
before `sprint_complete`, the orchestrator emits
`orchestrator.coverage_check` with the breakdown
`{merged_total, ui_bls, backend_only, ratio, threshold, subtype}`.
`sprint_complete` then carries `coverage_subtype: full | partial` and
`ui_coverage_ratio`. The threshold comes from `RunBriefRequest`'s
`min_ui_coverage_ratio` (default `0.0` = informational-only — subtype is
always `full`); when an operator sets a positive floor and the actual
ratio falls short, subtype is `partial`. **Terminal status is never
flipped** — the framework already merged the BLs; partial is purely an
operator-visibility UX signal that the assembled product may not be
reachable from the user seat. `ui_globs` are repo-configurable
(defaults: `**/*.tsx,jsx,vue,svelte`, `frontend/**/*`, etc.).

**5.6.3 doctrine_meta-agent.** The orchestrator spawns the
self-hardening role. It reads the sealed trace archive
(`traces_archive/<run_id>/`) and writes proposals to
`.planning/doctrine_proposals/<run_id>-<topic>.md`. Operator approval is
the only path to landed doctrine change. A43's "Evidence Discipline"
section in the meta-agent SKILLS.md forbids absence-claims without
per-tool per-record citations.

**5.6.4 `closure_check`** asserts the I-3 postconditions: no orphaned
worktrees on the target, no agent_branches not yet merged or explicitly
preserved, no docker containers tagged with the `run_id`, no state files
in `.orchestrator-state/live/`. Violations are emitted by class — the
orchestrator does not silently leak.

**5.6.5 Trace archival** moves `traces/<repo>/...` to
`traces_archive/<run_id>/`. The orchestrator state file moves from
`live/` to `done/`. The run is sealed.

---

## 6. The control mechanisms in detail

These are the levers the harness pulls. Each has a one-line definition,
the file that implements it, and the failure mode it prevents.

### 6.1 R-rules — the agent contracts

| Rule | Floor | Enforcement point | Prevents |
|---|---|---|---|
| **R5** | ≥3 grounded retrieval calls before any Write/Edit | streaming (Tier 1.5) + post_validation | Hallucinated code that doesn't match codebase conventions |
| **R5b** | Citations in QA artifacts | post_validation (validator scans artifact) | QA writing tests without inspecting the engineer's commit |
| **R7** | Rubric self-consistency (brownfield-axis ≤2 → Fail) | post_validation (scorer) | "Passing on average" while breaking brownfield principles |
| **R8** | ≤30 `mcp__retrieval__*` calls per role | streaming | Runaway grounding loops that never reach Write |
| **R9** | ≥1 `graph_*` call (graph-grounding) | streaming + post_validation (**A8 gap**) | Pure semantic-search grounding that misses structural patterns |
| **R10** | Up to 2 gate retries with focused prompts | orchestrator | Single-flake gate failures aborting good work |
| **R10.1** | Up to 2 doctrine retries with delta prompts | flow function | Agents who forgot one artifact giving up |
| **R10.2** | Up to 2 re-spawns after subprocess errors | orchestrator | Transient API failures looking like agent failures (A45 candidate) |
| **R11** | No-op short-circuit if work already on agent_branch | engineer flow | Engineer reinventing already-merged code on re-run |
| **R12** | Scorer grounding floor (same as R5 but per-role) | streaming (Tier 1.5) | Scorer grading from memory instead of citing |
| **R13** | No agent-initiated history-rewriting git | streaming (kill on Bash tool_use match) | Agents destroying refs or pushing force, the orchestrator owns refs |
| **R14** | Test design constraints (no `TestClient(app)` without `with`, no Alembic DDL with session-scoped fixture, no timeout opt-outs) | doctrine (QA SKILLS.md) + framework (pytest-timeout) | Gate hangs that look like indefinite test runs (A32 root cause) |

> Each R-rule maps to **one or more enforcement points** and **at least
> one test** (I-2 invariant). New rules don't ship without both.

### 6.2 I-invariants — the structural rules

These govern the harness itself, not the agents:

- **I-1 Resource lifecycle** — every subprocess registers cleanup on
  every exit path. Implemented via pgroup kill (B1) and closure_check.
- **I-2 Doctrine contract** — every R-rule maps to an enforcement point
  + a test. (8 known I-2 gaps in DESIGN_SHORTCOMINGS — this is the next
  systematic tightening target per Batch E.)
- **I-3 Closure postconditions** — at termination, assert no orphaned
  worktrees, branches, containers, state files. Implemented in
  `closure_check.py`.
- **I-4 Run identity** — one `run_id`, minted once in the router,
  threaded through every artifact (trace meta, events.jsonl, state
  file, archival path).
- **I-5 Failure observability** — every failure produces a sealed,
  citable artifact (trace dir + events.jsonl line).
- **I-6 Failure taxonomy** — 10 classes (race, resource-leak,
  silent-failure, silent-success, consistency-violation,
  enforcement-gap, starvation, data-loss, observability-gap,
  scope-creep). >3 instances of one class triggers structural review.
- **I-7 Self-hardening** — the doctrine-meta-agent proposes; the
  operator approves; the framework-reviewer adversarially challenges
  (Batch C, not yet built). No auto-merge of doctrine changes.

### 6.3 Validators

`doctrine_validator.py` has one entrypoint per role:

- `validate_po(feature_dir, bl_ids) → {kind, missing[], dangling_refs[], summary}`
- `validate_engineer(feature_dir, bl_id, agent_branch) → {kind, missing[], …}`
- `validate_qa(feature_dir, bl_id, agent_branch) → {kind, missing[], …}`
- `validate_scorer(feature_dir, bl_id) → {kind, missing[], …}`

Each returns a structured result the orchestrator branches on. The
`missing[]` field is what `build_fix_prompt` consumes to produce the
focused retry prompt — the contract is explicit and machine-readable.

### 6.4 The gate

`regression_gate.run_gate(agent_branch, target_ref, test_cmd) → GateResult`

Two disposable docker stacks (PRE, POST) per call. Each runs the
target's `test_cmd` (default: `sh scripts/regression_gate.sh`). The
parser classifies:

- **green** — POST passes, no new failures vs PRE
- **regressed** — POST has new failures vs PRE; `regressions[]` lists
  them
- **inconclusive** — PRE itself failed (the baseline is broken before
  the engineer touched anything)
- **error** — gate infrastructure failed (docker, network, etc.)
- **skipped** — non-brownfield runs

The gate IS the durability test. If the brownfield rubric's "Regression
Coverage" axis is the doctrine-level expression, the gate is its
operational implementation.

### 6.5 Retries

Three independent retry budgets. Each maps to a distinct class of
failure:

| Budget | Trigger | Retry shape | Limit |
|---|---|---|---|
| **R10.1** | Doctrine `incomplete` (artifacts missing or under-cited) | Same worktree, focused fix prompt naming exact missing paths | 2 |
| **R10** | Gate `regressed` | Same worktree, focused prompt naming exact failing tests + post_tail | 2 |
| **R10.2** | Subprocess error / exit non-zero / API error (A45-class) | Fresh worktree, same prompt | 2 |

These compose. A BL can use all three. After all three exhaust → `give_up`
→ `stop_on_failure=true` → `orchestrator.aborted`.

### 6.6 Tier 1.5 streaming kills

Implemented in `claude_agent.py`'s line-by-line stream parser. Before
the host harness writes any tool_use back to the subprocess, it
inspects:

- Bash invocations against a `FORBIDDEN_GIT_RE` regex (R13)
- `Write`/`Edit` tool_uses before R5 grounding count reached
- `mcp__retrieval__*` count exceeding R8 budget

If any matches, the host kills the subprocess group with SIGTERM and
emits a distinct `_meta phase=...` event (`pregrounding_violated`,
`tier_15_forbidden_git`, etc.) so the failure is honest.

Tier 1.5 exists because post-validation alone has a cycle-cost problem:
the LLM might run for 10 minutes producing work, then post-validation
rejects it. Tier 1.5 catches it the moment the violation is observable
in the output stream — usually within seconds.

### 6.7 Worktree isolation

Every role spawn runs in its own `git worktree`. This means:

- Concurrent BLs (when we eventually run them) can't collide.
- An agent can't read another agent's in-flight commits.
- The canonical checkout (where the operator might be looking) is never
  in a half-built state.
- Cleanup is `git worktree remove`, which is atomic.

### 6.8 Doctrine-meta self-hardening

Runs once per sprint at sprint_complete. Reads the sealed trace
archive (every per-agent stream.jsonl, phase_events.jsonl, retrieval.jsonl,
meta.json) and proposes:

- Tightening an existing R-rule that fired too often or too late
- Loosening a rule that fired on cases it shouldn't have
- A new rule for a class of failure no existing rule catches
- A new invariant if no I- entry covers the finding

It writes proposals; it never merges. Operator approves.

**A43's Evidence Discipline rule** in the meta-agent SKILLS.md was a
direct lesson from a false-evidence proposal: any absence-claim ("tool T
does not log field X") now requires ≥3 per-tool per-record citations,
not aggregate counts.

---

## 7. Artifacts and where they live

```
agentic-skills/                              # this repo
├── webapp/backend/
│   ├── app/
│   │   ├── routers/projects.py              # HTTP/SSE entrypoints
│   │   ├── services/*.py                    # host harness modules
│   │   ├── templates/                       # target harness templates
│   │   │   ├── regression_gate.sh
│   │   │   └── compose.gate.yml
│   │   └── ...
│   ├── traces/<repo>/<ts>-<role>-<bl>-<task_id>/
│   │   ├── stream.jsonl                     # full SSE event stream
│   │   ├── phase_events.jsonl               # _meta-only filter
│   │   ├── retrieval.jsonl                  # every mcp__retrieval__ call
│   │   └── meta.json                        # task_id, role, harness_sha, prompt
│   ├── traces_archive/<run_id>/             # sealed traces after sprint_complete
│   ├── .orchestrator-state/
│   │   ├── live/<run_id>.json               # live sprint state
│   │   └── done/<run_id>.json               # archived after termination
│   ├── logs/orchestrator/<ts>/              # orchestrator stdout/stderr
│   └── repos/<repo>                         # symlink → target

<target-repo>/                               # outside agentic-skills
├── .agentic-skills.json                     # target harness config
├── scripts/regression_gate.sh               # target harness gate runner
├── compose.gate.yml                         # target harness compose overlay
├── .gitignore                               # +graphify-out, +events.jsonl
├── _brownfield/features/<slug>/             # per-feature artifact tree
│   ├── brief.md
│   ├── sprint_briefs/<run_id>-<slug>.md
│   ├── _codebase_context/CODEBASE_CONTEXT.md
│   ├── BACKLOG.md
│   ├── SPRINT_PLAN_C1.md
│   ├── BL-0001/
│   │   ├── codebase_context.md              # PO output
│   │   ├── eng_patterns.md                  # engineer output
│   │   └── qa_impact.md                     # QA output
│   └── events.jsonl                         # the truth log
└── graphify-out → ~/.cache/agentic-skills/graphify/<sha>/  # gitignored symlink

.planning/                                   # operator-local
├── doctrine_proposals/
│   ├── <run_id>-<topic>.md                  # meta-agent output
│   ├── accepted/
│   └── rejected/
└── ...
```

---

## 8. A worked example: one BL through the loop

Take BL-0003 from the `time-tracking` sprint: *Manual time-entry UI.*

| t (mm:ss) | Event | What the harness did |
|---|---|---|
| 0:00 | `orchestrator.bl.start BL-0003` | Picked the next BL from BACKLOG |
| 0:00 | `orchestrator.engineer.start BL-0003` | About to spawn |
| 0:02 | `worktree_ready bl=BL-0003 task_id=e756aec…` | `git_worktree.create_worktree` forked `agent/e756aec…` off `agent_branch` |
| 0:02 | `spawn cmd=[claude, --print, …]` | `claude_agent.stream_agent_task` launched the subprocess with engineer SKILLS.md + BL-0003 codebase_context.md |
| 0:02 → 12:14 | (streaming output) | Engineer made 4 retrieval calls (semantic_search × 2, graph_summary, graph_neighbors), Tier 1.5 confirmed grounded, then Wrote 15 files |
| 12:14 | `exit exit_code=0 duration_s=731.4` | Subprocess returned a clean JSON `{status:complete, commit_sha:e756aec, files_changed:15}` |
| 12:14 | `doctrine_check kind=complete attempt=1` | `validate_engineer` found `eng_patterns.md` with 4 retrieval citations + 15 source files changed → complete first try |
| 12:14 → 18:09 | `regression_gate kind=green reason="post suite green (251 passed)"` | `regression_gate.run_gate` spun up PRE+POST docker stacks, ran `sh scripts/regression_gate.sh` twice; diff was clean |
| 18:09 | `merge_to_target kind=ff` | `git_worktree.fast_forward_target` cleaned untracked `graphify-out` (A35) and `git merge --ff-only` succeeded |
| 18:09 | `orchestrator.engineer.done bl=BL-0003 merged=true` | Engineer phase closed |
| 18:09 → 21:33 | reindex_after_engineer | graphify + claude-context incremental |
| 21:33 | `orchestrator.qa.start BL-0003` | Spawned QA in its own worktree |
| 21:33 → 26:48 | (streaming) | QA wrote `qa_impact.md` + a new `frontend/tests/time.spec.ts` with 10 playwright tests |
| 26:48 | `doctrine_check kind=complete attempt=1` | `validate_qa` found citations + test file |
| 26:48 → 31:12 | `regression_gate kind=green reason="post suite green (251 passed)"` | QA's added tests passed, no regressions on existing tests |
| 31:12 | `merge_to_target kind=ff` | Merged |
| 31:12 → 33:01 | reindex_after_qa | |
| 33:01 → 36:14 | scorer | Doctrine retry once (forgot to write `.agile-v/scorecards/BL-0003.md`), passed retry, brownfield axes all ≥3 |
| 36:14 | `orchestrator.bl.done BL-0003 outcome=merged_full` | Ready for BL-0004 |

The harness facets visible in this trace:
- **Worktree isolation** (4 worktree forks across phases)
- **Subprocess streaming** (driving the LLM through tool_use cycles)
- **R5 grounding** (counted, satisfied first try)
- **R10.1 doctrine retry** (scorer used 1)
- **Gate** (4 docker stacks total: engineer PRE+POST, QA PRE+POST)
- **A35 pre-merge cleanup** (graphify-out stripped before each merge)
- **Trace writing** (4 sealed trace dirs produced)
- **Event emission** (every transition emitted to events.jsonl AND
  streamed to the operator's browser AND written to disk state)

---

## 9. Failure modes and what they taught the harness

Each A-numbered finding in `DESIGN_SHORTCOMINGS.md` is a lesson the
harness internalized. Selected:

| Finding | Lesson | Harness change |
|---|---|---|
| A1 | Operator commit on agent_branch while engineer was working → non-FF | `fast_forward_target` now auto-rebases on non-FF and re-runs the gate |
| A2 | QA doctrine give-up was silent and falsely marked the BL "merged" | `qa_doctrine_failed` event + `bl.done outcome=merged_no_qa` |
| A7 | Orchestrator state lived only in memory; crash-restart impossible | Disk-persisted state under `.orchestrator-state/{live,done}/` |
| A34 | SSE client disconnect killed the orchestrator | (Open) Decouple run from response — orchestrator should be a background task, SSE a consumer |
| A35 | Untracked `graphify-out` symlink blocked FF-merge mid-sprint | Pre-merge cleanup in `fast_forward_target` + `.gitignore` belt-and-suspenders |
| A36 | PO satisfied R5 by retrieval count but missed migration layer → engineer wrote SQLModel without matching `op.create_table` name | PO prompt requires layer-coverage; engineer prompt names tablename rule; pre-merge tablename validator |
| A37 | QA merge errored but orchestrator advanced to scorer silently | `qa_merge_failed` event + abort under `stop_on_failure=true` |
| A40 | Engineer manually re-wrote import statements when biome had `--apply` | Engineer prompt explicitly directs use of formatter `--fix` |
| A43 | Meta-agent's first novel proposal had false absence-claims with aggregate evidence | Evidence Discipline section: schema-uniformity-assumption forbidden, ≥3 per-tool per-record citations required for any absence-claim |
| A44 | Asyncio's 64 KiB readline buffer killed engineer on Read of large files | `STREAM_READER_LIMIT = 64 MiB` passed to `create_subprocess_exec`, distinct `phase=stream_overrun` event |

The pattern: **every silent failure becomes a named event; every named
event maps to a validator or a kill rule; every validator/kill rule maps
to a test**. The harness gets honest by design.

---

## 10. Harness engineering — principles

If you're building your own harness around LLM agents, these are the
durable lessons we've extracted, in priority order:

### 10.1 The harness owns refs. Always.

Agents must never push, rebase, reset, force, amend, or tag. They write
code, the harness writes refs. R13 enforces this via streaming-side
kills on forbidden Bash patterns. Without this rule, agents WILL
eventually destroy branches "trying to be helpful."

### 10.2 Every rule maps to one enforcement point + one test.

"R5 requires ≥3 grounded calls" isn't enforced — it's documented. The
enforcement is `claude_agent.py:_count_retrieval_calls`. The test is
`tests/test_r5_pregrounding.py`. The doctrine string and the code and
the test land in the same commit or not at all. This is I-2.

### 10.3 Validators name what's missing in machine-readable form.

A validator that says "the artifact is incomplete" is useless. A
validator that returns
`{kind:"incomplete", missing:["_brownfield/.../eng_patterns.md"]}` is
the contract. The orchestrator turns the `missing[]` list into a
focused fix prompt. The agent gets one more chance focused on the gap.

### 10.4 Tier 1.5 catches what post-validation would also catch — but
   minutes earlier.

Watch the stream. Kill on observable violation. Don't let the LLM
produce 10 minutes of work you're going to throw away.

### 10.5 Retries are budget-bounded, distinct by class.

Doctrine retries, gate retries, and subprocess-error retries are
separate budgets. They compose; each maps to a different kind of
failure. After all exhaust → abort. **Indefinite retry loops are not
retry — they're hope.**

### 10.6 The honest-failure event is more valuable than the
   optimistic-success event.

A37, A2, A35 — every one was an instance of the harness silently turning
a failure into a success. The harness's most important property is that
it cannot lie about what happened. Sealed traces + named events + closure
postconditions ensure this structurally.

### 10.7 The host/target split is real architecture, not cosmetics.

Code in the host harness affects ALL future runs. Code in the target
harness affects ONE branch. Make the split explicit. Use templates +
init endpoints so target-harness bugs propagate by re-init, not by
mass-cherry-pick.

### 10.8 Worktree isolation is free; collision recovery is not.

Every agent runs in its own `git worktree add`. Branches are cheap.
Worktrees are cheap. Concurrent or sequential, the model is the same.

### 10.9 The harness can become honest about its own limits.

The doctrine-meta-agent reads the harness's own trace archive and
proposes hardening. The operator approves. The framework-reviewer (when
built) adversarially challenges. **The crew's self-hardening loop is
itself harness engineering.**

### 10.10 No silent advancement past a failure.

If a phase failed and the harness can't be sure the state is recoverable,
abort. `stop_on_failure=true` is the default. Operator can override on a
specific BL after triage. *Never* the framework's choice.

---

## 11. Trust model (A52 / A47 — read before pointing the crew at a new target)

Added 2026-08-16 (autonomy-hardening Batch 7-3). The security boundaries
that DO and DO NOT exist:

1. **Target-repo content is untrusted input.** Retrieval chunks, file
   reads, and test output from the brownfield target all flow into agent
   prompts. A malicious or poisoned target is a prompt-injection vector.
2. **`--allowedTools` is NOT a security boundary.** A47 (4 worked
   examples): built-in CLI tools (`ScheduleWakeup`, `Glob`, …) bypass the
   allowlist silently. Doctrine that names allowed tools is behavioral
   guidance, enforced only where the harness adds a streaming-side check
   (Tier 1.5, R8, R13).
3. **Agents run `--dangerously-skip-permissions` with unrestricted Bash**
   in their worktree. R13 blocks history-rewriting git; nothing blocks
   `curl`, package installs, or arbitrary computation.
4. **The agent env is allowlisted (A52).** Since Batch 7-3, agent
   subprocesses receive only shell basics + git identity + claude auth
   (`HOME`, `CLAUDE_*`, `ANTHROPIC_*`, `AWS_*`, `GOOGLE_*`/`VERTEX_*`) +
   proxy vars. Retrieval secrets (`AZURE_OPENAI_*`, `OPENAI_API_KEY`,
   `MILVUS_*`) reach only the MCP *server* via its own config env, never
   the agent process. Operator knobs: `AGENT_ENV_ALLOWLIST="V1,V2"`
   extends; `AGENT_ENV_PASSTHROUGH_ALL=1` is the emergency full-inherit
   rollback.
5. **What remains open (deferred per operator decision D4):** container-
   jailed Bash, filesystem scoping beyond the worktree, and network
   egress control. Until that track lands, point the crew only at targets
   you trust as much as your own shell.

## 12. Pointers

- `THESIS.md` — the mission and definition-of-done
- `ARCHITECTURE_INVARIANTS.md` — I-1..I-7 in detail
- `DESIGN_SHORTCOMINGS.md` — the complete ledger of observed failures
  and their fixes; every A-number is a harness lesson
- `WORKFLOW.md` — comprehensive ASCII diagram of every gate, guard, and
  event from brief submission through sprint completion
- `RUNBOOK_clean_brownfield_reset.md` — the manual procedure
  `POST /init-feature` automates
- `EVALUATION_2026-05-28.md` — calibrated audit of how much of the
  thesis is delivered (~40%) and what's missing

---

*Authored 2026-05-29 as a teaching document for engineers new to
harness engineering on this project. Update when the host/target
boundary shifts or a new control mechanism lands.*
