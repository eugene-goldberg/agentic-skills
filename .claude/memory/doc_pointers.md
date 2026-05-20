---
name: doc-pointers
description: "Canonical project docs to consult before editing — CLAUDE.md, PROJECT_STATE.md, and the rubric"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 2b184b19-1809-4a2e-bad8-ec19ea9ee94c
---

- `CLAUDE.md` at repo root — short orientation, points at PROJECT_STATE.md. Auto-loaded by Claude Code.
- `webapp/PROJECT_STATE.md` — deep current-state reference for the webapp subproject. **Section 14 (Brownfield mode)** is the brownfield-production-branch addendum: modules, endpoints, artifact layout, doctrine validator, embedding stack.
- `BROWNFIELD_PROGRESS.md` at repo root — living progress doc for the current brownfield target (full-stack-fastapi-template). Has the per-BL ledger, scorecard summaries, known gaps, resume instructions. Update at the end of each agent cycle.
- `rubrics/production_grade_scorecard.md` — greenfield rubric (50 core + 25 role = 75).
- `rubrics/production_grade_scorecard_brownfield.md` — sidecar brownfield rubric (50 core + 25 role + 25 brownfield = 100). Single brownfield-axis dim ≤2 forces Fail. Webapp's `score-bl` picks the file via `target_status()`.
- `docs/SKILLS_WITH_GRAPHS_PLAN.md` (branch `skills_with_graphs`) — older implementation plan for the graph + semantic retrieval layer.
- The three brownfield SKILLS.md files at `skills/brownfield/brownfield-production-incremental-{po,engineer,qa}/SKILLS.md` — **these are the binding doctrine, loaded verbatim by `prompts_brownfield.py` at runtime**. Editing them changes agent behavior on the next run.

**How to apply:** any brownfield-flow question → BROWNFIELD_PROGRESS.md + PROJECT_STATE.md §14. Any rubric / scoring question → the right rubric file. Any doctrine question → the SKILLS.md files directly. Don't reinvent these.
