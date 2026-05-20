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
| BL-0002 | WorkspaceMember model + role enum | **DONE — Pass 93/100** |
| BL-0003 | Workspace CRUD API | **DONE — Pass 94/100** |
| BL-0005 | Membership dep + 404 privacy invariant | **DONE — Pass 96/100** |
| BL-0007 | Project model + CRUD API | **DONE — Pass-W/R 92/100** |
| BL-0011 (partial) | Frontend Workspaces nav + list/create | next |

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

### BL-0002 — WorkspaceMember model + WorkspaceRole enum

| Role | Verdict | Commit | Notes |
|---|---|---|---|
| PO | doctrine_ok | (carried from BL-0001 sprint plan) | per-BL artifacts from Sprint 1 |
| Engineer | doctrine_ok | `18e8ca6` | WorkspaceMember model + WorkspaceRole enum; doctrine passed first try |
| QA | **PASS** | `fbd48bf` | 8 tests added, 0 regressions |
| Scorer | **Pass 93/100** | `1ccb351` | brownfield rubric |

Both Engineer and QA gates inconclusive (Docker compose gap) → force-merged via `merge-branch?skip_gate=true`.

### BL-0003 — Workspace CRUD API

| Role | Verdict | Commit | Notes |
|---|---|---|---|
| Engineer | doctrine_ok | `c6ff799` | CRUD at `/api/v1/workspaces`; doctrine passed first try |
| QA | **PASS** | `22a1a31` | 10 tests added, 0 regressions |
| Scorer | **Pass 94/100** | `dd132e5` | brownfield rubric |

Both gates inconclusive → force-merged.

### BL-0005 — Membership dep + 404 privacy invariant (REQ-0002)

| Role | Verdict | Commit | Notes |
|---|---|---|---|
| Engineer | doctrine_ok | `2b37950` | central `get_workspace_member` dep enforcing 404-for-non-members; gate **GREEN** (pre 117 → post 128) after gate hardening |
| (merge) | clean non-FF | `ccadd36` | manual merge — agent branch diverged from `agentic-skills-work` via the gate-hardening commit `4725d7d` |
| QA | **PASS** | `2c231db` | 7 tests added, 0 regressions, **gate green, AUTO-MERGED** (first BL without `skip_gate`) |
| Scorer | **Pass 96/100** | `2914437` | brownfield rubric — highest score in Sprint 1 |

First BL to merge through a passing regression gate. The gate caught a false-positive on the engineer first try (stale `backend:latest` docker image across pre/post runs); hardened test_cmd with `--build` + always-clean-up `docker compose down -v` (commit `4725d7d`).

### BL-0007 — Project model + workspace-scoped CRUD API (REQ-0003)

| Role | Verdict | Commit | Notes |
|---|---|---|---|
| Engineer v1 | **discarded** | `3466dba` → reverted | Anthropic 529 storm aborted code generation; only doctrine doc committed; doctrine validator passed (artifact present) but real code was missing. Whole BL-0007 chain (eng + qa + scorer 18/100 Fail) reset to BL-0005 tip. |
| (infra) | doctrine fix | `webapp/...doctrine_validator.py` | Validator now also requires a non-empty source-code diff vs `agent_branch` before declaring engineer doctrine_ok. Closes the docs-only-commit gap. |
| (target) | brittle test fix | `b9010d9` | `test_alembic_chain_remains_single_head` hardcoded BL-0002 head SHA; replaced with `len(heads)==1`. Same antipattern as BL-0001's QA test (a8a2f3d). |
| Engineer v2 | doctrine_ok (after 2x 529 retries) | `9123e5b` | Real code: Project SQLModel + alembic `c3d4e5f6a7b8` + routes scoped via `get_workspace_member` + 15 tests. Gate **green** but surfaced 1 engineer-authored test failure (`test_delete_project` session-isolation bug). |
| (merge) | non-FF | `5237aea` | Same divergence pattern as BL-0005 (brittle-test fix landed on agentic-skills-work first). |
| QA | **PASS-W/R**, auto-merged | `85b277f` | 10 adversarial tests added (privacy parity, cross-workspace mutate 404, HTTP cascade); fixed engineer's `test_delete_project` with `db.expunge_all()`. Gate green, 160/160 passing. *Mid-run uvicorn crash* surfaced but QA had already committed; recovered via merge-branch endpoint. |
| Scorer | **Pass-W/R 92/100** | `246deef` | Reservation likely for engineer's session-isolation defect. |

Operational learnings:
- API overload (529 storm) + doctrine-validator gap = docs-only commit slipped through. Validator now hardened.
- Uvicorn died mid-QA-stream (silent crash, no traceback in log). QA agent commits to its worktree branch *before* the SSE done event, so work is recoverable via direct merge-branch endpoint after restart. Worth noting as a workflow property.

## Known gaps / open issues

1. ~~**Regression gate is currently always inconclusive.**~~ **RESOLVED 2026-05-20** (target commit `a8a2f3d`). Root cause was actually two-layered:
   (a) `compose.override.yml` uses Docker Compose v2.22+ `develop:` key that local Engine 24.0.6 / Compose v2.21.0 rejects, breaking *every* compose subcommand including `exec`.
   (b) Even with that fixed, the prior `docker compose exec -T backend pytest -q` test_cmd required a long-running stack AND the worktree's compose project name to match it — neither holds under the disposable-worktree gate model. So a Compose upgrade alone would have fixed nothing operationally.

   Fix: in target's `.agentic-skills.json`, replaced test_cmd with `sh -c 'docker network inspect traefik-public >/dev/null 2>&1 || docker network create traefik-public; docker compose -f compose.yml run --rm -v "$PWD/backend/tests:/app/backend/tests:ro" backend pytest -q tests'`. Skips the broken override file, creates the external network idempotently, bind-mounts tests (upstream Dockerfile excludes them by design), and uses ephemeral `run --rm` so each worktree gets its own throwaway compose project.

   Bonus: getting the gate operational *immediately surfaced* a real BL-0002 production bug — `b2c3d4e5f6a7_add_workspace_member_table.py` was double-creating the `workspacerole` PG enum (`sa.Enum.create(checkfirst=True)` then `op.create_table` with a column-bound Enum that re-fires `CREATE TYPE` without checkfirst). Fixed by dropping the explicit `.create()` and letting the column-bound Enum auto-create. Also fixed brittle QA test `test_alembic_revision_chain_is_linear` that hardcoded the BL-0001 head SHA. All 117 tests now pass.
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
