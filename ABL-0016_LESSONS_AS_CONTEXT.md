# ABL-0016 — Lessons-as-context (cumulative learning, Stage 1)

> **Status: DRAFT plan, operator approval required before implementation.**
> Author: architect. Date: 2026-06-02. Branch: `cumulative_learning`.
> Implements **Stage 1** of [`CUMULATIVE_LEARNING_ROADMAP.md`](CUMULATIVE_LEARNING_ROADMAP.md).
> Dependency: ABL-0014 §I.3 findings ledger — **satisfied** (shipped).
>
> Grounded in a verification pass of the retrieval/prompt seams at the
> `cumulative_learning` tip. Every file:line below was confirmed against
> the working tree on 2026-06-02.

---

## 1. What this closes — and why it's the highest-leverage cumulative move

Per the roadmap, the single biggest cumulative-learning gap is the **read
path**: the crew accumulates findings but no agent consults them at
decision time. The §I.3 findings ledger is read by exactly **one** role
(the acceptance agent, via priors injection). The PO, engineer, QA, and
scorer read nothing. An engineer about to edit `billing/invoices.py` has
no idea a confirmed `product_bug` shipped there on a prior feature.

ABL-0016 closes that gap: surface **prior confirmed lessons** to every
role as advisory context, so the crew's hard-won findings become inputs to
future work — "what's learned on one target carries forward," within a
target.

## 2. Verified seam (the verification pass)

### 2.1 Prompt-injection seam — clean, all four roles ready

The brownfield prompt builders already receive `repo_dir` + `feature_slug`
at their call sites, so a lessons block can be assembled at build time:

| Role | build call site (orchestrator.py) | builder + insertion seam (prompts_brownfield.py) |
|---|---|---|
| PO | `build_po(...)` `:290` | `build_po_prompt_brownfield` — after `{skills_md}` (`:124`) |
| Engineer | `build_engineer(...)` `:422` | `build_engineer_prompt_brownfield` — after `{skills_md}` (`:286`) |
| QA | `build_qa(...)` `:574` | `build_qa_prompt_brownfield` — after `{skills_md}` (`:430`) |
| Scorer | `build_score(...)` `:576` | `build_score_prompt_brownfield` — after `{RETRIEVAL_HINT_BROWNFIELD}` (`:526`) |

### 2.2 The proven analog — `_build_priors_block`

`_build_priors_block(repo_dir, feature_slug)` (orchestrator.py:962-1023)
is the exact template: reads the findings ledger, returns a markdown block
(silent empty string when no data), interpolated into the acceptance
prompt at `_build_acceptance_task` (`:1112` build, `:1145` interpolate),
gated by `inject_acceptance_priors` (default OFF). ABL-0016 mirrors this
shape for a `_build_lessons_block` shared by all four roles.

### 2.3 Retrieval store — Option B mapped, deferred

The retrieval MCP server (`mcp_servers/retrieval_server.py`) exposes
`semantic_search` over a **per-target** Milvus collection
(`code_chunks_<md5(repo_path)[:8]>`), indexed by the claude-context bridge
(`app/services/indexing.py::run_claude_context_index`). Lessons *could* be
indexed into a parallel `lessons_<md5>` collection with a sibling
`search_lessons` tool — but that's a larger surface (new collection,
new MCP tool, free-text schema, ranking union). **Deferred to a follow-up
(Stage 1.5).** See §4 decision.

### 2.4 The scope insight that shapes v1

The findings ledger is keyed **per `feature_slug`**
(`_brownfield/features/<slug>/acceptance/findings_log.jsonl`) and is
populated by acceptance at **sprint end**. Therefore feature-scoped
lessons are nearly useless *within* a sprint (every engineer runs before
acceptance writes anything). The real value is **cross-feature,
same-target**: feature B benefits from feature A's confirmed findings.

**=> v1 is TARGET-scoped:** the lessons reader unions confirmed/deferred
findings across *all* feature ledgers in the target
(`_brownfield/features/*/acceptance/findings_log.jsonl`), optionally
ranking same-feature lessons higher. Cross-*target* (different repos) is
roadmap Stage 3, out of scope here.

## 3. v1 design — Option A (prompt-injection), target-scoped

**Lesson source (v1):** the findings ledger only — findings with
`verdict in {confirmed, deferred}` (real bugs worth remembering; exclude
`refuted` = false positives and `None` = untriaged). Other roadmap sources
(recurring gate failures, accepted doctrine rules, blast-radius hotspots)
are explicitly **out of v1 scope** — added as later batches once the read
path proves its value.

**Reader (target-scoped):**
```
lessons_svc.list_lessons(repo_dir, feature_slug=None) -> list[Lesson]
  # glob _brownfield/features/*/acceptance/findings_log.jsonl
  # keep verdict in {confirmed, deferred}
  # dedup by finding_id; rank: same feature_slug first, then by seen_count
```

**Renderer (shared, silent-when-empty, mirrors _build_priors_block):**
```
render_lessons_block(lessons, *, role, bl_id=None, cap=N) -> str
  # "## Relevant prior lessons (advisory)" + per-lesson:
  #   classification · feature · summary · (hypothesis site if present)
  # "" when no lessons (no prompt noise)
```

**Advisory framing (critical):** the block is explicitly *evidence to
weigh, not rules that bind* — same "falsification priors, not bans"
language §I.3 established. The agent must still ground its own retrieval;
a lesson is a pointer, not a verdict.

## 4. Operator decisions (gray areas)

**D1 — Option A now, Option B later?** *Recommendation: yes.* Ship A
(prompt block) as v1; it closes the read-path gap for all roles at
near-zero risk and reuses the §I.3 pattern. Graduate to B (semantic
lessons retrieval, files-in-scope relevance) only once the lessons store
proves valuable and we want relevance ranking by symbols-in-scope.

**D2 — flag default.** The roadmap argues lessons-as-advisory *can* be
un-gated. *Recommendation: still ship behind `inject_lessons: bool =
False`* and flip after one calibration smoke — consistent with the
discipline used for `run_acceptance`, `inject_acceptance_priors`,
`run_acceptance_followup`. Cheap insurance; flip is one line.

**D3 — which roles.** *Recommendation: all four* (PO, engineer, QA,
scorer). PO gains "this target's recurring failure modes" at planning;
engineer/QA gain per-area hazard pointers; scorer gains context for
judging blast radius. Low marginal cost once the helper exists.

## 5. Invariant analysis

- **I-2 (doctrine contract):** lessons are advisory context, **not** a new
  R-rule — no enforcement point needed. (Contrast R15 for auto-dispatch.)
  No new rule lands here.
- **Grounding property (mature):** this *extends* it — lessons are
  additional evidence in the same advisory spirit as retrieval, and the
  injection is logged for later efficacy measurement (Stage 2 hook).
- **I-4 (run identity):** lessons carry their source `finding_id` +
  `feature_slug` so any action they influence is traceable.
- No subprocess/closure (I-1/I-3) impact — pure prompt assembly + file
  reads. No new executor, no new worktree, no new docker.

## 6. Batches

| Batch | Scope | Test gate |
|---|---|---|
| **A — lessons reader + renderer** | New `lessons.py` svc: `list_lessons` (target-scoped union over feature ledgers, verdict filter, dedup, rank) + `render_lessons_block` (silent-empty). Dormant — zero call sites. | unit tests: union across multiple feature ledgers; verdict filter (confirmed/deferred in, refuted/pending out); dedup; same-feature ranking; empty → "" |
| **B — wire into 4 role prompts + flag** | `inject_lessons: bool = False` through `RunBriefRequest` → `run_brief` → the four `build_*` calls; thread the rendered block into the four brownfield builders at the verified seams; advisory framing text. | wiring tests (flag default/plumb, mirrors test_followup_flag_wiring); per-role injection present when flag on + lessons exist, absent when off/empty |
| **C — provenance + live calibration smoke** | **Provenance SHIPPED** (architect half): `lessons.record_injection` writes a per-run `logs/lessons/<run_id>.jsonl` of which lessons were injected per role/bl_id (the hook Stage 2 consumes); the three flows call it when `inject_lessons` is on. **Remaining (operator-gated):** run one sprint with `inject_lessons=true` on a target with prior confirmed findings, confirm blocks render + provenance written + no regression, then flag-flip proposal. | provenance unit-tested; smoke operator-gated |

Batches A+B ≈ 1–1.5 days. Batch C is the operator-gated calibration.

## 7. Calibrated proposal (risk / test / rollback)

**Risk:** Low. Pure additive prompt context + read-only file globs; no
behavior change with the flag at default OFF. The realistic failure mode
is *prompt bloat / distraction* (too many stale lessons crowding the
prompt) — mitigated by a cap (top-N by rank) and the advisory framing.
A poisoned lesson (operator-confirmed-then-wrong) is bounded because
lessons are advisory, not binding, and the agent still grounds itself.

**Named test that proves benefit:** a reader test that builds two feature
ledgers on one target (feature A with a confirmed `product_bug`, feature B
empty), asserts `list_lessons` surfaces A's finding when building feature
B's engineer prompt — i.e. cross-feature memory works. Plus the per-role
injection tests and `test_lessons_flag_off`.

**Named rollback:** gated by `inject_lessons=False`; rollback = leave the
default (or revert the batch). The reader/renderer are dormant additive
code; the four prompt builders fall back to their current text when the
block is empty.

## 8. Out of scope (this ABL)

- Lesson sources beyond the findings ledger (gate failures, doctrine
  rules, blast-radius) — later batches.
- Option B semantic lessons retrieval (Stage 1.5).
- Cross-target / global crew memory (roadmap Stage 3).
- Closed-loop efficacy measurement (roadmap Stage 2) — Batch C only lays
  the provenance hook.

## 9. Verification items resolved (this pass)

1. Prompt seams + call-site context — **resolved** (§2.1; all four
   builders get `repo_dir`+`feature_slug`).
2. Priors-injection analog — **resolved** (§2.2; `_build_priors_block`
   is the template).
3. Retrieval-store option — **resolved + deferred** (§2.3; Option B
   mapped, not v1).
4. Ledger keying/timing → target-scope requirement — **resolved**
   (§2.4; v1 unions across feature ledgers).

No open technical unknowns block Batch A.
