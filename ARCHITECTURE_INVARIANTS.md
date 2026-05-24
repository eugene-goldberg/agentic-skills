# Agentic Skills — Architecture Invariants

> Seven structural rules the entire orchestrator must satisfy. Each existing
> A/B shortcoming back-maps to one of these. Future shortcomings should be
> tagged with the violated invariant before a patch is proposed.
>
> **The point:** stop catching bugs one at a time. Audit each component
> against each invariant; empty cells are where the next failure lives.
>
> *Authored 2026-05-23 after Sprint 4 surfaced A8 + A9-candidate (sibling-
> class violations of B1). Companion: `DESIGN_SHORTCOMINGS.md` (instances),
> `IMPLEMENTATION_PLAN.md` (Sprint-3 hardening), `WORKFLOW.md` (visual map).*

---

## How to use this document

1. **Before opening a new ledger entry**, classify the failure under one of
   the seven invariants. If it doesn't fit, the taxonomy needs a new entry —
   surface that first.
2. **Before approving an invariant-violating patch**, ask whether a sibling
   site violates the same invariant. (B1 covered claude; A9 covered gate
   because nobody asked.)
3. **The doctrine-meta agent (ABL-0003)** uses this list to classify its
   own findings. Patches that don't map to an invariant get flagged.

---

## Invariant I-1 — Resource lifecycle is owned end-to-end

> Every external resource the orchestrator brings into being must register
> a cleanup hook reached on every exit path (success, abort, exception,
> consumer-disconnect, kill -9 → restart).

### Resources in scope

| Resource | Created by | Cleanup hook today | Compliant? |
|---|---|---|---|
| Agent subprocess (claude tree) | `claude_agent.stream_agent_task` | `_kill_pgroup` in inner+outer finally (B1) | ✓ |
| Gate subprocess (`regression_gate.sh` + docker compose) | `regression_gate_svc.run_gate` | local `proc.kill()` only; no pgroup; **30h orphan observed in Sprint 4** | ✗ (A9 candidate) |
| Graphify subprocess | `indexing.run_graphify_update` | none beyond default | ✗ (no observed leak yet) |
| Claude-context bridge (Node) | `indexing.run_claude_context_index` | none beyond default | ✗ (no observed leak) |
| Agent worktree | `git_worktree.create_worktree` | `remove_worktree` in finally | ✓ (most paths) |
| Gate worktrees (`.gate-worktrees/pre-/post-`) | `regression_gate_svc.run_gate` | local cleanup only; orphans observed | ⚠ |
| Trace dir + retrieval log | `traces.TraceWriter` | `trace.close()` in finally; B15 archives | ✓ |
| MCP config tmp file | `claude_agent._build_retrieval_mcp_config` | outer finally `mcp_config_path.unlink()` | ✓ |
| Disk state file | `run_state.write_checkpoint` | `mark_terminated` in finally | ✓ |
| Async lock (B2) | `_get_run_lock` | `lock.release()` in `gen()` finally | ✓ |

### Back-mapped shortcomings

- **B1** (claude pgroup-kill) — fixed for one resource class only.
- **A9 candidate** (gate subprocess pgroup-kill) — same class, different resource.
- **B3** (graphify cache pollution) — adjacent: a write that escaped its
  intended location. The fix made the write safe, not the cleanup.
- **R13** (agent-initiated git history rewriting) — surfaced api-keys sprint;
  scope-creep/silent-failure pair. Agents reach across the boundary and
  mutate refs the orchestrator owns. R13 is the streaming-kill guard;
  ARCHITECT_TRACKER + SKILLS.md updates carry the role-side discipline.

### Tightened scope (post-R13)

The agent–orchestrator resource boundary is now explicit: **agents own
the *files* in their worktree, never the *refs*.** The orchestrator
owns:
- branch creation/deletion (`create_worktree`, `remove_worktree`)
- merge / fast-forward into the integration branch (`fast_forward_target`)
- non-FF recovery via auto-rebase in the orchestrator's own worktree (A1)
- tag and branch lifecycle

Any agent attempt to perform these operations on its own is a boundary
violation enforced by R13 (streaming-kill) + SKILLS.md Forbidden Tools.

### Architectural mandate

A **single `ManagedSubprocess` primitive** should wrap every
`asyncio.create_subprocess_exec` call site. Direct usage of the asyncio
primitive should be linted out. Same for `git worktree add` —
`create_worktree` is already the funnel; ensure no caller bypasses it.

### Closure-postcondition pairing

At run termination (any exit path), the orchestrator must assert:
- 0 child PIDs whose `ppid` traces back to the run's pgroup
- 0 `.agent-worktrees/*` paths whose branch carries the run's tag
- 0 `.gate-worktrees/*` paths from this run
- 0 docker containers labeled `agentic-skills.run_id=<run_id>` (requires
  labeling, currently absent — separate work)

Failures here become structured `closure_violation` events, not silent leaks.

---

## Invariant I-2 — Doctrine is a contract, not three layers of advice

> Every documented R-rule (or Tier) must map to exactly one declared
> enforcement point AND have an associated test. Documentation alone is not
> enforcement.

### Enforcement points

| Enforcement point | Where |
|---|---|
| `prompt` | injected into the role's task prompt (`prompts_brownfield._load_skill`) |
| `preflight` | `_preflight_retrieval`, lock acquisition, repo-dir checks |
| `streaming` | `claude_agent.stream_agent_task` per-event check (Tier 1.5, R8) |
| `post_validation` | `doctrine_validator.validate_<role>` reading artifacts + retrieval.jsonl |
| `gate` | `regression_gate_svc.run_gate` (test results, regressions) |

### Current R-rule coverage

| Rule | Documented in | Enforcement point | Test? | Verdict |
|---|---|---|---|---|
| R5 (≥3 grounded retrieval calls) | SKILLS.md + CLAUDE.md | `streaming` (Tier 1.5 counts), `post_validation` checks artifacts | partial | ✓ |
| R5b (citations in QA artifacts) | SKILLS.md | `post_validation` (artifact scan) | no | ⚠ |
| R7 (rubric self-consistency) | rubric.md | `post_validation` (scorer flow) | no | ⚠ |
| R8 (≤30 retrieval calls) | SKILLS.md | `streaming` (`max_retrieval_calls`) | no | ✓ |
| R9 (≥1 graph_* call) | CLAUDE.md | **none** | no | ✗ (A8) |
| R10 (gate retry) | code | `orchestrator` retry loop | no | ✓ |
| R10.1 (doctrine retry) | code | `_engineer_flow` / `_qa_or_scorer_flow` retry loop | no | ✓ |
| R10.2 (gate retry with focused prompt) | code | `orchestrator` retry loop with fix prompt | no | ✓ |
| R11 (no_op short-circuit) | code | `_engineer_flow` outcome | no | ✓ |
| R12 (scorer grounding floor) | SKILLS.md | `streaming` (same Tier 1.5) | no | ⚠ |
| R13 (no agent-initiated history-rewriting git) | SKILLS.md (Forbidden Tools) + code | `streaming` (`forbidden_git_op`) | regex unit tests | ✓ |
| Tier 1.5 (pre-modification kill) | code | `streaming` (`pregrounding_violated`) | no | ✓ |

### Architectural mandate

- **A single doctrine spec data structure** (in code, not prose) names each
  rule, its enforcement point, and a callable check.
- **A meta-test** asserts: every doctrine entry has at least one enforcement
  point AND a callable check. Adding a new R-rule without enforcement fails
  CI. Documenting a rule that no code enforces is a build failure.
- **Tests for each rule** as inputs in a synthetic role harness:
  R5 → spawn agent making 2 grounded calls → expect kill.
  R9 → spawn agent with 0 graph_* calls → expect validator fail.
  etc.

### Back-mapped shortcoming

- **A8** (R9 advisory not enforced) is a direct violation of I-2 — the rule
  is documented but lacks an enforcement point. Fixing A8 in isolation
  closes one instance; building the doctrine spec closes the entire class.

---

## Invariant I-3 — Closure postconditions are asserted, not hoped for

> At run termination — any exit path — the orchestrator verifies that the
> world is in the state cleanup intended, and surfaces a structured event
> if not.

### Required postcondition checks

| Postcondition | Today | Architectural target |
|---|---|---|
| 0 alive subprocesses from this run | trust `_kill_pgroup` | scan ppid tree; emit `closure_violation` if any survive |
| 0 stale agent-worktrees | trust `remove_worktree` | `git worktree list` filter by branch pattern; emit violation if found |
| 0 stale gate worktrees | trust local cleanup | `ls .gate-worktrees/` scan; emit violation |
| 0 dangling agent branches | trust orchestrator pre-merge cleanup | `git branch | grep agent/<run_id>` |
| 0 docker containers from this run | no labeling today; nothing to scan | future: label containers `run_id=...`, scan + cleanup |
| `traces_archive/<run_id>/` exists | trust B15 | assert directory exists at terminate; emit violation |
| State file moved to done/ | trust A7 | assert `done/<run_id>.json` exists |

### Back-mapped shortcomings

- The 30h-old `regression_gate.sh` + docker containers observed in Sprint 4
  ARE a closure-postcondition failure. Cleanup didn't reach them; nothing
  asserted they were gone. **No code path today even checks for the
  violation** — the only reason we know about it is that I (claude) listed
  `ps -eo command | grep regression_gate` manually.

### Architectural mandate

- A `closure_check()` function called from the orchestrator's outer finally.
- Each check runs independently (one failure doesn't skip others).
- Violations get a structured SSE event `orchestrator.closure_violation`
  with `kind`, `resource`, `detail`. The doctrine-meta agent reads these
  during post-sprint analysis.

---

## Invariant I-4 — Single source of identity per run

> A run has exactly one `run_id`, minted in exactly one place, threaded
> through every artifact it produces.

### Current state

| Artifact | run_id source | Consistent? |
|---|---|---|
| Lock metadata `_RUN_META[repo]` | router B2 mints | ✓ (canonical mint site) |
| Orchestrator's internal run_id (in `run_brief`) | accepts from router OR mints (back-compat) | ✓ since A7 unified |
| Trace dir name (`<ts>-<role>-<bl>-<task_id>`) | task_id only, NOT run_id | ⚠ — task_id is per-agent, run_id is per-sprint; linkable but not identical |
| Trace `meta.json` `harness_sha` (B14) | captured per-process | ✓ |
| Disk state file `<run_id>.json` (A7) | matches router's run_id | ✓ since orchestrator accepts param |
| `traces_archive/<run_id>/` (B15) | matches | ✓ |
| Log dir `logs/orchestrator/<timestamp>/` (B18) | timestamp-only, NOT run_id | ⚠ — separate identity scheme |

### Back-mapped shortcomings

- A7 + B14 + B15 each came from a separate decision, each invented its own
  identity convention. The Sprint-2 hardening pass unified them through the
  `run_id` parameter, but the log dir (B18) was specced before the
  unification and still uses its own timestamp. **Trace dirs likewise are
  indexed by per-agent task_id, not run_id — meaning to find all traces
  from a given run you must scan the archive's parent dir, not lookup by id.**

### Architectural mandate

- Trace dirs include `run_id` in the path: `traces/<repo>/<run_id>/<role>-<bl>-<task_id>/`
- Log dir matches: `logs/orchestrator/<run_id>/run.log`
- All future cross-artifact joins use `run_id` as the foreign key.
- The router becomes the only place that mints `run_id`.

---

## Invariant I-5 — No aggregate label is more optimistic than its worst component

> A multi-step process whose individual steps can fail must not surface a
> success label unless every step succeeded.

### Current state

Sprint 2 violation: `bl.done outcome="merged"` regardless of whether QA
landed.

Fix landed: **A5** — outcome now ∈ {`merged_full`, `merged_no_qa`,
`merged_no_score`, `engineer_unmerged`, `no_op`}.

### Architectural mandate

- Any function returning an aggregate status must accept a list of
  component statuses and apply the rule "worst wins."
- The doctrine-meta agent should flag any new aggregate label that violates
  this (e.g., a future "sprint.outcome" string that papers over per-BL
  failures).

### Sibling sites to audit

| Site | Aggregate label | Worst-wins? |
|---|---|---|
| `bl.done outcome` | computed from qa_doc_ok, qa_merged, scorer_doc_ok | ✓ (A5) |
| `sprint_complete summary` | currently just lists per-BL; no aggregate verdict | ✓ by absence |
| Trace `meta.json.done.summary` | comes from agent's own JSON summary | ⚠ — trust the agent (defensive: scorer rubric over-rides) |
| Future cross-sprint health score (observer Batch D) | not yet defined | must inherit I-5 |

---

## Invariant I-6 — Failure modes have a canonical taxonomy

> Every shortcoming is classified into one class. The class informs the fix
> shape. Patches that don't fit a class need a new class entry, not an
> ad-hoc workaround.

### Classes (initial set)

| Class | Definition | Examples |
|---|---|---|
| **race** | Two concurrent actors mutate shared state | A1 (operator commit races agent worktree); B2 (concurrent run-brief) |
| **resource-leak** | A resource lives past its intended scope | B1 (orphan claude); A9 candidate (orphan gate); orphan docker containers |
| **silent-failure** | A step failed but the system reported success | A2/A5 (QA give-up labeled "merged"); B12 (file-existence alone bypasses QA) |
| **silent-success** | A step succeeded by accident; the system can't tell | A8 (R9 advisory; agent passed without graph_* calls — "success" is suspect) |
| **consistency-violation** | Cross-component invariant broken | I-3 closure violations; I-4 identity mismatches |
| **enforcement-gap** | A documented rule has no enforcing code | A8 (R9); future: any R-rule documented in SKILLS.md but not in `doctrine_validator.py` |
| **starvation** | A process never makes progress | B5 (idle timeout — claude hung silently); future: gate timeouts |
| **data-loss** | An artifact intended to persist got destroyed | B18 (logs in /tmp/ wiped on reboot); B15 (traces accumulated then overflow) |
| **observability-gap** | A real event happened but produced no record | A6 (formatter dropped fields); B14 (no harness_sha); B15 (live traces buried) |
| **scope-creep** | A component's responsibility expanded silently | B3 (graphify polluting target worktree); B16 (decompose-brief becoming plan-only path) |

### Architectural mandate

- Every `DESIGN_SHORTCOMINGS.md` entry includes a `class:` field at the top.
- The doctrine-meta agent reads existing entries to learn the class
  patterns; new findings get auto-tagged with their class on first draft.
- A class with >3 instances triggers an architectural review: "why does
  this keep happening?" That review either tightens an invariant or
  introduces a new one.

---

## Invariant I-7 — The framework hardens itself

> In steady state, no new R-rule, validator, or invariant comes from a
> human. The framework observes its own failures, proposes hardening, and
> opens proposals (not auto-merges) for operator approval.

### Current state

Every R-rule from R5 onward was added by Eugene (operator) or me (claude)
manually. The framework cannot catch up to itself; each sprint exposes
1–3 new things only after they fail in production.

### Architectural mandate

This is what ABL-0003 + this branch's Batch B is for:

1. After every sprint, a doctrine-meta agent reads all trace dirs, scorer
   rubrics, gate outcomes, and R-rule trigger counts.
2. It identifies recurring failure modes (eg "in 9 of 13 BLs the engineer
   omitted citations on first commit and R5b had to retry").
3. It drafts a proposal under `.planning/doctrine_proposals/<sprint>-<topic>.md`
   with motivation, evidence count, proposed change.
4. The framework-reviewer (Batch C) adversarially reviews the proposal.
5. Operator approves OR rejects (NOT auto-applied).

### Why operator-gated forever

Auto-applying doctrine changes risks runaway self-modification: the agent
loosens the rule that triggered an inconvenient retry, the next sprint
slips past unnoticed, the system silently degrades.

Proposal-review-approve is the safest loop. The doctrine-meta agent earns
trust over many sprints before its proposals get one-click approval, but
never auto-merge.

---

## Cross-reference: existing A/B items mapped to invariants

| Item | Invariant | Class |
|---|---|---|
| A1 (non-FF auto-rebase) | I-1 (worktree lifecycle) | race |
| A2 (qa_doctrine_failed event) | I-5 (truthful labels) | silent-failure |
| A3 (Milvus auto-restart) | I-1 (resource lifecycle) | resource-leak (via crash, not orphan) |
| A4 (start_bl resume) | I-3 (resumability of state) | data-loss adjacent |
| A5 (truthful outcome) | I-5 | silent-failure |
| A6 (full event dump) | I-3 (observability) | observability-gap |
| A7 (disk-persisted state) | I-4 (identity), I-3 (closure) | data-loss |
| A8 (R9 enforcement) | I-2 (doctrine contract) | enforcement-gap |
| **A9 (gate subprocess pgroup)** *(candidate)* | I-1 | resource-leak |
| B1 (claude pgroup kill) | I-1 | resource-leak |
| B2 (per-repo lock) | I-1 (shared-state guard) | race |
| B3 (graphify cache) | I-1 (write scope) | scope-creep |
| B4 (UI new events) | I-3 (observability) | observability-gap |
| B5 (idle timeout) | I-1 (subprocess hygiene) | starvation |
| B7 (gitignore preflight) | closed by B3 | scope-creep |
| B9 (brief-hash idempotency) | I-1 (race guard) | race |
| B12 (partial_resume git-log check) | I-5 (no false-positive resume) | silent-failure |
| B14 (harness_sha) | I-4 (identity) | observability-gap |
| B15 (trace archive) | I-1 (lifecycle), I-3 (closure) | observability-gap |
| B17 (UI Stop) | I-1 (closes via B1) | resource-leak |
| B18 (logs out of /tmp/) | I-3 (durability) | data-loss |
| A12 (events.jsonl vs stream.jsonl drift) | I-2 | enforcement-gap |
| A13 (phase events not in per-agent trace) | I-3 + I-5 | observability-gap |
| A14 (meta-agent forbidden_tools gap) | I-7 | scope-creep |
| R13 (agent-initiated history rewriting) | I-1 (refs are orchestrator-owned) | scope-creep + silent-failure |
| R5b prompt drift (first-attempt fails) | I-2 (rule fires; prompt didn't teach it) | enforcement-gap |

---

## Empty cells = next likely shortcomings

Audit each component against each invariant. Cells without a current
mitigation are the next candidates for hardening:

| Component | I-1 lifecycle | I-2 doctrine | I-3 closure | I-4 identity | I-5 truthful labels | I-6 taxonomy | I-7 self-harden |
|---|---|---|---|---|---|---|---|
| `claude_agent` | ✓ (B1, B5) | ✓ (Tier 1.5) | ⚠ (no closure assert) | ✓ (trace) | n/a | n/a | n/a |
| `regression_gate_svc` | ✗ (A9 candidate) | n/a | ✗ (no closure check) | ⚠ (uses ad-hoc id) | n/a | n/a | n/a |
| `indexing` (graphify) | ✓ (B3) | n/a | ⚠ | ✓ | n/a | n/a | n/a |
| `indexing` (claude-context) | ⚠ (no pgroup) | n/a | ⚠ | ✓ | n/a | n/a | n/a |
| `git_worktree` | ✓ | n/a | ⚠ (no postcondition scan) | ✓ | n/a | n/a | n/a |
| `orchestrator.run_brief` | ✓ | n/a | ⚠ (no closure_check call) | ✓ (A7) | ✓ (A5) | n/a | ✗ (no meta-agent yet) |
| `doctrine_validator` | n/a | ⚠ (R9 gap = A8) | n/a | n/a | n/a | n/a | n/a |
| `router projects.py` | ✓ (B2/B9) | n/a | n/a | ✓ (mint site) | n/a | n/a | n/a |

**At time of writing**, the empty cells say:
- Closure-check is missing in 5 components.
- I-7 (self-hardening) is missing everywhere — this branch's Batch B
  introduces it.
- I-2 has one gap (A8 / R9), already in the ledger.
- I-1 has one gap (A9 candidate, gate subprocess), surfaced Sprint 4.

The point isn't to fix all empty cells right now. The point is they're
*visible* now, in one place, before the next failure surfaces them
individually.

---

## Living document

Update this file when:
- A new invariant is identified (numbered I-N+1).
- A component's compliance changes (✓ → ✗ or vice versa).
- The doctrine-meta agent (Batch B) writes a proposal that touches an
  invariant.

Do NOT update when an individual shortcoming is filed — those go in
`DESIGN_SHORTCOMINGS.md`. This document is the structural lens; the
ledger is the instance list.

*Last updated 2026-05-23 — initial draft after Sprint 4's A8 + A9-candidate
findings made the structural pattern visible.*
