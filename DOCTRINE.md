# Doctrine — what it is, and where it (and its rules) live

> Reference doc. Written 2026-06-04. Companion to `CLAUDE.md` (R-rules table),
> `CONTROL_FLOW.md` (enforcement flowchart), and `ARCHITECTURE_INVARIANTS.md`
> (the meta-rules that govern doctrine itself).

---

## 1. What "doctrine" is

**Doctrine is the codified body of rules and instructions that governs how the
autonomous crew behaves on a target repo** — the crew's "constitution." It
covers: how agents must *ground* their work in retrieval before changing code,
what *artifacts* each role must produce, how many *retries* are allowed, what
is *forbidden* (e.g. history-rewriting git), how output is *scored*, and how
acceptance *findings* are remediated.

Doctrine comes in two **families**, selected per target by the `doctrine` field
in `<target>/.agentic-skills.json`:

| Family | When | Notes |
|---|---|---|
| **brownfield** | working inside an existing codebase (current target) | adds 5 axes: Pattern Fidelity, Regression Coverage, Characterization Tests, Invariant Preservation, Blast Radius; full regression gate |
| **greenfield** | from-scratch work | regression gate returns `skipped` |

Doctrine has **two expressions**:

1. **Agent-facing doctrine** — prose instructions *injected into the agent's
   prompt*. This is what the agent literally reads. Stored as **`SKILLS.md`**
   files (one per role per family).
2. **Machine-enforced doctrine** — the enumerated, checkable **R-rules** the
   harness enforces automatically (streaming kills + post-agent gates).
   Registered in **`doctrine_spec.py`** (the I-2 single source of truth).

---

## 2. Where doctrine is stored — the map

| Layer | What it holds | Path |
|---|---|---|
| **Agent-facing doctrine (prose)** | the instructions each role reads | `skills/brownfield/brownfield-production-incremental-{po,engineer,qa}/SKILLS.md`, `skills/brownfield/brownfield-acceptance-agent/SKILLS.md`, `skills/brownfield/brownfield-production-incremental-doctrine-meta/SKILLS.md` (greenfield analogs under `skills/{po,engineer,qa}/…`) |
| **Machine registry (I-2 source of truth)** | every R-rule + enforcement point + resolvable check + enforced flag | `webapp/backend/app/services/doctrine_spec.py` (`DOCTRINE_SPEC`) |
| **Human prose table** | the R-rules in readable form | `CLAUDE.md` § "R-rules and Tier-1.5" |
| **Consistency guard** | fails CI if the prose table and the registry drift | `webapp/backend/tests/test_doctrine_spec.py` |
| **Prompt builders** | assemble the agent prompt = role text + `{skills_md}` + webapp contract + grounding | `webapp/backend/app/services/prompts_brownfield.py` (`build_{po,engineer,qa,score}_prompt_brownfield`) |
| **Scoring doctrine (rubric)** | the one scorecard the scorer grades against | `rubrics/production_grade_scorecard_brownfield.md` |
| **Enforcement code** | the checks that actually run | streaming: `app/services/claude_agent.py`; post-agent: `app/services/doctrine_validator.py`, `app/services/regression_gate.py`; control flow: `app/services/orchestrator.py` |
| **Per-run snapshot** | which rules were active for a given run (ABL-0020) | `doctrine_spec.manifest()` → `doctrine_manifest` in A7 state (`.orchestrator-state/<run_id>.json`) |
| **Doctrine evolution** | proposed rule changes mined from sprint traces | `.planning/doctrine_proposals/` (written by the doctrine-meta agent; operator approves) |
| **Meta-doctrine** | the invariants that govern doctrine itself | `ARCHITECTURE_INVARIANTS.md` (esp. **I-2**: every R-rule maps to one enforcement point + one test) |

Flow of one rule through the layers: **authored in `CLAUDE.md`** → **registered
in `doctrine_spec.py`** with an enforcement point + check → **enforced** in
`claude_agent`/`doctrine_validator`/`regression_gate`/`orchestrator` → **taught
to the agent** via the role's `SKILLS.md` → **snapshotted per run** in the
manifest. The CI guard makes the registry authoritative: a rule in the prose
table with no registry entry (or no check) fails the build.

---

## 3. The rules (R-rules) — what each requires & where it's enforced

(From `doctrine_spec.py`; enforcement points are the resolvable checks.)

| Rule | Requires | Enforced at | Enforced? |
|---|---|---|---|
| **R5** | ≥3 grounded retrieval calls before the change is trusted | `doctrine_validator:_count_grounded_retrieval` (post) + Tier 1.5 (streaming) | ✅ |
| **R5b** | citations to retrieval evidence in role artifacts | `doctrine_validator:_check_citations` (post) | ✅ |
| **R7** | rubric self-consistency — a brownfield axis ≤2 forces Fail | `doctrine_validator:validate_scorer` (post) | ✅ (verdict/signal) |
| **R8** | ≤30 `mcp__retrieval__*` calls (budget ceiling) | `claude_agent:MAX_RETRIEVAL_CALLS_DEFAULT` (streaming) | ✅ |
| **R9** | ≥1 `graph_*` call | streaming | ❌ **advisory gap (A8)** |
| **R10** | up to 2 gate retries with a focused fix prompt | `orchestrator:_engineer_flow` | ✅ |
| **R10.1** | up to 2 doctrine retries per role | `orchestrator:_qa_or_scorer_flow` | ✅ |
| **R10.2** | up to 2 retries on gate fail (re-spawn with failure detail) | `orchestrator:_engineer_flow` | ✅ |
| **R11** | no-op short-circuit when the work is already on `agent_branch` | `doctrine_validator:validate_engineer` | ✅ |
| **R12** | scorer grounding floor (Tier-1.5 streaming kill) | `claude_agent:stream_agent_task` (streaming) | ✅ |
| **R13** | no agent-initiated history-rewriting git (rebase / reset --hard / push -f / commit --amend / branch -D …) | `claude_agent:FORBIDDEN_GIT_RE` (streaming) | ✅ |
| **R15** | an acceptance `product_bug` is dispatched at most once | `orchestrator:_select_followup_candidates` | ✅ |
| **Tier 1.5** | pre-modification kill: <min grounded calls before the first Write/Edit | `claude_agent:stream_agent_task` (streaming) | ✅ |

Two enforcement *modes* (see `CONTROL_FLOW.md`): **streaming** rules kill the
agent subprocess live; **post-agent** rules block the merge. R7 produces a
quality verdict (the BL may already be merged); R9 is the one declared
*unenforced* gap.

---

## 4. How doctrine changes (governed evolution)

New/changed rules are **not** hand-edited into enforcement code ad hoc. The
loop (I-7):

1. The **doctrine-meta agent** (`skills/brownfield/…-doctrine-meta/SKILLS.md`)
   runs after `sprint_complete`, mines `traces_archive/<run_id>/`, and writes
   *proposals* to `.planning/doctrine_proposals/`.
2. The **operator approves** — nothing auto-applies.
3. An approved rule lands in **`doctrine_spec.py` + `CLAUDE.md` together**
   (I-2: rule + enforcement point + check, or it fails CI), and its
   agent-facing wording goes into the relevant `SKILLS.md`.

This is why the registry is the keystone: it forces every documented rule to be
real, testable, and per-run auditable.
