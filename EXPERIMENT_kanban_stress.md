# Experiment — Kanban Stress Test of the Crew

> Authored 2026-06-07. Purpose: deliberately stress the autonomous crew on the
> dimension the Task-Labels sprint never tested — **feature difficulty** (a
> refactor with a fragile foundation BL), while holding the substrate fixed (the
> toy `project-management-app` target, for controllability + zero blast radius).
> This is Experiment 1 of two; Experiment 2 (real third-party brownfield repo) is
> the follow-on once feature-difficulty and substrate-noise are separated.

## 1. Motivation

The Task-Labels sprint (`run-20260607T002244Z-1a46d9`) was 6 **additive** BLs:
new tables, new router, "keep old behavior byte-for-byte." It went 6/6 with 0
doctrine violations and 0 acceptance findings — but that is weak evidence for the
mission, because additive work never exercises the crew's hard cases. The one
recorded crew failure (the Horizon run) was a **foundation BL that broke existing
behavior** and the engineer could not self-repair within budget. This experiment
re-creates that pressure on a controllable substrate.

## 2. Hypothesis

The crew can autonomously deliver an *additive* slice (proven). It is **not yet
proven** that it can deliver a slice that (a) requires a schema migration on a
populated DB under `create_all` (no Alembic), (b) refactors existing
list-ordering behavior, (c) implements a non-CRUD ordering algorithm, and (d)
implements optimistic-UI-with-rollback. We expect at least one of these to
produce an escalation or a latent ship-a-bug — and that is a *result*, not a
failure of the experiment.

## 3. The brief

`brownfield-targets/project-management-app/_brownfield/features/kanban-board-and-ordering/brief.md`
— "Kanban Board with Drag-and-Drop Ordering." 6 BLs:

| BL | Slice | Difficulty probe |
|---|---|---|
| KAN-001 | `rank` field + migration/back-fill on populated DB | **the landmine** — `create_all` won't ALTER; fresh-DB tests hide it |
| KAN-002 | `PATCH /tasks/{id}/move` reorder endpoint | deterministic, concurrency-tolerant ranking algorithm |
| KAN-003 | ordered reads `(status, rank)` | **changes** existing `order_by(Task.id)` — regression surface |
| KAN-004 | characterization test of the OLD ordering first | does the crew pin existing behavior before changing it? |
| KAN-005 | React 3-column board | reuse existing client + keep label chips |
| KAN-006 | drag-drop + optimistic update + rollback | real client state, dep addition, rollback path |

## 4. Predicted failure modes (falsifiable — record which actually happen)

1. **The migration landmine (highest-value prediction).** Engineer adds `rank`
   to the model, unit tests pass (fresh in-memory DB), BL merges green — but the
   real app started against the existing `app.db` 500s with `no such column:
   task.rank`. **Prediction: the crew's own gates do NOT catch this** because
   every test fixture builds a fresh DB. If true, this is a finding about the
   crew's gate design (it never tests against a populated/persistent DB), not
   just this BL.
2. **Self-repair depth on KAN-001.** If the crew *does* detect the migration
   need, can it implement a correct guarded `ALTER`/back-fill, or does it thrash
   and escalate (the Horizon pattern)?
3. **Silent ordering regression.** KAN-003 changes the list contract. Does the
   regression checkpoint (now that item #1 is fixed — see §6) actually flag the
   changed ordering, or does it pass blind?
4. **Optimistic rollback missing.** KAN-006 ships the happy path (card moves) but
   no rollback on failure. Does acceptance E2E catch a forced server-failure
   rollback gap, or does it only test the success path?
5. **DnD dep integration.** Adding a frontend DnD dep cleanly (types, bundle,
   build) vs. a broken/again-untested integration.

## 5. Measurement / success-break criteria

Record for the run:
- BLs merged / escalated, and **which BL** escalated (KAN-001 escalation = the
  capability-wall finding we want documented).
- Did the crew write KAN-004 characterization BEFORE KAN-003 unprompted?
- Did the regression checkpoint return a real verdict (green/regressed) — not
  `inconclusive` (item #1 must be fixed first, §6)?
- Did acceptance E2E include a rollback/failure-path journey, or only happy path?
- **Manual post-sprint verification (the landmine):** stop the running app,
  restart it against the existing on-disk `app.db`, hit
  `GET /api/projects/1/tasks` and the board. A 500 (`no such column`) = the crew
  shipped a latent migration bug its gates could not see → primary finding.

Interpretation:
- **Clean 6/6 + landmine handled + rollback tested = strong signal** the crew
  handles hard, non-additive work. Materially advances the thesis.
- **Escalation on KAN-001 = expected capability wall**, cleanly documented (no
  abort, dossier attached). Also a good outcome.
- **6/6 green BUT real app 500s on restart = the most important finding:** the
  crew's gates give false confidence on schema-migration work. Feeds a
  doctrine/gate hardening proposal (test against a populated DB).

## 6. Preconditions (run order)

1. **DONE — item #1 gate fix** (`fix(gate)` commit `dfc00df`): `run_gate` now
   returns a real verdict instead of `inconclusive` on this target (proven live:
   integration-vs-main now `green`). Without this the §5 regression read is
   blind.
2. PREFLIGHT (`PREFLIGHT.md`) before launch: Milvus/Ollama up, target baseline
   green, no leftover gate/agent worktrees, disk budget.
3. Target on `integration` @ baseline; `main` pristine. The toy is the substrate
   — blast radius is one branch on the toy; rollback = `git reset integration`.
4. Clean up the seeded demo labels/tasks first (or accept them as pre-existing
   data — note: that seeded data ALSO exercises the §5 landmine, since those rows
   predate the `rank` column).

## 7. Rollback

The run only writes to `integration` on the toy target. `main` stays pristine
(enforced by `_ensure_on_agent_branch`). A bad run is recoverable with
`git -C <target> reset --hard <baseline> ` on `integration`. Zero impact on the
agentic-skills harness repo.

## 8. Next (Experiment 2)

After Exp 1, scope a real third-party brownfield PM-ish repo: clone outside the
repo, write `.agentic-skills.json`, get the baseline gate green (may need
Docker/CI setup), index for retrieval, pick a non-trivial brief. Higher thesis
fidelity, more setup risk — run it with Exp 1's feature-difficulty findings as a
baseline so substrate-noise is isolated.
