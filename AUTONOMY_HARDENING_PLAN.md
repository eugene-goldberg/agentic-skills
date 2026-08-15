# Autonomy Hardening Plan — closing the mission-blocking flaws

> **Status: AUTHORIZED 2026-08-15** — operator directed "make the most
> sensible choices, create a new branch, begin executing." Decisions
> locked (all per architect recommendation): **D1** keep
> `stop_on_failure=True` until one clean triage-ON sprint; **D2**
> revert operator-gated in v1; **D3** no QA-before-merge restructure;
> **D4** sandbox track deferred to its own plan; **D5** no auto-resume
> (surface + explicit resume); **D6** all batches, order 0→1→2→3→4,
> 5–7 opportunistic. Work branch: `autonomy-hardening` (off
> `architect-prereqs` @ `8745331`). Live tracker:
> `AUTONOMY_HARDENING_TRACKER.md`.
>
> Authored 2026-08-15 by the architect from a full code audit of
> the harness (every finding verified at file:line against the
> `architect-prereqs` tip `8745331`).
>
> **Source findings:** C1–C5 (critical) and M1–M4 (major) from the
> 2026-08-15 audit session, plus 6 smaller confirmed defects. Known
> ledger overlaps: C1=A34, C4=A39+A44-followup+A45. New findings get
> ledger entries in Batch 0 (proposed IDs A49–A57).
>
> **Companion docs:** `DESIGN_SHORTCOMINGS.md` (instances),
> `ARCHITECTURE_INVARIANTS.md` (lens), `ARCHITECT_PLAN.md` (prereqs
> branch — Batches C/D/E/G remain separately proposed there).

---

## 0. The thesis-level framing

The audit's one-paragraph synthesis: the worker cell is sound; what's
missing is everything a human crew has *above* the individual
contributor —

| Missing crew function | Flaw | Batch here |
|---|---|---|
| Existence independent of who's watching | C1 (A34) | **1** |
| Trustworthy senses | C4 (A39, A44-wiring, A45) | **2** |
| A tech lead who exercises judgment on failure | C2 | **3** |
| Review-with-teeth and a revert option | C3 | **4** |
| An economically viable inner loop | C5 | **5** |
| A memory | M1 | **6** |
| Deployment-grade hygiene (checkout, secrets, retrieval health) | M2–M4 | **7** |

Sequencing rationale: **1 → 2 → 3** is a strict dependency chain — a
detached, durable run (1) is the substrate everything executes on;
triage (3) built on lying signals (2) mis-triages, so signals are
repaired first. 4–7 are independent of each other after 3 and can be
re-ordered by operator priority. Every batch is independently
revertible; no batch changes a default behavior without an explicit
operator decision (§10).

---

## Batch 0 — Preconditions (environment + ledger hygiene)

Nothing in this plan can be *verified* until the migrated environment
(`/Users/egoldberg`, discovered 2026-08-15) is operational.

| ID | Item | Verification |
|---|---|---|
| 0-1 | Memory symlink: `rmdir` empty canonical dir + `scripts/setup_memory_symlink.sh` | `readlink ~/.claude/projects/<enc>/memory` → repo `.claude/memory` |
| 0-2 | Recreate `webapp/backend/.venv`; install deps | `pytest tests/ -q` → 208/208 |
| 0-3 | Restore brownfield target(s): clone `full-stack-fastapi-template` under `~/dev/ai-projects/brownfield-targets/`, restore branches (incl. the Journey 03 findings ledger state), re-link `webapp/backend/repos/`; remove dangling `lg-graph-test` symlink or re-point it | PF-6, PF-10 |
| 0-4 | Docker Desktop + Milvus stack + Ollama `bge-m3` | PF-1..3, PF-5 |
| 0-5 | File new ledger entries: **A49** dep-gating gap (I-6 class: silent-failure), **A50** post-merge toothless quality / no revert primitive (I-5), **A51** PO `check=False` commit + main-checkout branch invariant (I-5, I-3), **A52** agent env inheritance + `--dangerously-skip-permissions` (I-1 boundary / security), **A53** mid-sprint indexer `ok` unchecked (I-5), **A54** `has_new_commits("HEAD~1")` semantics (I-2), **A55** `extract_section` None → literal "None" prompt (I-5), **A56** no `--model` pinning (I-4 identity), **A57** retrieval-budget hard-kill discards in-flight work (I-1) | entries in `DESIGN_SHORTCOMINGS.md` with class + invariant back-refs |

**Effort:** ~half a day (mostly environment). **Risk:** zero (docs +
env). **Rollback:** n/a.

---

## Batch 1 — C1 / A34: the run outlives the connection

**Invariant:** I-1 (run lifecycle owned end-to-end), I-3.
**Goal:** a sprint survives client disconnect, browser close, and
uvicorn restart-with-resume; SSE becomes a *view* of the run, not the
run itself.

### 1-1 Run registry + background execution

- New `app/services/run_registry.py`: `start_run(...)` wraps
  `orchestrator.run_brief` in `asyncio.create_task`, registered as
  `{run_id: {task, queue, started_at, repo}}`.
- Events fan out to (a) the existing per-feature `events.jsonl`
  appender (already durable, `projects.py:1316`) and (b) an in-memory
  `asyncio.Queue` per attached consumer.
- `POST /run-brief` gains `detached: bool = False` (back-compat: the
  default preserves today's inline streaming). With `detached=true` it
  returns `202 {run_id, events_url}` immediately.
- Explicit abort: `POST /api/runs/{run_id}/abort` cancels the task —
  **disconnect stops meaning abort**. Cleanup paths (B1 pgroup kills,
  worktree finallys, A7 `mark_terminated`) already fire on task
  cancellation; verified they are `finally`-based, not
  GeneratorExit-dependent.

### 1-2 Resumable event stream

- `GET /api/runs/{run_id}/events` — SSE consumer: replays
  `events.jsonl` from optional `Last-Event-ID`/offset, then tails live
  via the queue. Multiple concurrent consumers allowed.
- `GET /api/runs/{run_id}` — status snapshot from A7 disk state.

### 1-3 Startup orphan surfacing (not auto-resume)

- On FastAPI startup: scan `.orchestrator-state/*.json` (active) and
  emit a log + expose `GET /api/runs?status=orphaned`. Resume remains
  an explicit `POST /run-brief {skip_po:true, ...}` — auto-resume is
  deferred (operator decision D5) because blind resume after a crash
  can double-run a BL whose merge landed but whose checkpoint didn't.

**Risk (explicit):** medium-high — touches the run lifecycle; the B2
lock and `_RUN_META` currently assume request-scoped runs. Mitigation:
lock acquisition moves into `start_run`; the inline (non-detached) path
delegates to the same registry so there is exactly one execution path.
**Named test:** integration test — start detached run against a stub
orchestrator, kill the SSE consumer mid-run, assert run completes and
`events.jsonl` contains `sprint_complete`; second test: `POST /abort`
→ closure_check fires, worktrees reaped. Live smoke: `curl
--max-time 5` a real 1-BL sprint; sprint must finish.
**Rollback:** `detached` flag off = today's behavior verbatim; revert
is one commit dropping the registry.
**Effort:** ~2 days.

---

## Batch 2 — C4: repair the senses

**Invariant:** I-2 (signal quality is part of the doctrine contract),
I-5 (no label more optimistic — or more *pessimistic* — than reality).

### 2-1 A39a/b — gate parser stops lying

`regression_gate.py`:

- Build/lint sentinel scan of `post_tail` (`tests/gate::build FAILED`,
  `lint_typecheck_build FAILED`, tsc/biome/ruff error blocks) →
  `kind="build_fail"` (new), `regressions=[]`, `reason` carries the
  actual compiler/linter error block (truncated to the error, not
  container noise), new field `gate_failure_class ∈
  {build, lint, test, infra}`.
- Invariant assertion (39b): `kind=="regressed"` requires
  `len(regressions) + len(new_failures) > 0`; otherwise downgrade to
  `inconclusive` with `post_tail`. An empty list with a positive count
  can never be emitted again.
- `build_gate_fix_prompt` switches on `gate_failure_class`: build
  failures get "the build doesn't compile, here is the error" instead
  of 161 test names; lint failures get the A40 auto-fix clause
  ("run the formatter's `--fix` before manual edits").
- Orchestrator retry predicate (`orchestrator.py:480,630`) extends to
  `kind in ("regressed", "build_fail")` — build failures are
  engineer-fixable and should retry, now with correct signal.

### 2-2 A44 wiring — API errors are infra, not incompetence

`orchestrator.py` per-role flows: track `phase=api_error` events from
the agent stream. When an attempt ends with an api_error:

- Do **not** count it against the doctrine/gate retry budget.
- Retry the same attempt with exponential backoff (30s/120s), max 2
  infra-retries per role invocation, emitting
  `phase=infra_retry kind=api_error`.
- If still failing → `awaiting_review reason=api_error` (→ triage in
  Batch 3), never `"engineer did no work"`.

### 2-3 A45 — busy ≠ idle

`claude_agent.py`:

- Track in-flight tools: a `tool_use` id with no matching
  `tool_result` yet ⇒ agent is *busy*. While ≥1 tool is in flight, the
  idle clock is suspended (wall timeout still applies). ~25 LOC in the
  event loop; the tool_result ids are already in the stream.
- Doctrine side (R14.3 extension, engineer/QA SKILLS.md): never
  self-run the full regression gate; no silent blocking wait loops —
  emit periodic progress if a wait is unavoidable. (2-1 removes the
  *need* to self-diagnose, per the A39→A45 causal chain.)

### 2-4 Small-defect sweep (files as one commit each)

| Fix | Change |
|---|---|
| A54 | Record base SHA at `create_worktree`; `has_new_commits` counts `<base_sha>..HEAD` |
| A55 | `_resolve_engineer_section` raises structured `backlog_section_missing` abort event when `extract_section` returns None (per-BL failure → Batch 3 triage, not a garbage prompt) |
| A56 | `--model` from new `AGENT_MODEL` env/config; model id recorded in trace `meta.json` next to `harness_sha` |
| A57 | Retrieval budget enforced MCP-server-side (tool returns a budget-exhausted *error result*, agent continues with what it has); harness kill retained only as 2× backstop |

**Risk:** low-medium; 2-1 touches the live gate classifier (the A21/A25
lesson: classifier changes need negative controls). **Named tests:**
2-1: fixture post_tails from the three real incidents (documents_2
BL-0008 "161 regressions", time-tracking BL-0014 empty-regressions,
biome lint case) → assert `build_fail` / `inconclusive` / lint class
respectively; property test: regressed ⇒ non-empty list. 2-2: stub
agent emitting api_error → assert doctrine attempt counter unchanged,
infra_retry emitted. 2-3: stub stream with tool_use then 700s silence
then tool_result → no kill; silence with *no* in-flight tool → kill at
600s. **Rollback:** each sub-item is one revertible commit;
`gate_failure_class` is additive (consumers ignore unknown fields).
**Effort:** ~2–3 days total.

---

## Batch 3 — C2: judgment between "retry" and "kill everything"

**Invariant:** I-5, I-6; delivers ABL-0002 (v1 scope).

### 3-1 Dependency-aware scheduling (mechanical; ships first)

`orchestrator.py` per-BL loop:

- Maintain `merged: set[str]` (outcomes `merged_*` or `no_op`).
- Before dispatching a BL, check `deps ⊆ merged`. Unmet → emit
  `bl.skipped kind=dep_unmet deps_missing=[...]`, outcome
  `deferred_dep`, continue. Dependents of a failure no longer build on
  air.
- `sprint_complete` summary gains a `deferred` section (worst-wins
  aggregate per I-5 — a sprint with deferrals is labeled
  `complete_with_deferrals`, never bare success).

### 3-2 Triage agent v1 (bounded scope)

- New role: `skills/brownfield/brownfield-production-incremental-triage/SKILLS.md`
  + `prompts_brownfield.py` wiring (mirrors doctrine-meta's shape,
  including `forbidden_tools` from day one — A14 lesson).
- `_triage_flow(bl_id, failure_context)` invoked wherever the loop
  today hits `engineer_unmerged` / `qa_merge_failed` /
  `awaiting_review`. Inputs: the BL's phase_events, gate result
  (with Batch-2 `gate_failure_class`), doctrine summary, worktree
  branch state. Output — exactly one of:
  - `RETRY_REWRITE` — one extra engineer spawn with the triage
    agent's written meta-prompt (hard cap: 1 triage-granted retry per
    BL, so worst case adds one attempt);
  - `DEFER` — outcome `deferred_triage` + written justification;
    dependents auto-defer via 3-1;
  - `ESCALATE` — one precisely-framed question written to
    `_brownfield/features/<slug>/escalations/<bl>.md` + event; sprint
    continues past the BL (does not block).
  - **SPLIT is out of v1 scope** (needs PO-grade decomposition;
    revisit after ABL-0006).
- Decision recorded to `_brownfield/<feature>/<BL>/triage.md` (I-3:
  durable, in the sealed artifact tree).
- New doctrine rule **R16**: triage decides at most once per BL per
  sprint; enforcement = dispatch-site state check; test = re-invoke
  flow, assert zero second spawn (same shape as R15). Lands with
  enforcement + test per I-2.

### 3-3 Policy defaults (operator decision D1)

With 3-1 + 3-2 in place, `stop_on_failure=True` stops being the only
safe policy. Proposed new default: `stop_on_failure=False` **only
after** one clean calibration sprint with triage ON. Flag-gated:
`run_triage: bool = False` until calibrated (same discipline as
ABL-0014/0015).

**Risk (explicit):** medium — triage is a new agent with authority over
control flow. Mitigations: decisions are enum-constrained + validated
(free-text can't route); retry cap 1; DEFER is the fallback on any
validator failure of the triage artifact itself; flag OFF by default.
**Named test:** synthetic sprint with a planted always-failing BL-0002
that BL-0003 depends on → assert BL-0003 `deferred_dep`, BL-0004
(independent) merges, sprint completes with `complete_with_deferrals`;
triage e2e: planted `build_fail` context → triage returns
RETRY_REWRITE with a meta-prompt naming the build error.
**Rollback:** `run_triage=False` + revert 3-1's scheduling commit
restores today's behavior exactly.
**Effort:** ~3–4 days.

---

## Batch 4 — C3: quality with teeth

**Invariant:** I-5; addresses A50.

### 4-1 Scorer verdict enters control flow

- Parse verdict + total from the scorecard (parsers already exist:
  `doctrine_validator.py:559,600` — reuse, don't duplicate).
- `bl.done` carries `score_total` + `score_verdict`.
- On `Fail` verdict: emit `score_failed`, route the BL to triage
  (Batch 3) with the scorecard as context. v1 consequence is
  triage-or-escalate, **not** auto-revert.
- Sprint summary aggregates scores worst-wins; `sprint_complete`
  carries `min_score` / `mean_score`.

### 4-2 Orchestrator-owned revert primitive

- `git_worktree.revert_bl_span(repo_root, bl_id, agent_branch)`:
  identify the BL's commit span on `agent_branch` (subjects match
  `^(eng|qa)\(<bl>` / `^BL-NNNN`), `git revert --no-edit` them in a
  disposable worktree, gate the revert branch (existing `run_gate`),
  FF-merge on green. The orchestrator owns refs (R13 boundary
  preserved — agents never call this).
- Exposed as operator-gated `POST /api/projects/{repo}/revert-bl
  {bl_id, confirm:true}`. **No automatic invocation in v1** (D2).
- This is the missing half of ABL-0015's loop: acceptance
  `product_bug` findings on a specific BL now have a *backward* remedy
  as well as the forward-fix dispatch.

### 4-3 Pre-merge QA — decision only, no build

Restructuring to QA-before-merge changes the "every merge is
production-ready" contract and roughly doubles branch lifetime.
Presented as operator decision **D3** with the architect's
recommendation: **do not restructure now** — 4-1 (fail→triage) + 4-2
(revert) + acceptance agent give equivalent protection at far lower
disruption. Revisit if reverts become frequent (>1/sprint over 3
sprints — measurable via 5-3 telemetry).

**Risk:** 4-2 medium (ref surgery) — mitigated by disposable-worktree +
gate-before-merge + operator `confirm:true`; 4-1 low (additive).
**Named test:** 4-1: fixture scorecard with Fail verdict → `score_failed`
emitted, triage invoked; 4-2: seed repo with 2-commit BL + dependent
commit on top → revert span produces gate-green branch, FF lands,
feature code gone, dependent intact (and a conflict case → structured
`revert_conflict` error, no mutation). **Rollback:** both additive;
one revert each. **Effort:** ~2–3 days.

---

## Batch 5 — C5: economics

**Invariant:** I-1 (bounded resource consumption is lifecycle
ownership); delivers ABL-0013 minimal core + A28/A29.

| ID | Item | Detail | Effort |
|---|---|---|---|
| 5-1 | A28 playwright workers | `--workers 4 --retries 1` in the target's `regression_gate.sh` (target-side commit; PF-10 check updated) | 1 line |
| 5-2 | A29 PRE-baseline cache | Cache `TestSet` keyed `(target_ref_sha, hash(test_cmd))` in `.gate-cache/<key>.json`; on hit, skip the entire PRE worktree+stack+run. Invalidation is automatic — any merge moves `target_ref_sha`. TTL 24h backstop. Kills ~50% of gate wall-time after the first BL | ~60 LOC |
| 5-3 | Cost aggregation | Sum `total_cost_usd` from result frames per role → `bl.done cost_usd`, `sprint_complete total_cost_usd` + per-role breakdown; persisted in A7 state | ~40 LOC |
| 5-4 | Sprint budget cap | `max_sprint_usd: float \| None` on `RunBriefRequest`; checked between BLs (never mid-BL): over cap → remaining BLs `deferred_budget`, sprint completes-with-deferrals honestly (I-5) | ~25 LOC |
| 5-5 | A30 TIA / A31 tiered gate | **Explicitly deferred** — re-evaluate after 5-1/5-2 measurements; TIA's under-inclusion risk isn't worth taking before triage exists to catch escapes | — |

**Risk:** 5-2 is the only real one (stale-cache false-green). Mitigations:
key includes exact target SHA; cache write only on parseable, completed
PRE runs; `gate.pre_cache_hit` event makes every hit auditable.
**Named test:** 5-2: two consecutive gates on unchanged target → second
emits `pre_cache_hit` with identical `pre` dict; merge a commit →
cache miss. 5-4: 3-BL synthetic sprint with cap below BL-2's cost →
BL-3 `deferred_budget`. **Benefit proof:** wall-clock of an identical
sprint before/after (the A28 test plan, extended). **Rollback:** cache
bypass flag; budget cap default None. **Effort:** ~2 days.

---

## Batch 6 — M1: memory (within-sprint first)

**Invariant:** I-7 adjacent; first concrete step toward the thesis's
*cumulative* property. Deliberately smaller than ABL-0007.

### 6-1 Sprint lesson log

- When a doctrine or gate retry **resolves** (fail→pass transition),
  the orchestrator appends a structured lesson to
  `_brownfield/features/<slug>/LESSONS.jsonl`:
  `{bl_id, phase, failure_class, lesson}` — where `lesson` is
  extracted from the fix that worked (gate: first regression +
  `gate_failure_class`; doctrine: the missing-item list).
- Prompt builders inject the last N (=10) lessons into engineer/QA
  prompts as a "Lessons already paid for in this sprint" block
  (~15 LOC in `prompts_brownfield.py`; token cost ~1KB).
- The BL-0001-learns-migration-naming → BL-0004-relearns-it loop
  closes at near-zero cost.

### 6-2 Sprint-close export

- `sprint_complete` writes `LESSONS.jsonl` summary into the acceptance
  dir + doctrine-meta prompt context (the meta-agent currently mines
  raw traces; lessons are pre-distilled signal for it).
- Cross-sprint / cross-target memory remains **ABL-0007** (unchanged,
  separately scheduled); this batch feeds it clean input later.

**Risk:** low — additive artifacts + prompt block. Prompt-bloat guard:
hard cap N=10, each lesson ≤200 chars. **Named test:** synthetic sprint
where BL-0001 resolves a gate retry → assert BL-0002's engineer prompt
contains the lesson block; measurable acceptance criterion (A16
style): repeat-failure rate of the same `gate_failure_class` within a
sprint drops on the next real run. **Rollback:** remove the prompt
block; files are inert. **Effort:** ~1 day.

---

## Batch 7 — M2/M3/M4: deployment-grade hygiene

### 7-1 M2 — main-checkout invariants become code (A51)

- Run-start preflight (in `run_brief`, before `index_initial`):
  assert target checkout is on `cfg.agent_branch` and
  `status --porcelain --untracked-files=no` is clean; else abort
  with `pre_flight.checkout_dirty` **before** any agent spawns
  (moves PF-6 from checklist to code).
- `_po_flow` copy-back: replace `check=False` with checked calls +
  post-commit verification (`rev-parse` the new commit; assert the
  backlog path is in it). Failure → structured
  `po_commit_failed` abort (honest early failure instead of
  mysterious downstream doctrine failures).

### 7-2 M4 — retrieval health is checked, not hoped for (A53)

- `_run_indexers` returns ok-flags to the caller; on failure:
  one Milvus restart attempt (reuse the A3 pattern mid-sprint) + one
  re-run; still failing → `infra_fail` route (pause + triage/escalate
  per Batch 3), never silent continuation on stale embeddings.

### 7-3 M3 — secret containment v1 (A52)

- Agent subprocess env becomes an **allowlist**
  (`HOME, PATH, GIT_*, CLAUDE_*`, TERM-class vars) instead of
  `{**os.environ}`. Retrieval-relevant secrets already flow to the MCP
  *server* config separately (`claude_agent.py:157` list) — the agent
  process itself needs none of them.
- `HARNESS.md` gains an explicit trust-model section: target-repo
  content is untrusted input; `--allowedTools` is not a boundary
  (A47); `--dangerously-skip-permissions` scope documented.
- Full sandboxing (container-jailed Bash, egress control) is named as
  the production requirement it is, and **explicitly deferred** to its
  own plan (operator decision D4) — it is a multi-week track and
  should not gate Batches 1–6.

**Risk:** 7-3's allowlist can break agents that legitimately need an
env var (e.g. corporate proxy vars) — mitigate with an operator-extend
`AGENT_ENV_ALLOWLIST` config + one calibration sprint watching for
env-related failures. **Named test:** 7-1: dirty-checkout fixture →
abort pre-spawn; PO commit blocked by a hook → `po_commit_failed`
within seconds. 7-2: stop Milvus mid-synthetic-sprint → restart
attempt observed, then infra route. 7-3: spawn agent, `env` dump via
its Bash → assert no `AZURE_*`/`OPENAI_*` present. **Rollback:** each
one commit; allowlist has a `AGENT_ENV_PASSTHROUGH_ALL=1` escape hatch
for emergency rollback without redeploy. **Effort:** ~2 days.

---

## 8. What this plan deliberately does NOT do

- **No SPLIT triage outcome, no Sprint-Planner re-planning loop** —
  both need PO-grade judgment (ABL-0006 territory).
- **No pre-merge QA restructure** (D3 — recommended against for now).
- **No auto-revert** — revert is operator-gated in v1 (D2).
- **No full sandbox** (D4 — separate track).
- **No changes to ARCHITECT_PLAN Batches C/D/E/G** — framework-reviewer,
  observer, doctrine-spec, and governance hygiene remain proposed
  there; Batch E (doctrine-spec + CI meta-test) is *complementary*:
  R16 and the new gate kinds should be registered in the spec if/when
  E lands.

---

## 9. Sequencing, effort, and gates

```
Batch 0 (env + ledger)          ~0.5 d   ── precondition for all test gates
Batch 1 (detached runs)         ~2 d     ── C1
Batch 2 (signal repair)         ~2–3 d   ── C4          [after 1]
Batch 3 (dep-gating + triage)   ~3–4 d   ── C2          [after 2]
Batch 4 (score teeth + revert)  ~2–3 d   ── C3          [after 3]
Batch 5 (economics)             ~2 d     ── C5          [independent after 1]
Batch 6 (sprint memory)         ~1 d     ── M1          [independent after 1]
Batch 7 (hygiene)               ~2 d     ── M2–M4       [independent after 1]
                                ────────
                                ~15–18 focused days
```

**Calibration discipline** (same as ABL-0014/0015): Batches 3 and 4
ship flag-OFF (`run_triage`, auto-consequences), flip only after one
clean calibration sprint each. Batches 1, 2, 5, 6, 7 are
behavior-preserving by default or strictly-additive.

**End-state test (the plan's definition of done):** one live sprint on
the restored target where the operator (a) submits detached, (b)
closes the laptop, (c) a planted flaky BL triages to DEFER with its
dependent auto-deferred, (d) the sprint completes-with-deferrals under
budget, (e) reconnecting replays the full event history, and (f)
`closure_check` reports 0 violations. That run, clean, is the first
honest evidence the crew can be walked away from.

---

## 10. Operator decisions required before build

| # | Decision | Architect recommendation |
|---|---|---|
| D1 | Flip `stop_on_failure` default to False once triage calibrates? | Yes — after 1 clean triage-ON sprint |
| D2 | Revert stays operator-gated, or auto-revert on Fail-verdict + confirmed acceptance finding? | Operator-gated in v1; revisit with ≥3 clean manual reverts |
| D3 | Restructure to QA-before-merge? | **No** for now — 4-1 + 4-2 + acceptance cover it; revisit if reverts >1/sprint |
| D4 | Authorize the sandbox/security track as a separate plan? | Yes, but after Batches 1–3 — it gates org adoption, not crew capability |
| D5 | Auto-resume orphaned runs on backend startup? | No — surface + one-click resume; auto-resume risks double-running a BL |
| D6 | Authorize this plan's batches (all, or a subset/order)? | 0→1→2→3 minimum; 5–7 schedulable opportunistically |

---

*Authored 2026-08-15 from the same-day code audit. Tracker to be
created as `AUTONOMY_HARDENING_TRACKER.md` upon authorization (house
convention: plan is immutable-ish, tracker is live).*
