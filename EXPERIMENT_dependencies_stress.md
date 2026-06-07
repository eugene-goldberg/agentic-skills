# Experiment 1b — Task Dependencies & Blocking (no-telegraph discovery variant)

> Authored 2026-06-07. Second crew stress test. **Different feature class** from
> the Kanban experiment (graph-integrity + invariant-enforcement, not
> schema-migration + ordering) and **deliberately addresses Exp 1's biggest
> caveat**: the Kanban brief *telegraphed* the migration landmine (§5). This
> brief does NOT. Requirements are stated crisply like a real ticket, but the
> hard correctness traps are left for the crew to *discover* — no algorithm
> hand-holding, no "here's the gotcha" section.

## 1. Why a different feature

Kanban stressed: migration on a populated DB, ordering refactor, optimistic UI.
Dependencies stresses an orthogonal set:
- **Graph algorithm correctness** — cycle detection that must be *transitive*
  (A→B→C→A), not just direct-edge.
- **Invariant enforcement across multiple code paths** — "no `done` while
  blocked" must hold on `PATCH /tasks/{id}` AND `PATCH /tasks/{id}/move`, server
  side, not UI-only.
- **Derived read state** — `blocked` / `blocked_by` computed from the graph, not
  stored stale.
- **Regression surface on existing behavior** — the status-update path currently
  sets `status` freely; the invariant changes that.

It is also a *feature on top of features* (labels + Kanban already merged on
`integration`) — realistic incremental brownfield.

## 2. The deliberate design choice: no telegraph

The brief (`…/task-dependencies-and-blocking/brief.md`) states the REQUIREMENTS
(no self-dependency, no circular dependency, no `done` while blocked, on every
status path) but does NOT:
- prescribe the algorithm (no "use DFS / check transitively"),
- call out where the gates could miss a bug,
- include a §5-style landmine section.

This is the fair "would a competent engineer, given a normal ticket, get it
right?" test. Exp 1 proved "executes a well-specified hard brief"; this probes
"discovers the hard parts of a normally-specified one."

## 3. Predicted failure modes (falsifiable — record which happen)

1. **Shallow cycle detection (highest-value probe).** Crew rejects direct
   self/2-cycles but MISSES a transitive cycle (A→B, B→C, then C→A is allowed).
   Post-sprint check: build A→B→C via the API, then attempt C→A — expect
   rejection; if accepted, the graph can be made cyclic.
2. **Invariant enforced on only one path / UI-only.** The done-guard works on
   `PATCH /tasks/{id}` but NOT on `/move` (or only in the React UI), so the API
   still lets a blocked task reach `done`. Post-sprint check: force `done` via
   both endpoints on a blocked task.
3. **Stale/incorrect blocked computation.** `blocked` doesn't update when the
   last dependency completes (computed wrong, or cached/stored).
4. **No characterization** of the existing status path before changing it
   (REQ-DEP-005) — the change to existing behavior ships silently.
5. **Regression** — existing status-change / move / label tests break, or the
   new guard wrongly blocks unblocked tasks.

## 4. Measurement / success-break criteria

Record: BLs merged/escalated (and which BL), acceptance verdict, doctrine
violations, suite delta. Then the manual probes that the crew's fresh-DB gates
may not cover:
- **Transitive cycle:** `POST` A→B, B→C, then C→A → expect 409/422. (#1)
- **Done-guard on every path:** create blocked task, `PATCH status=done` → 409,
  `PATCH /move status=done` → 409. (#2)
- **Unblock:** complete the dependency, confirm the dependent becomes
  `blocked=false` and can then be set `done`. (#3)
- **No regression:** existing labels/Kanban/status flows still work; full suite
  green.

Interpretation:
- **6/6 + transitive cycles rejected + guard holds on every path + unblock works
  = strong signal** the crew discovers and handles hard correctness unprompted —
  directly retires Exp 1's "telegraph" caveat.
- **Ships a shallow cycle check or a one-path guard that the gates pass = the key
  finding:** the crew implements the happy path of a normal ticket but misses the
  hard correctness the ticket implies — and its gates don't catch it. Feeds a
  doctrine proposal (QA must enumerate invariant edge cases from requirements).
- **Escalation = a clean capability-wall datapoint** (no abort; dossier).

## 5. Preconditions

1. Harness server on :8000 running THIS session's code (item #1 gate fix, scorer
   persistence, Janitor). Already restarted (R16 present). Regression checkpoint
   returns real verdicts.
2. Target on `integration` (labels + Kanban merged) @ baseline; `main` pristine.
   The new feature builds on the merged board.
3. Sprint runs in worktrees → the running pm-app dev servers (:8002/:3002) and
   the runtime `backend/app.db` do not interfere.
4. Blast radius = one branch on the toy; rollback = `git -C <target> reset --hard
   <baseline>` on `integration`. Zero impact on agentic-skills.

## 6. Relationship to the experiment program

- Exp 1 (Kanban): well-specified hard feature, landmine telegraphed → PASSED.
- **Exp 1b (this): different hard feature, landmine NOT telegraphed** → tests
  discovery.
- Exp 2 (future): real third-party brownfield repo → tests substrate realism.

## 7. RESULTS — `run-20260607T135926Z-908991` (2026-06-07)

**Verdict: the crew PASSED the no-telegraph discovery test.** From a brief that
stated requirements like a normal ticket and deliberately withheld the algorithm
and gotchas, the crew **discovered and correctly implemented** the hard
correctness on its own. ~4.5h (08:59→13:28), **6/6 BLs `merged_full`, 0
escalations, 0 janitor spawns, `main` pristine.** Scorecards (all Pass W/R):
BL-0001 97 · BL-0002 95 · BL-0003 95 · BL-0004 95 · BL-0005 97 · BL-0006 94.
regression_checkpoint **green** (item-#1 exit-code fallback); scorer merged 6/6
(item-#2 fix); acceptance validator.ok, 0 findings.

**Predicted failure modes — all FALSIFIED, confirmed at BOTH code and runtime:**

| Prediction (§3) | Code | Live probe (restarted backend, real data) |
|---|---|---|
| #1 shallow cycle detection | `_would_create_cycle` is a reachability **DFS** (`stack`+`visited`, follows edges across the graph) | A→B→C then **C→A → 409** "Dependency would create a cycle"; self-dep A→A → 409 |
| #2 one-path / UI-only done-guard | one shared `_reject_if_blocked_done` applied to **both** `update_task` (`PATCH /tasks/{id}`) and `move_task` (`/move`), server-side, reusing the same `_blocked_state` as `TaskRead.blocked` | blocked X: `PATCH /tasks/X done` → **409**, `PATCH /tasks/X/move done` → **409** ("blocked by tasks [11]") |
| #3 stale blocked computation | `blocked`/`blocked_by` derived from dependencies' live statuses (not stored) | complete Y → X `blocked=false` → `PATCH X done` → **200** (unblock works) |
| #4 no characterization | BL-0005 dedicated characterization + edge BL merged | (n/a — covered by the dedicated BL) |
| #5 regression | existing tasks/labels/Kanban untouched | full-suite regression_checkpoint green; acceptance 0 findings |

**This retires Exp 1's biggest caveat.** Exp 1 proved "executes a well-specified
hard brief (landmine telegraphed)." Exp 1b proves "**discovers** the hard
correctness from a normally-specified ticket" — transitive closure and
multi-path server-side invariant enforcement, unprompted.

**Honest caveats:**
1. **This run's PO grounded BLIND** (0 retrieval calls — the A56 cold-start; the
   fix wasn't live on the running harness). So the crew produced a correct 6/6
   *despite* the PO grounding on direct file reads, not the indexed graph/semantic
   layer. Strong outcome, but it means PO-retrieval grounding is **not** what
   carried this run — the engineers' retrieval (which worked) + the codebase's
   own clarity did. A56 (live after the next harness restart) closes the PO gap;
   a future run should confirm a grounded PO.
2. **Still the toy substrate.** Exp 2 (real third-party brownfield) remains the
   substrate-realism test.
3. The feature builds on the already-merged labels + Kanban — realistic
   incremental brownfield, but a clean, small codebase.

**Net:** combined with Exp 1, the worker-crew now has evidence it can deliver
non-additive, correctness-heavy features both when the hard part is *telegraphed*
(Kanban) and when it must be *discovered* (dependencies). The frontier moves to
substrate realism (Exp 2) and closing the PO-grounding gap (A56 live).
