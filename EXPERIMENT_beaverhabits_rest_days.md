# Experiment 2 — Rest Days (streak freeze) on a REAL third-party brownfield

> Filed 2026-06-07. The first crew sprint against a **real, third-party**
> codebase the team did not author: `daya0576/beaverhabits` (FastAPI +
> SQLAlchemy-async + aiosqlite, BSD-3, ~1.8k★). See
> [`arch_target_beaverhabits`](.claude/memory/arch_target_beaverhabits.md) and
> ledger **A57** (the gate enabler that made this target runnable).

## Why this experiment

Experiments 1 (Kanban, telegraphed landmine) and 1b (Task Dependencies,
discovery landmine) both ran on the **purpose-built toy** target
(`project-management-app`) — controllable, but we authored it, so they are weak
evidence for the mission's **brownfield** premise ("point the crew at a real
repo it has never seen"). Exp 2 changes exactly **one** variable: the
**substrate**. Same crew, same gates, but now a real third-party app with its
own idioms the crew must *discover via retrieval*, not recall:

- completions are **not** rows in a table — they are `done:bool` records inside
  a **single JSON blob** per user (`HabitListModel.data` → `DictHabitList` /
  `DictHabit` / `DictRecord`, `beaverhabits/storage/dict.py`);
- a runtime **`HabitDataCache`** (`dict.py:64`) tracks only `done=True` days;
- **streaks are computed in the FRONTEND** (`frontend/components.py:941
  compose_habit_streaks`) as strict consecutive calendar days
  (`(d1-d2).days == -1`) — there is **no** streak API and **no** core streak fn;
- **period/target** logic ("3× per 2 weeks") lives separately in
  `core/completions.py`;
- dates are **naive** ISO strings; "today" is timezone-derived in
  `utils.get_user_today_date`.

The crew must navigate all of this to land a correct feature without breaking
the 48-test baseline.

## The feature (the brief handed to the PO)

**Title:** Add "Rest Days" so planned breaks don't break a habit streak.

**Context:** Users want to take a *planned* day off from a habit (a "rest day")
without losing their streak. Today the only thing recordable for a day is "done"
or nothing, and a missed day breaks the streak. We want first-class rest-day
support.

**Requirements (stated as product behavior — implementation is the crew's job):**
1. A user can mark a specific calendar day for a habit as a **rest day**, and can
   later un-mark it. This must work for **past** days too (e.g. marking last
   Wednesday as a rest day).
2. A rest day is **not** a completion: it must not appear in the habit's
   completion history, must not count toward any periodic target (e.g. a "3× per
   week" habit), and must not be reported as "done".
3. A day cannot be both completed **and** a rest day at the same time — the two
   are mutually exclusive; setting one clears the other.
4. **Streak behavior:** a rest day must neither extend nor break a streak — it
   **bridges** it. If a user completes a habit Monday and Tuesday, takes a rest
   day Wednesday, and completes it again Thursday, their current streak is **3**
   (the three completed days) and is unbroken. A genuinely missed day (no
   completion, no rest day) still breaks the streak as it does today.
5. The app must be able to **report a habit's current streak length** (correctly
   accounting for rest days) so the user can see it.
6. Existing behavior must be preserved **exactly** for habits that use no rest
   days. All existing tests must continue to pass.

**Out of scope:** UI styling polish, bulk import, notifications.

**Acceptance:** verifiable through the API. Demonstrate: a rest day bridges a
streak across a gap; a rest day is not counted as a completion; done/rest mutual
exclusion; and a normal missed day still breaks the streak.

## What is deliberately NOT telegraphed (the discovery surface)

A competent engineer reading the ticket must *discover* — from the real code —
that:
- streak computation today is **frontend-only** and consecutive-calendar-day
  based; to satisfy req 4+5 correctly **and** testably it must become a
  **core/storage** function (the `(d1-d2).days==-1` scan cannot bridge a gap as
  written);
- a rest day needs a **distinct record state**, not `done=True` — otherwise req
  2 fails (it would pollute completions and inflate period targets);
- the **`HabitDataCache`** only indexes `done=True` days, so rest days need their
  own tracking or the bridge can't "see" them;
- **mutual exclusion** (req 3) and **idempotency** of repeated marks must be
  enforced in `DictHabit.tick`/storage, not assumed;
- the new behavior must not perturb **`core/completions.py`** period logic.

## Hypothesis

The crew can deliver a complex, correctness-laden feature on a real third-party
codebase by grounding in retrieval — discovering beaverhabits' JSON-blob storage
model, the frontend-only streak logic, and the rest-day hazards — and either
ship it green-with-tests or escalate honestly with a source-grounded dossier.

## Falsifiable failure-mode predictions

| # | Prediction (what we'd SEE if the crew fails this way) | Falsified if… |
|---|---|---|
| P1 | **False-success via `done=True` tag.** Crew implements rest-day as a completion record with a text marker (`#rest`). Streak "works", baseline stays green, BLs merge — but completions/period targets are silently polluted (req 2 violated). | Rest day is a distinct state and a test proves a rest day is absent from `/completions` and does not satisfy a periodic target. |
| P2 | **Untestable frontend-only streak.** Crew adds bridging only in `frontend/components.py`, exposes no API/core streak, so acceptance can't verify req 4/5 → weak coverage or escalation. | A core/API streak surface exists and is exercised by tests at the pytest layer. |
| P3 | **Middle-gap bridge fails.** The streak still uses `(d1-d2).days==-1` over `done` days only; a rest day in the middle splits the streak (reports 1+1 instead of bridged 3). | A test asserts done,done,REST,done → current streak == 3. |
| P4 | **Mutual-exclusion / idempotency gap.** A day can end up both `done` and `rest`, or repeated marks duplicate records / corrupt the cache. | A test asserts setting rest clears done (and vice versa) and that repeat marks are idempotent. |
| P5 | **Baseline regression.** The storage/cache refactor breaks one of the 48 existing tests (the acceptance regression checkpoint catches it). | `regression_checkpoint` green: 48 baseline tests still pass post-merge. |
| P6 | **Capability wall on real substrate.** Crew cannot navigate the JSON-blob/cache model from retrieval and stalls/escalates at BL-0001 (the storage foundation), as the Horizon run did. | All foundation BLs merge; the crew progresses past storage into streak logic. |

## Measurement / outcome interpretations

- **Clean delivery** — rest-day is a distinct state, streak bridges correctly
  with tests proving the middle-gap case (P3), period logic untouched (P1),
  done/rest exclusion tested (P4), 48 baseline green (P5), acceptance ACCEPT →
  **strongest evidence yet**: the crew handles real third-party substrate +
  discovers non-obvious correctness. Advances the mission's "grounded" +
  "brownfield" claims simultaneously.
- **Honest escalation** with a source-grounded dossier (P6) → a real
  **capability wall on real substrate** — still high-value (the honest-failure
  property), and a precise frontier marker.
- **6/6 green but P1/P3 false-success** → the crew shipped slop the gates didn't
  catch → reveals a **discovery gap + a gate-coverage gap** (the most important
  thing this experiment can surface).

## Run configuration

- Target: `beaverhabits` (symlinked at `webapp/backend/repos/beaverhabits`),
  agent_branch `integration`, baseline `main`, gate `uv run pytest` + test_env
  (A57). Brief submitted via `POST /api/projects/beaverhabits/run-brief`.
- `warm_retrieval=True` (A56 — **first real test that the PO grounds on a fresh
  target**: expect `orchestrator.retrieval_warmup.done` + a non-empty PO
  `retrieval.jsonl`, no `po.grounding_unavailable`).
- `run_acceptance=True` (whole-feature API E2E + the one full-suite regression
  checkpoint), `run_doctrine_meta=True`, `stop_on_failure=True` (halt at the
  first escalation to capture the wall cleanly).

## Results

_(to be filled in §Results after the run terminates — verdict, per-BL outcomes,
failure-mode falsification table, A56 PO-grounding confirmation, honest caveats.)_
