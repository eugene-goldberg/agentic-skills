---
name: doc-pointers
description: "Canonical project docs to consult before editing — CLAUDE.md, PROJECT_STATE.md, and the rubric"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 2b184b19-1809-4a2e-bad8-ec19ea9ee94c
---

- `CLAUDE.md` at repo root — short orientation, points at PROJECT_STATE.md. Auto-loaded by Claude Code.
- `webapp/PROJECT_STATE.md` — deep current-state reference for the webapp subproject (10 endpoints, 4 prompt builders, UI layout, env auto-loading, commit history, known constraints). The webapp README is quick-start; this is the full reference.
- `rubrics/production_grade_scorecard.md` — **single source of truth** for scoring. Both the langgraph harness and the webapp's `score-bl` endpoint feed it to their scorer prompts verbatim. Never fork this file.
- `docs/SKILLS_WITH_GRAPHS_PLAN.md` (branch `skills_with_graphs`) — implementation plan for the graph + semantic retrieval layer.

**How to apply:** for any webapp-related question, read PROJECT_STATE.md first — it has 13 sections covering everything from endpoint shapes to deferred constraints. For scoring or rubric questions, read the rubric file. Don't reinvent these.
