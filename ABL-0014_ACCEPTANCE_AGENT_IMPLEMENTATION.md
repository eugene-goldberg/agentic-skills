# ABL-0014 — Acceptance Agent Implementation Plan

> **Numbering note (2026-05-30):** earlier this session and in commits
> `4a5c108` (Batch A) and `f1bdb8b` (Batch B) the Acceptance Agent was
> referenced as "ABL-0010". That ID was already taken by the Meta-rubric
> entry in `BACKLOG.md`. Per operator decision (Option A), the new work
> was renumbered to **ABL-0014** for the Acceptance Agent and **ABL-0015**
> for the deferred auto-dispatch follow-up. Past commit messages still
> say "ABL-0010"; in this codebase "ABL-0010" referenced from anything
> Acceptance-related means ABL-0014. Original ABL-0010 (Meta-rubric) and
> ABL-0011 (Concurrent BL execution) in `BACKLOG.md` keep their numbers.

> Status: **Batches A + B SHIPPED; Batch C in flight**
> Author: Claude (architect role), 2026-05-30
> Source SKILLS.md: [`skills/brownfield/brownfield-acceptance-agent/SKILLS.md`](skills/brownfield/brownfield-acceptance-agent/SKILLS.md)
> Wiring pattern reference: `webapp/backend/app/services/orchestrator.py::_doctrine_meta_flow` (lines 676–783)

This document captures, with ≥95%-confidence-pending-7-open-questions, the
complete set of deliverables required to implement the Acceptance Agent
(ABL-0014) into the agentic-skills harness. It is the authoritative
scoping artifact for that work; do not start coding until the 7 questions
in §E are answered by the operator.

The Acceptance Agent is structurally a **sibling of doctrine-meta**
(one-shot, post-`sprint_complete`, sandboxed outputs, file-based
validator) **and** a **sibling of QA** (runs in a target worktree, boots
the gate docker stack, runs playwright). Both patterns are reused; no new
machinery is invented where existing pattern fits.

---

## A. Code changes — 12 concrete deliverables

| # | Deliverable | Location | Pattern source |
|---|---|---|---|
| 1 | `_load_skill("acceptance")` registration | `webapp/backend/app/services/prompts_brownfield.py` | doctrine_meta entry |
| 2 | `_acceptance_flow(repo_dir, repo_name, run_id, feature_slug, agent_branch, timeout)` async generator | `webapp/backend/app/services/orchestrator.py` | `_doctrine_meta_flow` lines 676–783 |
| 3 | Wire into `run_brief` between the `sprint_complete` yield and the `_doctrine_meta_flow` block (~line 1092) | `webapp/backend/app/services/orchestrator.py` | existing `if run_doctrine_meta:` block |
| 4 | `run_acceptance: bool = True` parameter on `run_brief` + matching field on `RunBriefRequest` Pydantic model | `orchestrator.py`, router | `run_doctrine_meta` plumbing |
| 5 | Detached worktree off `agent_branch` (read-only intent, no commit), with `finally` cleanup registered with closure_check | uses `git_worktree.create_worktree` | QA flow pattern |
| 6 | `acceptance_validator.py` — schema-checks `journeys.yaml`, asserts every step has an on-disk screenshot, validates `report.json` outcome/classification enums, returns machine-readable missing-artifact list | new `webapp/backend/app/services/acceptance_validator.py` | `doctrine_validator.py` |
| 7 | R10.1-style doctrine retry (max 2) on validator-missing artifacts; **no retry on journey failures** | inside `_acceptance_flow` | engineer/QA flow |
| 8 | Archive copy: `<target>/_brownfield/features/<slug>/acceptance/` → `webapp/backend/traces_archive/<run_id>/acceptance/` | inside `_acceptance_flow` finally | B15 archival |
| 9 | Docker stack tagging: `COMPOSE_PROJECT_NAME=acceptance-<run_id>` so `closure_check` enumerates it on leak | prompt instruction + closure_check scan extension | I-3 |
| 10 | `allowed_tools = "Bash,Read,Write,Edit"` + retrieval MCP tools | `stream_agent_task` call | QA flow |
| 11 | Events emitted: `acceptance.start`, `acceptance.validator.{ok,incomplete,give_up}`, `acceptance.done` (with `journeys_planned/passed/failed/unshippable`, `report_path`, `screenshots_dir`) | inside flow | doctrine_meta event vocabulary |
| 12 | Frontend: checkbox in run-brief form + run-viewer event filter + summary tile linking to `report.md` and screenshots gallery | `webapp/frontend/src/...` | existing `closure_check` UI surface |

---

## B. Tests (matching project convention)

- **`test_acceptance_flow.py`** — fakes `stream_agent_task`; verifies:
  - skip when `brief.md` missing → `acceptance.skipped` event
  - event order: `start → validator.* → done`
  - archive copy lands at `traces_archive/<run_id>/acceptance/`
  - error path emits `acceptance.error` and does NOT abort `closure_check`
- **`test_acceptance_validator.py`** — golden valid fixture + 5 specific invalid fixtures:
  - missing screenshot file referenced by a step
  - malformed `journeys.yaml` (schema violation)
  - invalid classification enum in `report.json`
  - missing `report.json` entirely
  - journey with zero steps
- **`test_run_brief_acceptance_wiring.py`**:
  - `run_acceptance=False` short-circuits cleanly (no flow invocation)
  - `run_acceptance=True` triggers `_acceptance_flow`
  - exception in flow yields `acceptance.error` and does NOT abort `closure_check`
- **`test_closure_check_acceptance_stack.py`**:
  - `closure_check` enumerates `acceptance-<run_id>` containers
  - reports leaks under `by_kind["acceptance_docker"]`

---

## C. Documentation updates

- **`HARNESS.md`** — extend 5-layer model + flow diagram to include the
  acceptance pass; add Acceptance Agent to agent-contracts section
- **`WORKFLOW.md`** — extend state machine: `sprint_complete → acceptance → doctrine_meta → closure_check`
- **`CLAUDE.md`** — add to governance docs table; add to R-rules table if
  new R-rules emerge (candidate R15: "every acceptance claim has a
  re-openable artifact path")
- **`DESIGN_SHORTCOMINGS.md`** — file the deferred A4x "per-BL isolation
  prevents cross-component bug recovery" with ABL-0014 as resolution and
  the BL-0007 REQ-0502 worked example as motivating evidence
- **`BACKLOG.md`** — ABL-0014 status → in-progress
- **`ARCHITECT_PLAN.md` / `ARCHITECT_TRACKER.md`** — add ABL-0014 batch
  containing the 12 deliverables above
- **`.claude/memory/arch_acceptance_agent.md`** — flip status from
  "proposed" to "implementing"

---

## D. Architecture-invariant compliance checklist

Each must be explicitly satisfied before the work ships, or I regress an
invariant:

- **I-1 (resource lifecycle)** — worktree + docker stack registered on
  spawn, cleaned on every exit path (success, failure, timeout, SIGTERM)
- **I-2 (doctrine contract)** — every new R-rule lands with its
  enforcement point + a callable check, in the same change
- **I-3 (closure postconditions)** — `closure_check` sees
  acceptance-tagged docker containers AND acceptance worktrees; reports
  leaks under specific `by_kind` keys
- **I-4 (run identity)** — `run_id` is threaded into `acceptance-<run_id>`
  stack name, trace dir, archive path, every event
- **I-6 (failure taxonomy)** — acceptance failure modes integrated with
  ledger taxonomy; `product_bug/test_bug/data_bug/infra_bug/uncertain`
  classes are explicit, machine-readable enum values
- **I-7 (self-hardening)** — acceptance failures become doctrine-meta
  evidence: the meta-agent reads `acceptance/report.json` the same way it
  reads engineer/QA traces

---

## E. Open questions blocking ≥95% confidence (need operator answers before coding)

1. **Worktree base** — detached off merged `agent_branch` (recommend —
   matches I-1/I-3 isolation), or run directly in a checkout of
   `agent_branch`?
2. **Timeout** — `doctrine_meta` uses 2400s. Acceptance + playwright +
   docker boot is heavier. Propose 3600s default — confirm?
3. **Failure semantics** — do failing journeys *block* `sprint_complete`
   downstream effects, or are they always advisory? SKILLS.md implies
   advisory — confirm.
4. **Cost cap** — max journeys per sprint (suggest 8) and max steps per
   journey (suggest 15) enforced via prompt? Without caps, an over-eager
   agent could burn an hour of playwright runs.
5. **Auto-dispatch on `product_bug`** — report-only v1, or also spawn a
   follow-up engineer to attempt a fix? Recommend report-only;
   auto-dispatch becomes ABL-0015.
6. **Default on/off** — `run_acceptance=True` by default from day one, or
   default `False` until 2–3 smoke runs prove the agent doesn't waste
   operator time?
7. **Concurrent regression-gate collision** — acceptance runs *after*
   `sprint_complete` so the regression gate should be down, but should we
   add a defensive port-collision check + skip-with-warning if a gate
   stack is still up?

Answers to these 7 produce a fully-scoped implementation plan. Until
then, do not start coding deliverable 1.

### E.1 Architect's recommended answers (pending operator confirmation)

1. **Worktree base** → **detached worktree off `agent_branch`.** Matches
   I-1/I-3 isolation; closure_check already enumerates worktrees by
   run_id; aligns with QA's pattern. Direct checkout saves ~2s of setup
   and costs us an invariant.
2. **Timeout** → **3600s (1h) default, configurable per-call.** Doctrine-
   meta at 2400s is pure Read; acceptance is docker boot (~60s) + seed
   (~30s) + N journeys × ~3min playwright each. With Q4 caps (8×15)
   runtime is ~24 min + setup + retry headroom. Expose as
   `acceptance_timeout: int = 3600` on `run_brief`.
3. **Failure semantics** → **advisory, never blocking.** (a) acceptance
   is reporting per its mantra; (b) blocking couples a soft signal to
   hard merge gating; (c) doctrine-meta + closure_check MUST run even on
   acceptance failure. Wire `acceptance.done` as a yielded event only;
   never set `terminal_status="aborted"` from this flow.
4. **Cost cap** → **8 journeys × 15 steps, two-layer enforcement.**
   Layer 1: SKILLS.md adds "MAXIMUM 8 journeys; prioritize cross-actor
   handoffs, report discarded as `journeys_deferred`." Layer 2:
   `acceptance_validator.py` hard-rejects > 8 journeys or any journey
   with > 15 steps. Two-layer matches I-2 pattern (rule + check land
   together).
5. **Auto-dispatch on `product_bug`** → **report-only v1.** Auto-dispatch
   crosses two new invariant boundaries (acceptance becomes a writer;
   engineer gets a non-PO-decomposed BL). File as **ABL-0015** with
   ABL-0014 as prerequisite. Ship the smaller surface, learn from real
   sprint evidence, then design ABL-0015 against that evidence.
6. **Default on/off** → **`run_acceptance=False` for first 3 sprints,
   then flip to True.** The agent is unproven. Three explicit opt-in
   smoke runs give calibration data (proposal accuracy, runtime, FP
   rate). After 3 clean runs, flip the default. Encode the flip date as
   a TODO comment in `run_brief` referencing this doc.
7. **Concurrent regression-gate collision** → **defensive pre-flight
   check, skip-with-warning on collision.** Add 2-line pre-flight:
   `docker ps --filter "name=gate-<run_id>" --format "{{.Names}}"` — if
   non-empty, emit `acceptance.skipped reason=gate_stack_still_up` and
   exit cleanly. A non-empty result is itself a closure_check violation
   worth investigating.

These are the architect's recommendations. Operator may override any of
them; once confirmed, this section becomes the locked contract Batches
A–C build against.

---

## F. Sequencing recommendation (once §E is unblocked)

Three batches, each independently mergeable:

**Batch A — Skill loader + validator + flow skeleton (no UI)**
Deliverables 1, 2, 6 + tests B.1 + B.2. Flow returns without spawning the
agent; just validates the contract. Lets us land the plumbing safely.

**Batch B — Wire + spawn + archive (still no UI)**
Deliverables 3, 4, 5, 7, 8, 9, 10, 11 + tests B.3 + B.4. End-to-end
smoke-runnable from curl. This is where the structural risk lives.

**Batch C — Frontend + docs + ledger**
Deliverable 12 + all of §C. Operator-visible delivery.

Each batch ends with an explicit operator approval gate before the next
starts. No invariant-touching change auto-promotes.

---

*Last updated 2026-05-30. Captured verbatim from architect analysis
delivered in-session. Replaces ad-hoc chat scoping with a durable
artifact the operator can review, comment on, and grant batch-level
approval against.*

---

## G. Item 1 — API Acceptance (added 2026-06-01)

Motivated by `run-20260601T032339Z-dd81c5` (Client_Portal): the
acceptance agent honestly flagged 4 backend BLs (BL-0006/0007/0008/0009)
as `capability_gaps` because none had reachable UI, but could not
*exercise* their backends. Their only assurance was per-BL QA — exactly
what ABL-0014 was created to backstop. Item 1 closes that gap.

### G.1 Contract additions

- Every merged BL whose commit touched a path matching the target's
  `api_route_globs` MUST have ≥1 entry in `api_journeys.yaml` with a
  matching `backend_bl:` field. Validator enforces.
- Each api_journey is a list of HTTP requests against the seeded
  acceptance compose stack as a portal-authenticated client.
- Request schema: `{method, path, auth_actor, assert_status}` + optional
  `body`, `assert_json`.
- Cost caps: `MAX_API_JOURNEYS=20`, `MAX_REQUESTS_PER_API_JOURNEY=25`.
- Failures classified with same taxonomy as UI journeys; logs land at
  `fixtures/api_logs/<journey_id>.jsonl`; per-journey outcome added to
  `report.json` under `api_journeys: [...]`.

### G.2 Sequencing (shipped)

**Batch A — Validator + SKILLS.md (gated, dormant)** — commit `2282c69`.
Validator accepts `backend_bls=None` (no-op) or a list (coverage
asserted). SKILLS.md "API Acceptance" section documents the contract.
12 new tests. Backward-compatible; production behavior unchanged.

**Batch B — Orchestrator wiring (live)** — commit `3cc52ca`. New
`_compute_backend_bls` helper walks `target_ref..agent_branch`, matches
each BL commit against `RepoConfig.api_route_globs`, returns
`(bls, evidence)`. `_acceptance_flow` computes on entry, threads through
`_build_acceptance_task` (new "API Acceptance — REQUIRED" prompt block
naming each BL + cited route files) and `validate_acceptance`.
`RunAcceptanceRequest.backend_bls_override` lets operator pin scope.
Both `acceptance.start` and `acceptance.done` events carry
`backend_bls`. 9 new tests. **Proof point in flight against
Client_Portal: should compute BL-0001..BL-0009 (BL-0010 = frontend
shell, excluded).**

### G.3 Locked operator decisions

- **G.3.1 Glob source**: defaults in `repo_config.DEFAULT_API_ROUTE_GLOBS`
  (FastAPI/Flask shaped); overridable per-target via `api_route_globs`
  key in `.agentic-skills.json`. Targets that diverge (Django,
  Rails, Next.js routes) override; no code change required.
- **G.3.2 Test exclusion**: paths under `/tests/` (or starting with
  `tests/`) never count toward backend coverage — exercising shipped
  behavior is the intent, not re-running QA tests.
- **G.3.3 Evidence cap**: ≤5 cited route files per BL in the prompt for
  readability; full diff available via the agent's own `git show`.
- **G.3.4 Multi-commit dedup**: a BL with multiple commits appears once;
  evidence merged across commits. Subject must start with `BL-NNNN`
  (the `fix(BL-XXXX):` form is intentionally excluded — keeps the
  scan deterministic).
- **G.3.5 Auth model**: api_journeys reuse the seeded identities from
  `fixtures/seed.py`; tokens minted via the real login route and
  stashed in `seed_log.txt` so journeys can resolve `auth_actor` at
  run time. No hard-coded tokens; no token sharing across actors.

---

## H. Item 2 — UI-coverage check (added 2026-06-01)

Operator-visibility complement to Item 1: even after Item 1 closes the
assurance gap, the operator needs a signal when "everything merged" but
"nothing reaches the user." Client_Portal had ratio = 1/10 = 0.1.

### H.1 Contract additions

- New `orchestrator.coverage_check` event between `bl.done` (last BL)
  and `sprint_complete`. Payload:
  `{merged_total, ui_bls, backend_only, ratio, threshold, subtype}`.
- `sprint_complete` extended with `coverage_subtype` (`full`|`partial`),
  `ui_coverage_ratio`, `ui_coverage_threshold`.
- New `RunBriefRequest.min_ui_coverage_ratio: float = 0.0`. When 0.0,
  subtype is always `full` (informational-only). When > 0.0 and the
  actual ratio falls below, subtype is `partial`.
- **`terminal_status` is never flipped** — sprint still completes; the
  partial flag is purely operator-visibility UX.
- `ui_globs` repo-configurable via `RepoConfig.ui_globs`; defaults
  cover React/Vue/Svelte plus frontend/web/ui top-level dirs.

### H.2 Sequencing (shipped)

**Batch C — Orchestrator + plumbing** — commit `25a8d33`.
`_compute_ui_coverage` parallel to backend version; emission wired
before `sprint_complete`; `RunBriefRequest.min_ui_coverage_ratio`
threaded; 7 new tests including reproduction of Client_Portal ratio.

**Batch D — Frontend + docs + memory** — current commit. AppV2
gains a Coverage tile rendering subtype + ratio + threshold +
backend-only BL list; existing Acceptance tile gains a `backend_bls`
line. New input control for `min_ui_coverage_ratio` (default "0.0").
HARNESS.md §5.6.2 split into §5.6.2.1 (API Acceptance) + §5.6.2.2 (UI
coverage). `arch_acceptance_agent.md` memory rewritten.

### H.3 Locked operator decisions

- **H.3.1 Subtype over terminal_status flip**: rejected the
  `terminal_status="partial_complete"` design because it forces every
  downstream consumer (UI renderers, doctrine-meta-agent inputs,
  closure_check trigger) to handle a new value. Subtype on the same
  event is cheaper, equally visible.
- **H.3.2 Default 0.0**: matches ABL-0014's original 3-smoke
  calibration discipline. Operator opts in after watching a few
  sprints' actual ratios.
- **H.3.3 Future tighter mode**: a `hard_gate_on_partial` flag could
  flip `terminal_status` when paired with a positive threshold. Defer
  until calibrated.
- **H.3.4 Full-stack BL counted as UI**: a BL whose commit touches BOTH
  backend AND frontend files counts as UI-covered (it has reachable
  surface). Backend-only is the residual.
- **H.3.5 UI test files don't count**: parallel to Item 1's test
  exclusion — `frontend/tests/*.spec.tsx` does NOT count toward UI
  surface.

---

*Items 1 + 2 raise ABL-0014 from "OPERATIONAL on UI surfaces" to
"fully functional for sprints with arbitrary UI/backend mix." Three
calibration smokes against backend-heavy sprints remain before the
new Item 1 default is "operational" with the same confidence as the
2026-05-31 UI-only flip.*
