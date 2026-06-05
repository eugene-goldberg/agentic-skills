# Control-flow map — checks, gates & control actions

> Visual companion to the R-rules table (CLAUDE.md), the doctrine-spec
> registry (`webapp/backend/app/services/doctrine_spec.py`, I-2) and
> `WORKFLOW.md`. Every rule shown maps to a real enforcement point.
> Generated 2026-06-04.

Two enforcement layers:
- **Streaming-time (Tier 1.5)** — the harness reads the agent's `stream-json`
  live and **kills the subprocess** before it can do harm.
- **Post-agent gates** — after the subprocess returns, the orchestrator runs
  validators/gates and **blocks the merge** unless they pass.

Plus **sprint-level** checks (pre-flight, acceptance, closure, doctrine-meta).

```mermaid
flowchart TD
    %% ---------------- sprint entry ----------------
    PF["Pre-flight disk check (A48)<br/>run_brief router · advisory/409"]
    LK{"B2 concurrency lock<br/>free for this repo?"}
    C409["HTTP 409 — run in progress"]
    IDX["index_initial<br/>graphify + claude-context"]
    PO["PO agent — decompose brief<br/>→ BACKLOG.md + codebase_context.md"]
    PF --> LK
    LK -- no --> C409
    LK -- yes --> IDX --> PO --> ENG

    %% ---------------- per-BL pipeline ----------------
    subgraph BLP["per-BL pipeline — runs for ENGINEER, then QA"]
      direction TD
      ENG["ENGINEER agent runs"]
      EDOC{"Doctrine validator<br/>R10.1 · R5 grounding≥3 · R5b citations<br/>artifacts ≥120B present?"}
      EGATE{"Regression gate (R10/R10.2)<br/>2 worktrees off target_ref<br/>build · fe-lint · pytest · e2e"}
      EMERGE{"fast-forward into<br/>agent_branch?"}
      REBASE["A1 auto-rebase onto target_ref<br/>+ re-run gate"]
      RIDX1["reindex_after_engineer"]
      QA["QA agent runs"]
      QDOC{"Doctrine validator (QA)<br/>R10.1 · R5b"}
      QGATE{"Regression gate (QA)"}
      QMERGE["merge + reindex_after_qa"]
      SCORE["SCORER agent — R7 rubric<br/>5 brownfield axes; axis≤2 → Fail (signal)"]
      BLDONE["bl.done(outcome)<br/>merged_full · merged_no_qa · engineer_unmerged · no_op"]

      ENG --> EDOC
      EDOC -- "incomplete (≤2 retries)" --> ENG
      EDOC -- give_up --> UNMERGED
      EDOC -- complete --> EGATE
      EGATE -- "regressed/inconclusive (≤2 retries R10.2)" --> ENG
      EGATE -- "still failing" --> UNMERGED
      EGATE -- green --> EMERGE
      EMERGE -- non_ff --> REBASE --> EMERGE
      EMERGE -- conflict --> ESC["escalate to operator"]
      EMERGE -- "ff / ok" --> RIDX1 --> QA --> QDOC
      QDOC -- "incomplete (≤2)" --> QA
      QDOC -- complete --> QGATE
      QGATE -- "fail (≤2)" --> QA
      QGATE -- green --> QMERGE --> SCORE --> BLDONE
    end

    UNMERGED["branch left unmerged<br/>→ ⚠ Review &amp; merge (operator, AppV2)"]

    BLDONE --> MOREBL{"more BLs?"}
    MOREBL -- yes --> ENG
    MOREBL -- no --> SC["sprint_complete"]

    %% ---------------- sprint-level ----------------
    SC --> ACC["Acceptance pass (ABL-0014)<br/>E2E journeys on the ASSEMBLED branch<br/>+ acceptance validator (R10.1-style)"]
    ACC --> FIND{"findings persisted?"}
    FIND -- yes --> TRIAGE["operator triage<br/>confirm / refute / defer"]
    TRIAGE --> DISP{"confirmed product_bug?<br/>R15 dispatch-at-most-once"}
    DISP -- "🛠 Dispatch fix" --> FUP["follow-up engineer<br/>SAME doctrine + gate + merge bar"]
    FUP --> FUPM{"merged?"}
    FUPM -- not_merged --> RM["⚠ Review &amp; merge (operator)<br/>→ A50 ledger sync"]
    FUPM -- merged --> CLOSE
    FIND -- none --> CLOSE
    RM --> CLOSE
    CLOSE["closure_check (I-3)<br/>0 worktrees / branches / run containers"]
    CLOSE --> META["doctrine-meta agent (I-7/ABL-0003)<br/>PROPOSES doctrine changes → .planning<br/>(operator approves; never auto-applies)"]

    %% ---------------- streaming controls (every agent) ----------------
    subgraph TIER["Streaming controls (Tier 1.5) — live, KILL the agent mid-run · claude_agent.stream_agent_task"]
      direction LR
      T5["R5 / Tier1.5<br/>&lt;3 grounded calls<br/>before Write/Edit"]
      T8["R8<br/>&gt;30 retrieval calls"]
      T13["R13<br/>forbidden git cmd<br/>(FORBIDDEN_GIT_RE)"]
      TB5["B5<br/>idle / wall timeout"]
      T12["R12<br/>scorer grounding floor"]
    end
    PO -. guarded by .-> TIER
    ENG -. guarded by .-> TIER
    QA -. guarded by .-> TIER
    SCORE -. guarded by .-> TIER

    %% ---------------- styling ----------------
    classDef kill fill:#3b1f1f,stroke:#a33,color:#fff;
    classDef gate fill:#3b2f1f,stroke:#c93,color:#fff;
    classDef op fill:#1f2a3b,stroke:#39c,color:#fff;
    classDef ok fill:#1f3b1f,stroke:#6a6,color:#fff;
    classDef quality fill:#2a2a2a,stroke:#888,color:#fff;
    class TIER,T5,T8,T13,TB5,T12 kill;
    class EDOC,EGATE,QDOC,QGATE,EMERGE gate;
    class TRIAGE,DISP,RM,ESC,UNMERGED,C409 op;
    class BLDONE,SC,QMERGE ok;
    class SCORE,ACC,META,FIND quality;
```

## Legend — who enforces what

| Color | Meaning | Examples |
|---|---|---|
| 🔴 red | **Streaming kill** (automatic, mid-run) | Tier 1.5 / R5, R8, R12, R13, B5 |
| 🟠 orange | **Post-agent gate** (automatic, blocks merge) | doctrine validator (R10.1), regression gate (R10/R10.2), FF check (A1) |
| ⚪ gray | **Quality / advisory** (signal, not a block) | scorer rubric R7, acceptance, coverage, R9 (unenforced) |
| 🔵 blue | **Operator-gated** (never automatic) | Review & merge, verdicts, Dispatch fix, doctrine approval, skip_gate |
| 🟢 green | terminal / success states | bl.done(merged_full), sprint_complete |

## Enforcement points (from the I-2 registry)

| Rule | Where | Enforced |
|---|---|---|
| R5 grounding floor | `doctrine_validator:_count_grounded_retrieval` (post) + Tier 1.5 (streaming) | ✅ |
| R5b citations | `doctrine_validator:_check_citations` (post) | ✅ |
| R7 rubric self-consistency | `doctrine_validator:validate_scorer` (post) | ✅ (signal) |
| R8 retrieval budget | `claude_agent:MAX_RETRIEVAL_CALLS_DEFAULT` (streaming) | ✅ |
| R9 ≥1 graph_* call | streaming | ❌ advisory gap (A8) |
| R10 / R10.2 gate retries | `orchestrator:_engineer_flow` | ✅ |
| R10.1 doctrine retries | `orchestrator:_qa_or_scorer_flow` | ✅ |
| R11 no-op short-circuit | `doctrine_validator:validate_engineer` | ✅ |
| R12 scorer grounding | `claude_agent:stream_agent_task` (streaming) | ✅ |
| R13 no history-rewrite git | `claude_agent:FORBIDDEN_GIT_RE` (streaming) | ✅ |
| R15 dispatch-at-most-once | `orchestrator:_select_followup_candidates` | ✅ |
| Tier 1.5 pre-mod kill | `claude_agent:stream_agent_task` (streaming) | ✅ |

> The registry + a CI consistency test keep this map honest: a documented
> R-rule with no enforcement point + resolvable check fails the build.
