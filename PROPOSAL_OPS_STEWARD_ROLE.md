# Proposal — Ops/Steward Agent (the crew's environment-anomaly investigator)

> **Status:** PROPOSAL, awaiting operator approval. Authored 2026-06-06 by the
> architect after `run-20260606T234911Z-00c0ca` (Task Labels & Filtering on
> `project-management-app`) escalated at BL-0001 on a `merge_to_target` error
> that was an **environment** anomaly, not a code defect — and was diagnosed +
> would have been fixed by the **architect**, outside the crew. That is the
> autonomy gap this role closes.
>
> Operator framing (2026-06-06): *"You yourself exist outside of the crew. Tell
> me which of the crew's own agents should detect and fix such an anomaly."*
> Answer: none today. This proposes the missing role.

---

## 1. Problem statement

The crew has agents for every **code/feature** concern — PO (decompose),
Engineer (build), QA (test), Scorer (rubric), Acceptance (verified root-cause
investigator for product/test/data bugs). It has **no agent** for
**orchestration/environment** failures: the non-code anomalies that arise
*between* agents, in the harness's own working state.

The deterministic orchestrator can **detect** these (it emits `error` /
`infra_fail` / merge-guard refusals) but cannot **investigate and repair** a
novel one — that needs a full Claude Code subprocess. Today such failures route
to the **operator/architect**. Every such route is a "walk away" violation.

### Worked instance (the trigger)

`merge_to_target → error: "main checkout has modified tracked files; not
merging"`. Verified root cause: the target checkout was on `main` (not the
configured `integration` agent branch), the orchestrator's own live
`_brownfield/.../events.jsonl` is a **tracked** file it appends to during the
run (perpetually dirty → trips the merge-guard's clean-checkout precondition),
and `graphify-out` was not gitignored. BL-0001's actual code (`labels.py`,
`models.py`, `test_labels.py` with 11 tests) was **correct** and passed the
native no-Docker gate. The crew produced good work and was blocked by harness
state it had no agent to repair.

## 2. Scope — what this role owns (and explicitly does NOT)

**Owns (environment / orchestration anomalies):**
- Merge preconditions: dirty checkout, wrong branch checked out, non-FF state
  not covered by A1 auto-rebase, branch-ref drift.
- Working-tree hygiene that blocks the harness: stray tracked modifications,
  untracked-vs-tracked collisions (`graphify-out`, generated files), gitignore
  gaps.
- Resource/infra anomalies: leaked worktrees/containers/volumes, `infra_fail`
  (disk near-full, ENOSPC), index/Milvus/Ollama unreachable mid-run.
- Config/setup anomalies: `.agentic-skills.json` test_cmd binary missing,
  venv absent at the path it names.

**Does NOT own (stays with existing roles):**
- Code/test defects in the target → Engineer / QA (per-BL) and Acceptance
  (cross-feature). The Ops agent never edits target *feature* code.
- Product behavior bugs → Acceptance → dispatch → Engineer (ABL-0015).
- Rubric judgement → Scorer.

The boundary line: **Ops repairs the harness's relationship to the target
(branches, working tree, resources, config); it does not change what the target
*does*.**

## 3. Spawn trigger (deterministic, orchestrator-owned)

The orchestrator invokes the Ops agent when a **non-code step** fails — i.e. a
failure that is NOT an engineer/QA gate verdict on target code:
- `merge_to_target` returns `kind=error`
- any phase returns `kind=infra_fail`
- closure-check / preflight reports a violation that blocks progress
- a worktree/branch/git operation errors

It is **not** spawned on `bl_tests: failed`/`regressed`/`no_tests` — those are
code defects owned by the engineer's no-abort loop. Clean separation prevents
the Ops agent from masking real test failures.

## 4. The Ops loop (no-abort doctrine applied to the environment)

Same investigate → fix → verify spine as every other agent, scoped to
infrastructure:

1. **Investigate to root cause** — read the failing harness signal, the git
   state (`git status`, branch, refs), resource state (worktrees, containers,
   disk), and config. Falsify competing causes. Cite the exact blocker
   (file:line / command output), never a hypothesis.
2. **Classify transient-vs-structural** (the critical step — see §5).
3. **Repair** the environment (clean the checkout, reset to the right branch,
   fix the gitignore, reap the leaked resource, recreate the venv) — within a
   whitelisted, auditable set of operations (§6).
4. **Verify** the blocking precondition now passes, and **signal retry** of the
   failed step.
5. On genuine exhaustion (a competent SRE would also be blocked — e.g. a real
   hardware/disk wall, an upstream outage) → **escalate** with a full dossier.
   Never silent abort.

## 5. The transient-vs-structural rule (prevents the complexity pathology)

This is the load-bearing constraint. Without it, the Ops agent band-aids
framework bugs every run and the crew accretes hidden complexity — the exact
pathology flagged in the 2026-06-06 architecture critique.

- **Transient/environmental** (a one-off: leftover dirty file from a prior
  manual session, a leaked container, a flaky reindex) → Ops **repairs in-run**
  and proceeds.
- **Recurring/structural** (the anomaly is caused by a *framework defect* — e.g.
  the harness tracking its own live `events.jsonl`, the bootstrap omitting
  `graphify-out` from `.gitignore`, the run operating on `main` instead of the
  agent branch) → Ops still unblocks the *current* run, but **must emit a
  `structural_anomaly` finding** routed to the **doctrine-meta-agent** (I-7) so
  the architect fixes it **once** at the framework level. A repair that fires on
  the same signature across N runs is by definition structural and must be
  escalated, not silently repeated.

Ops repairs symptoms to keep the run alive; the doctrine-meta-loop fixes causes
so the symptom stops recurring. The architect shrinks as that loop closes.

## 6. Guardrails (operator-gated authority boundaries)

The Ops agent has the **most dangerous** mandate in the crew (it mutates git
refs and the working tree), so it is the most tightly bounded:

- **Whitelisted operations only.** Allowed: `git checkout <agent_branch>`,
  `git stash`/clean of *untracked generated* paths, `git reset` of the working
  tree to a recorded SHA, edit `.gitignore`, reap worktrees/containers/volumes
  tagged with the run_id, recreate a venv from the target's lockfile. **Forbidden
  (R13 still applies):** history-rewrite of agent branches, force-push,
  `reset --hard` onto a branch that carries un-merged crew work, deleting
  target *feature* code, touching `main` except to *preserve* its pristineness.
- **Never destroys un-merged crew work.** Before any reset it records the SHA
  and refuses if the operation would orphan committed BL work.
- **Every action is logged** to the run's events + a dossier (what was dirty,
  what it did, transient-or-structural verdict).
- **Cost cap + escalation bar** identical to other roles: bounded attempts,
  then Option-A escalation.

## 7. Why not just extend an existing agent?

- **Acceptance** is the closest analog (verified root-cause investigator) but is
  end-of-sprint, read-only, and routes `infra→operator` by design — it is built
  to *hand this class to the human*. Re-purposing it would break its clean
  read-only contract and its timing.
- **Engineer/QA** are BL- and code-scoped; giving them git-ref/working-tree
  authority blurs the safety boundary that keeps them from clobbering refs (the
  R13 rationale).
- The **orchestrator** is deterministic code: great at *detecting*, structurally
  unable to *investigate novel anomalies*. It should spawn the Ops agent, not
  try to BE one.

A dedicated, tightly-scoped role keeps each boundary clean.

## 8. Invariant / doctrine placement

- New role SKILLS.md: `skills/brownfield/brownfield-production-incremental-ops/SKILLS.md`.
- Enforcement: the orchestrator's non-code-failure branches spawn it (a new
  flow function `_ops_flow`), mirroring `_engineer_flow`.
- Maps to **I-1** (resource lifecycle), **I-3** (closure postconditions), and
  **I-7** (self-hardening: its `structural_anomaly` findings feed the
  doctrine-meta-agent). Likely warrants a new R-rule in `doctrine_spec.py`
  (Ops escalation/▸repair fidelity) so it lands in the registry, not just prose.

## 9. Immediate disposition of the trigger anomaly

This instance is **structural**, so per §5 it goes to the architect/doctrine
loop now (not a one-off repair):
1. `graphify-out` → add to the target bootstrap `.gitignore` (framework: the
   target-init should always do this).
2. The live `events.jsonl` should **not** be a merge-blocking tracked file —
   either write it outside the merged tree or have `merge_to_target` ignore the
   feature-dir live log.
3. The run must operate on the **agent branch** (`integration`), not whatever is
   checked out — the orchestrator should check out `agent_branch` at run start
   (and assert `main` stays pristine).

These three are framework fixes for the architect; they are the *first
customers* of the Ops/doctrine-meta split this proposal defines.

## 10. Open questions for the operator

1. **New role vs. orchestrator-embedded helper for the simplest repairs?** Some
   repairs (checkout the right branch, gitignore a generated path) are so
   mechanical they could be deterministic orchestrator code, reserving the
   *agent* for genuinely novel anomalies. Where do you want the line?
2. **Authority breadth** — is the §6 whitelist the right initial set, or start
   read-only-plus-propose (Ops diagnoses + proposes the exact repair, operator
   one-click applies) until trust is established, mirroring the ABL-0015
   auto-dispatch calibration discipline?
3. **Naming** — Ops / Steward / SRE / Janitor? (affects SKILLS path + events).
