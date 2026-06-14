# Design — Wave concurrency>1 (true intra-wave parallel BL execution)

> Author: architect (Claude). Date: 2026-06-14. Branch: `wave-concurrency`.
> Status: **DESIGN — awaiting operator review before implementation.**
> Predecessor: `PROPOSAL_PARALLEL_WAVE_EXECUTION.md` (Phases 1–3, shipped, flag
> `wave_execution`, concurrency=1). This is **Phase 5** of that program: raise the
> intra-wave concurrency from 1 to N.
> Live context: Phases 1–3 are being live-proven right now on
> `run-20260614T143621Z-0b7c91` (order-fulfillment, `wave_execution=True`): R21 DAG
> gate accepted, BL-0001/0002/0003 merged_full, `reindex_after_wave.{0,1}` fired at the
> barriers with **zero** per-BL reindex. The scaffolding this design builds on is
> therefore being verified on a real sprint as this doc is written.

---

## 0. The operator's goal (verbatim intent)

Run the independent BLs of a wave **at the same time**, not one after another. Today
the wave scheduler groups BLs by the R21 dependency DAG into topological waves but runs
each wave at **concurrency=1** (byte-identical to the old flat sequential loop). The
operator wants the BLs within a wave to execute **concurrently**, so a wave's wall-clock
is the *slowest* BL in it, not the *sum*.

This design delivers that, with correctness held to the project's 95%-verified bar.

---

## 1. Correctness principle — interleaving-independent determinism

> Operator correction (2026-06-14), adopted as the governing principle of this design.

The agents (engineer/QA subprocesses) are LLM-driven and nondeterministic — that is
*outside* the harness and unchanged by this work. **The orchestration layer is plain
asyncio Python that we author and fully control.** Therefore concurrency correctness is
an **engineering obligation we own**, not an epistemic gap we tolerate.

What is *not* under our control is **timing**: each `await` in a concurrent task resolves
when an external process completes (`claude` subprocess, `git`, the gate, the filesystem),
and those completion times vary with OS scheduling, I/O, and CPU load. So the **interleaving**
of concurrent tasks is timing-dependent.

The design rule that follows: **make the *outcome* independent of the interleaving.** We
do not rely on tests happening to sample a bad interleaving. We make every concurrent
path either (a) operate on **isolated state** (its own git worktree, its own work-branch,
its own trace dir), or (b) touch shared state only under an **explicit lock with a fixed
acquisition order** and a **deterministic application order** (BL-id order). Under that
rule the assembled result is a pure function of the agents' diffs — the one thing that
*is* allowed to be nondeterministic (and is the LLM's province). The living proof that
this discipline is necessary and sufficient: the **findings-ledger data-loss race**
(`8e7d5ed`) was a pure harness timing bug with zero LLM involvement; isolating the lock
onto a stable sidecar fixed it deterministically. We apply the same discipline to every
shared resource below.

---

## 2. Current state (grounded in code)

`webapp/backend/app/services/orchestrator.py`:
- `_dep_waves(items)` (≈L3435) groups BLs into topological waves from the R21 DAG.
- The wave loop (≈L3710) is a **flat** `for it in ordered:` that runs each BL via
  `async for e in _engineer_flow(...): yield e` — awaited to completion before the next.
  Wave boundaries (`wave.start`/`wave.done`) and the barrier reindex
  (`reindex_after_wave.<n>`) are emitted as the flat order crosses DAG layers.
- Each BL **fast-forward-merges directly into the shared `agent_branch`** (the target's
  `integration`); the loop captures `pre_bl_sha` (≈L3750) to atomically roll back a single
  in-flight BL on failure.
- `_checkpoint(current_bl=bl_id)` (A7 disk state) tracks **one** in-flight BL.
- Per-agent **git worktree isolation** already exists (`git_worktree.py`).
- The **findings-ledger** concurrent-append race is **already fixed** (`8e7d5ed`).
- The **barrier reindex** is already concurrency-correct (fires only after a whole wave
  merges).

So the foundation is partly in place (worktrees, barrier reindex, ledger lock). The gaps
are the four below.

---

## 3. The four gaps and their designs

### 3.1 Async event-stream fan-in (the core new primitive)

**Gap.** `run_brief` is a single async generator yielding ordered SSE events; one BL is
awaited at a time. To run N BLs of a wave concurrently we must run N `_engineer_flow`
coroutines simultaneously and **merge their event streams into the one output generator**.

**Design.** A bounded fan-in helper:

```
async def _merge_streams(factories, concurrency):
    # factories: list of zero-arg callables each returning an async-gen (one per BL)
    # Runs up to `concurrency` at once; yields their events interleaved as they arrive.
    q = asyncio.Queue()
    sem = asyncio.Semaphore(concurrency)
    SENTINEL = object()
    async def _drain(factory, idx):
        async with sem:
            try:
                async for ev in factory():
                    await q.put((idx, ev))
            except Exception as e:            # isolate one BL's failure
                await q.put((idx, {"_stream_error": repr(e)}))
            finally:
                await q.put((idx, SENTINEL))
    tasks = [asyncio.create_task(_drain(f, i)) for i, f in enumerate(factories)]
    live = len(tasks)
    while live:
        idx, ev = await q.get()
        if ev is SENTINEL:
            live -= 1
            continue
        yield idx, ev
    await asyncio.gather(*tasks)              # surface any task exception
```

- **Event tagging.** Each yielded event is tagged with its BL id (the `idx`→`bl_id` map)
  so the merged SSE stream stays legible (`{"bl_id": "...", ...}`). The **stream order is
  cosmetic** (display only) — it does NOT feed any control decision. All control decisions
  read the structured per-BL **outcome**, collected after each stream ends.
- **Determinism.** The *interleaving of displayed events* varies run to run; the *set of
  outcomes* and the *assembled result* do not (§3.2). This is the principle of §1 in action.
- **Cancellation / no-abort.** One BL raising is caught in `_drain` (`_stream_error`) and
  does not kill siblings; the orchestrator handles that BL's failure via the existing
  no-abort path after the wave drains.

### 3.2 Per-BL work-branch + deterministic barrier assembly

**Gap.** Today every BL FF-merges into the shared trunk; with N concurrent BLs that
**races** (two merges into one ref) and can **conflict** (overlapping file edits).

**Design — isolate work, serialize integration, fix the order.**
- Each concurrent BL's engineer/QA merge into a **per-BL work-branch**
  `agentic-work/<run_id>/<bl_id>` forked from the **wave-base SHA** (the trunk SHA at the
  wave's start). No concurrent task touches the trunk during the wave.
- At the **wave barrier** (all BLs of the wave drained), the orchestrator **assembles**
  the wave onto the trunk by merging the per-BL work-branches **in fixed BL-id order**
  (deterministic), one at a time (no concurrent trunk writes). Only *then* does
  `reindex_after_wave.<n>` run (unchanged) and the next wave fork from the new trunk SHA.
- **Why this is interleaving-independent:** the trunk is mutated by exactly one writer
  (the barrier assembler), in a fixed order, after all agent work is frozen on isolated
  branches. The result depends only on the per-BL diffs, not on which BL finished first.

**Conflicts at assembly** are the one genuinely new decision — see §4 (the fork). The
default-recommended cut (serialized assembly) treats an assembly conflict on a BL exactly
like a merge failure today: route to the Janitor / no-abort loop for that BL; siblings
already assembled stay; the conflicting BL surfaces honestly. No silent drop.

### 3.3 Concurrency-safe orchestrator state

**Gap.** `_checkpoint(current_bl=...)` is single-pointer; `pre_bl_sha` trunk-reset assumes
one in-flight BL.

**Design.**
- `_checkpoint` gains `in_flight_bls: list[str]` (the wave's live set) alongside the legacy
  `current_bl` (kept = first of the set, for back-compat / resume display). Checkpoint
  writes already go through an atomic temp-replace; add the same **stable-sidecar lock**
  pattern used for the findings ledger so concurrent updates can't clobber.
- **Rollback** changes from "reset the shared trunk to `pre_bl_sha`" to "**discard the
  failed BL's work-branch**" — siblings are untouched because they were never on the trunk
  during the wave. The trunk only ever advances at the barrier, atomically, in fixed order.
- Resume semantics: a crash mid-wave re-forks the wave-base SHA and re-runs the wave's
  not-yet-assembled BLs (idempotent — work-branches are disposable and deterministically
  named).

### 3.4 Resource governance

**Gap.** N concurrent `claude` subprocesses + gate stacks stress CPU / RAM / Docker.raw / disk.

**Design.**
- New request flag **`wave_concurrency: int = 1`** (default 1 ⇒ **today's proven behavior,
  byte-identical**; concurrency>1 is opt-in). Effective per-wave concurrency =
  `min(len(wave), wave_concurrency, _resource_cap())` where `_resource_cap()` defaults to
  `max(1, (os.cpu_count() or 2) // 2)` and is operator-overridable.
- **Per-wave resource preflight**: before opening a wave at concurrency k, run the existing
  disk preflight scaled by k (`per_bl_disk_gb * k`); if it fails, **degrade k** (down to 1)
  rather than abort — emit a `wave.concurrency_degraded` event with the reason. Honest, no
  silent cap (the no-silent-truncation rule).
- The gate already runs per-BL scoped tests (simple gating model); k concurrent gates are
  independent DB-only stacks — the `COMPOSE_PROJECT_NAME` per-run prefix + closure_check
  already isolate/clean them. Verify (not assume) under concurrency in the test plan.

---

## 4. The one open decision — assembly-conflict policy

Two BLs in a wave that edit **overlapping lines** will conflict at barrier assembly. This
is the only genuinely new failure mode. Two strategies:

**(A) Serialized deterministic assembly (RECOMMENDED first cut).** Assemble per-BL
branches onto the trunk in fixed BL-id order; an assembly conflict on a BL is handled like
a merge failure today → Janitor / no-abort loop for that BL, siblings keep their assembled
state. Simplest, lowest new-failure-surface, captures ~the full wall-clock win (the
expensive engineer+QA+gate work parallelizes; only the cheap merge step serializes). The
R21 contract design already pushes the PO toward **file-disjoint** BLs within a wave, so
conflicts should be rare; when they occur, the existing repair machinery handles them.

**(B) Conflict-resolver agent (later phase).** A dedicated agent resolves overlapping edits
on a scratch assembly branch, then accept on the assembled branch. Maximum flexibility but
adds an agent + a new, harder-to-prove failure mode. Defer until (A) is live-proven.

**Recommendation:** build **(A)** now (serialized-assembly concurrency); keep **(B)** as a
named follow-on. This staged path keeps each step independently provable.

---

## 5. Failure semantics under concurrency (no-abort preserved)

- One BL escalating **does not abort the wave**. The wave drains; surviving BLs assemble;
  the escalated BL surfaces via the existing terminal `escalated` + dossier path. Aborting
  is still never an acceptable outcome (no-abort doctrine).
- `sprint_complete` aggregation is honest: per-BL outcomes (`merged_full` / `escalated`)
  are reported exactly; a partially-assembled wave is reported as such, not as "all green."
- I-5 truthful aggregation: the merged SSE stream's cosmetic interleaving never masks a
  real per-BL outcome.

---

## 6. Flag / rollout / rollback

- Reuse `wave_execution: bool` (gates the whole wave machinery, already shipped).
- Add `wave_concurrency: int = 1`. **`wave_concurrency=1` is byte-identical to the shipped,
  now-being-live-proven behavior** — it is the rollback. `wave_concurrency>1` is the new
  path, default OFF.
- Doctrine-spec / CLAUDE.md table: no new R-rule (this is execution mechanics, not doctrine),
  but `wave_concurrency` is documented alongside `wave_execution`.

---

## 7. Test plan + the 95% live-proof gate

**Unit (deterministic, on the remote venv — remote-first):**
1. `_merge_streams` interleaves N generators, surfaces all events, isolates one failing
   generator without killing siblings, respects the concurrency cap.
2. Barrier assembly merges work-branches in fixed BL-id order; result identical regardless
   of the order the streams *finished* (simulate with shuffled completion).
3. Assembly-conflict on one BL → that BL routes to the no-abort path; siblings keep state.
4. `_checkpoint` round-trips `in_flight_bls`; concurrent updates don't clobber (sidecar lock).
5. `wave_concurrency=1` path is byte-identical to the current flat loop (regression lock).
6. Resource preflight degrades k (not abort) when disk is tight; emits the degraded event.

**OFF-path regression:** the full remote suite stays green
(`cd webapp/backend && .venv/bin/python -m pytest tests/ -p no:cacheprovider`).

**The 95% live gate (the only artifact that earns the `[x]`):** a real sprint with a wave
containing **≥2 BLs run concurrently**, including a **deliberately file-overlapping BL pair**
to exercise the assembly-conflict path, that:
- shows `wave.start` with k>1 effective concurrency + interleaved per-BL events,
- assembles deterministically (re-runnable to the same trunk tree given the same diffs),
- reaches `acceptance.loop.accepted` + `integrity_ok=true`,
- passes the regression checkpoint,
- and ideally repeats clean 2–3× (the residual-timing stress check).

Until that run exists, concurrency>1 is reported at **~70%**, not 95%. The current
concurrency=1 run finishing clean is the verified base this is built on.

---

## 8. Risk · proof · rollback (the calibrated-proposal triple)

- **Risk:** concurrent git integration + N concurrent agent subprocesses (resource +
  trunk-mutation surface). Mitigated by per-BL branch isolation (no concurrent trunk
  writes), deterministic fixed-order barrier assembly, the concurrency cap + per-wave
  preflight, and the §1 interleaving-independence discipline.
- **Named proof:** the §7 live gate (concurrent wave + conflicting pair → accepted +
  regression green + deterministic re-run), plus the unit suite and the OFF-path regression.
- **Rollback:** `wave_concurrency=1` (byte-identical to today) — a single int. No schema or
  doctrine change to revert.

---

## 9. Implementation order (when approved)

1. `wave_concurrency` flag plumb-through (req model → router → orchestrator), default 1.
2. `_merge_streams` fan-in helper + unit tests (3.1).
3. Per-BL work-branch + fixed-order barrier assembly; switch the wave loop to assemble at
   the barrier instead of FF-into-trunk per BL (3.2). Unit tests incl. the byte-identical
   `wave_concurrency=1` regression.
4. Concurrency-safe `_checkpoint` + per-BL-branch rollback (3.3).
5. Concurrency cap + per-wave resource preflight + degrade event (3.4).
6. Assembly-conflict → no-abort routing (strategy A, §4).
7. Remote full-suite green; then the §7 live gate on a purpose-built brief.

Steps 1–6 are mechanical and fully under harness control; step 7 is the empirical proof.
