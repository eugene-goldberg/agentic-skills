# Brownfield-production — progress

Living progress doc for the `brownfield-production` branch. Update at the end of each agent cycle.

## Active target

- **Repo:** `~/dev/ai-projects/brownfield-targets/full-stack-fastapi-template`
- **Symlink:** `webapp/backend/repos/full-stack-fastapi-template`
- **Upstream:** https://github.com/fastapi/full-stack-fastapi-template
- **Pristine baseline:** branch `master` @ `32ebacf` (never touched by agents)
- **Working branch:** `agentic-skills-work`

## Doctrine source

The PO / Engineer / QA agents load these files VERBATIM as binding doctrine at runtime:

- `skills/brownfield/brownfield-production-incremental-po/SKILLS.md`
- `skills/brownfield/brownfield-production-incremental-engineer/SKILLS.md`
- `skills/brownfield/brownfield-production-incremental-qa/SKILLS.md`

Editing these files changes agent behavior on the next run with no Python edit needed.

## Scorecard rubric

`rubrics/production_grade_scorecard_brownfield.md` (core 50 + role 25 + brownfield 25 = 100 max). A single brownfield-axis dim ≤2 forces Fail.

## Backlog

13 BLs decomposed by PO from `REQUIREMENTS.md` (Team Collaboration Module: Workspaces → Projects → Tasks → Comments).

Source: `.agile-v/BACKLOG.md` on `agentic-skills-work`. Brief mapping: REQ-0001..REQ-0006 + observability NFR. Per-BL context: `_brownfield/<BL-id>/codebase_context.md`.

## Sprint 1 plan

Source: `_brownfield/SPRINT_PLAN_C1.md` (PO-authored). Committed scope:

| BL | Title | Status |
|---|---|---|
| BL-0001 | Workspace data model + migration | **DONE — Pass 92/100** |
| BL-0002 | WorkspaceMember model + role enum | next |
| BL-0003 | Workspace CRUD API | pending |
| BL-0005 | Membership dep + 404 privacy invariant | pending |
| BL-0007 | Project model + CRUD API | pending |
| BL-0011 (partial) | Frontend Workspaces nav + list/create | pending |

Deferred to Sprint 2+: BL-0004 (invitations), BL-0006 (member removal), BL-0008/BL-0009 (Tasks + assignment), BL-0010 (Comments), BL-0012, BL-0013.

## Per-BL ledger

### BL-0001 — Workspace SQLModel + Alembic revision

| Role | Verdict | Commit | Notes |
|---|---|---|---|
| PO | doctrine_ok | `14804a6` | 13 BLs, full doctrine artifacts, validator passed first try |
| Engineer | doctrine_ok | `6abe64e` | 4 files / +200/-0 / 9 tests; pure additive |
| QA | **PASS** | `011baeb` | 9 more tests, 0 regressions, 0 new defects |
| Scorer | **Pass 92/100** | `45464e1` | core 46/50 + role 23/25 + brownfield 23/25 |
| (chore) | gitignore fix | `72fd7de` | removed `_brownfield/` from target repo gitignore |

Scorer notes: 2 points docked because engineer left adversarial/boundary tests for QA to write; 2 points docked because `eng_patterns.md` / `qa_impact.md` were lost to the original gitignore (now fixed for future BLs).

## Known gaps / open issues

1. **Regression gate is currently always inconclusive.** Docker Compose v2.22+ `develop:` key in `compose.override.yml` is rejected by local Docker Engine 24.0.6, so `docker compose exec backend pytest` exits 15. Each Engineer/QA cycle currently force-merged via `POST /merge-branch` with `skip_gate=true`. Fix path: upgrade Docker Desktop, or add a `disable_regression_gate` repo_config flag, or run pytest in a host venv after `docker compose up -d db`.
2. **Engineer routinely under-tests.** For BL-0001 the engineer shipped 9 happy-path/relationship tests; QA had to add 9 adversarial/characterization. Score reflects it. If BL-0002 / BL-0003 repeat the pattern, tighten `ENG_COMPLETION_PROTOCOL` with an explicit characterization-test minimum.
3. **Cold-start latency on retrieval.** Each fresh MCP-server process pays ~85 s on the first `semantic_search` call (no-op auto-index handshake). Acceptable for now; if it becomes a bottleneck, add a fast pre-check in `SemanticRegistry.search` that uses pymilvus directly to detect a populated collection.

## How to resume

1. Verify env: `curl http://127.0.0.1:8000/api/health` → `{embedding_provider: Ollama, milvus: localhost:19530}`.
2. Verify Ollama: `curl -s http://127.0.0.1:11434/api/embed -d '{"model":"bge-m3","input":"x"}' | head -c 100` returns 1024-dim vector.
3. Verify Milvus has a populated collection for the brownfield: it'll be at name `hybrid_code_chunks_*` in Milvus; if dropped, run **Run claude-context index** in the UI.
4. Open `http://localhost:5173`, select `full-stack-fastapi-template` in the repo dropdown.
5. Pick the next BL (BL-0002), click Execute BL.
6. After Engineer's done card, if the gate is `inconclusive`, click **Force merge (skip gate)** to advance.
7. Run QA, Score, repeat.
