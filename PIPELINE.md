# Agentic Skills — End-to-End Pipeline (verification)

> **Purpose:** Map the operator-stated 8-step pipeline to existing code paths, flag gaps, and record verification answers. Authoritative reference for the Sprint 2 Orchestrator (ABL-0001) implementation.
>
> **Authoritative target:** `/Users/eugenegoldberg/dev/ai-projects/brownfield-targets/full-stack-fastapi-template` (symlinked at `webapp/backend/repos/full-stack-fastapi-template`).
>
> **Authoritative harness:** the `webapp/` (FastAPI + React + claude CLI subprocess + retrieval MCP). The `langgraph_engine/` directory remains as the original A/B research harness, not the runtime path.

---

## Architecture decision (resolved 2026-05-21)

**Q1 — subprocess-claude vs LangGraph for production multi-agent dev systems?**

**Decision: Hybrid.** Industry consensus (2026):

| Layer | Tool | Why |
|---|---|---|
| Per-agent execution (PO/Engineer/QA/Scorer) | **Claude CLI subprocess** (current `claude_agent.py`) | Proven on Sprint 1 (13 BLs, ~92 mean); inherits corporate OAuth; rich built-in tool surface; works today |
| Multi-agent orchestration (sprint conductor, retries, dependency DAG, escalation) | **LangGraph-style state machine** in Python (new `orchestrator.py`) | Durable state, reducer-based concurrent updates, `interrupt()` for human-in-loop, model-agnostic |

We do **not** rewrite the per-agent path into LangGraph nodes. The orchestrator is a thin durable state machine that calls `stream_agent_task(...)` per role just like the current per-BL endpoints do.

Sources: 2026 Agent Framework Showdown (QubitTool); Anthropic Claude Agent SDK docs; LangGraph vs Claude Code (Lowcode.agency).

---

## The 8-step pipeline → code paths + gap analysis

### Step 1 — Operator submits project brief via webapp; harness kicks off

| Aspect | Today | Gap |
|---|---|---|
| Brief submission endpoint | `POST /api/projects/{repo}/decompose-brief` (PO only) | No single "submit brief & walk away" endpoint — operator runs PO, then per-BL Engineer/QA/Score buttons by hand |
| New endpoint needed | — | `POST /api/projects/{repo}/run-brief` that chains: index → graphify → PO → loop(Engineer→reindex→QA→Score) |
| UI | `webapp/frontend/src/App.jsx` — per-role buttons only | New v2 UI: textbox + "Run pipeline" + live per-step visualization |

### Step 2 — Re-index brownfield codebase via claude-context / Milvus

| Aspect | Today | Gap |
|---|---|---|
| Endpoint | `POST /api/projects/{repo}/index/claude-context` exists | Not auto-invoked at brief submission |
| Incremental? | claude-context-core bridge supports it natively (re-index → diff & upsert) | Confirmed: re-running `op:index` does not lose existing vectors; only updates changed files |
| Trigger | Manual button | Orchestrator must call this as Step 2 of the brief flow |

### Step 3 — Graphify graph build

| Aspect | Today | Gap |
|---|---|---|
| Endpoint | `POST /api/projects/{repo}/index/graphify` exists | Not auto-invoked |
| Incremental? | `graphify update <repo> --no-cluster` is incremental by design (tree-sitter delta) | Confirmed |
| Trigger | Manual button | Orchestrator must call this as Step 3 |

### Step 4 — PO agent: decompose brief → BACKLOG + sprint plan

| Aspect | Today | Gap |
|---|---|---|
| Endpoint | `POST /api/projects/{repo}/decompose-brief` | Works (proven on Sprint 1). Produces `.agile-v/BACKLOG.md`, `_brownfield/_codebase_context/CODEBASE_CONTEXT.md`, sprint plan, per-BL `codebase_context.md` |
| SKILLS.md adherence | Enforced via prompt + doctrine validator R1–R12 | OK |

### Step 5 — Submit first BL to Engineer; strict SKILLS.md adherence

| Aspect | Today | Gap |
|---|---|---|
| Endpoint | `POST /api/projects/{repo}/execute-bl` | Works |
| SKILLS.md | `skills/brownfield/brownfield-production-incremental-engineer/SKILLS.md` injected into prompt; doctrine validator enforces R5/R5b/R10.1/Tier 1.5 etc. | OK |
| BL selection | Manual (`bl_id` in request) | Orchestrator picks next ready BL from dependency DAG |

### Step 6 — Re-index + graph update after Engineer commits

| Aspect | Today | Gap |
|---|---|---|
| Auto-trigger after engineer merge | **Not implemented** | Orchestrator must call `index/claude-context` + `index/graphify` after each ff-merge to `agent_branch` |
| Why needed | QA agent's retrieval must see the engineer's new code, not stale embeddings | Critical correctness fix |

### Step 7 — QA brings up backend+frontend + tests in prod-like env

| Aspect | Today | Gap |
|---|---|---|
| Regression gate v3 (verified) | `target_repo/scripts/regression_gate.sh` brings up full docker compose (db + mailcatcher + backend + frontend), waits for healthchecks, runs backend pytest in-container, then Playwright E2E against the live stack | ✅ Satisfies "test like production users would" |
| QA agent endpoint | `POST /api/projects/{repo}/qa-bl` | Works; gate fires automatically post-commit |
| Trigger | Manual button | Orchestrator triggers QA after engineer merge + re-index |

### Step 8 — Scorer; loop until backlog complete

| Aspect | Today | Gap |
|---|---|---|
| Scorer endpoint | `POST /api/projects/{repo}/score-bl` | Works |
| Loop across all BLs | **Not implemented** — currently a bash `nohup` chain launcher per BL | **This is ABL-0001 Orchestrator** |

---

## Verification answers (from operator, 2026-05-21)

1. **Subprocess vs LangGraph** — Hybrid (decided above).
2. **Incremental indexing OK** — Yes, provided no original knowledge is lost and new is added. Both providers satisfy this.
3. **QA prod-like testing** — Regression gate v3 satisfies the requirement (full docker stack + Playwright E2E).
4. **Output of this turn** — Doc + start filling ABL-0001 immediately.
5. **Branch + UI** — New branch `sprint-2-orchestrator`. Preserve current UI as v1; add v2 UI for brief submission + step-by-step live visualization.

---

## ABL-0001 Orchestrator — implementation contract

**New file:** `webapp/backend/app/services/orchestrator.py`

**New endpoint:** `POST /api/projects/{repo}/run-brief` (single-shot, brief → merged feature)

**Request shape:**
```json
{
  "brief": "Add multi-tenant billing with Stripe...",
  "project_name": "billing",
  "timeout_seconds_per_role": 2400,
  "max_bls": null,
  "sprint": "C1"
}
```

**Pipeline (durable state machine — each transition emits SSE):**

```
1. preflight       → retrieval health, repo dir, .agentic-skills.json
2. index_initial   → claude-context + graphify (parallel)
3. po              → decompose-brief flow (existing)
4. backlog_parsed  → emit ordered DAG
5. for each BL in dependency-topological order:
     5a. engineer       → execute-bl flow (existing, with R10.1 retries + gate)
     5b. on no_op / awaiting_review → emit + skip-or-stop per policy
     5c. on merged       → reindex (incremental)
     5d. qa              → qa-bl flow
     5e. on merged       → reindex (incremental)
     5f. scorer          → score-bl flow
6. sprint_complete → final summary event
```

**State persisted to disk** (`webapp/backend/.orchestrator-state/<run_id>.json`) so a process restart can resume.

**SSE event prefix:** all orchestrator events carry `phase=orchestrator.<step>` so the new UI can render a timeline.

**Replaces:** all `nohup bash -c 'until grep ...'` chain launcher patterns from Sprint 1.

---

## Out of scope for ABL-0001 (deferred to later ABLs)

- Triage on `awaiting_review` (ABL-0002) — for now, orchestrator stops the sprint and surfaces the failure
- Doctrine self-hardening (ABL-0003)
- Slack escalation (ABL-0004)
- Sprint planning from product intent (ABL-0006) — operator still provides a textual brief; PO does the decomposition
- Cross-project memory (ABL-0007)
- Concurrency (ABL-0011)

---

## UI v2 scope (this branch)

- Preserved: current `App.jsx` as `AppV1.jsx`, accessible via `?v=1` query param or `/v1` route
- New: `AppV2.jsx` as default at `/`
- Layout:
  - Top: project brief textarea + repo dropdown + "Run pipeline" button
  - Middle: vertical timeline of pipeline stages with live status (pending / in-progress / done / failed)
  - For each BL row: nested sub-timeline (Engineer / Reindex / QA / Reindex / Scorer)
  - Right rail: latest SSE event detail / retrieval call counts / costs
  - Bottom: full event log (collapsible)

The v2 UI subscribes to a single SSE stream from `POST /run-brief` and routes events into the timeline structure by `phase` + `bl_id`.

---

*Document version 1.0 — 2026-05-21*
