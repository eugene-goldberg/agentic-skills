---
name: project-layout
description: "Top-level structure of agentic-skills — two subprojects, three branches, key directories"
metadata: 
  node_type: memory
  type: project
  originSessionId: 2b184b19-1809-4a2e-bad8-ec19ea9ee94c
---

Repo at `/Users/eugenegoldberg/dev/ai-projects/agentic-skills/`.

**Two subprojects:**
1. `langgraph_engine/` — the original LangGraph-based PO/Eng/QA harness invoked via `python -m langgraph_engine run …`. Reads role SKILLS.md files, supports retrieval layer (graph + claude-context-core) when `RETRIEVAL_ENABLED=1`.
2. `webapp/` — FastAPI + React UI that invokes the local `claude` CLI as a subprocess for PO decomposition, per-BL execution, QA, and rubric scoring. See [[doc-pointers]].

**Three branches:**
- `main` — initial harness snapshot
- `skills_with_graphs` — retrieval-layer plan (`docs/SKILLS_WITH_GRAPHS_PLAN.md`), Phase 0-4 implementation, A/B harness scripts
- `webapp` — current working branch for the webapp subproject

**Notable directories:**
- `reference-repos/fastapi-good-patterns/` — curated reference repo (originally from kimi Run #14) used by the retrieval layer's `reference` source.
- `target-repos/lg-graph-test/` — playground target. As of 2026-05-17 contains a complete 18-BL FastAPI app I implemented manually with retrieval. Symlinked into `webapp/backend/repos/lg-graph-test`.
- `runs/`, `ab_runs/` — historical agent run artifacts (scorecards, raw logs).

**Why:** future Claude sessions should orient before editing — knowing which subproject and branch matters because skills+graphs lives only on `skills_with_graphs` while webapp lives only on `webapp`.

**How to apply:** before any non-trivial edit, run `git branch` and `git log --oneline -5` to confirm you're on the right branch.
