---
name: arch_stage3_cross_target
description: "ABL-0018 Stage 3 cross-target ('community') cumulative learning — SHIPPED 2026-06-11. global_lessons.py: recurrence graduation (≥2 targets, floor 0.62) + curated seed → shared global store; merged search_lessons + inject_global_lessons push. Read-path push+pull LIVE-PROVEN; recurrence write-path [~] (awaits cross-target data)."
metadata: 
  node_type: memory
  type: project
  originSessionId: e384aae0-0eb8-447a-acf0-cda9cbb661c2
---

**ABL-0018 Stage 3 — the mission pillar "learning carries forward ACROSS targets."**
SHIPPED 2026-06-11 (commit `b627d32` on `development`). Doc:
`ABL-0018_CROSS_TARGET_TRANSFER.md`. Builds on [[arch_cumulative_learning]] Stages
1/1.5/4 (which were per-target only).

**Mechanism (operator chose §3 option C = auto recurrence + curated seed):** a
failure mode independently confirmed on ≥N **distinct targets** — or an
operator/architect-curated obviously-general lesson — **graduates** into a shared
GLOBAL store every target's roles consult. A fresh target inherits the global layer
day one.

**Substrate (in the CORE project, never a target repo):**
`webapp/backend/.crew-memory/global_lessons.jsonl` (committed source of truth) +
fixed Milvus collection `lessons_global` (NOT md5-keyed). `global_lessons.py`.

**Write-paths:**
- **recurrence** (canonical, un-gated): at `sprint_complete`, off-thread best-effort,
  embeds every target's confirmed lessons, union-find clusters across targets at
  cosine ≥ **GRADUATION_MIN_SCORE=0.62** (EMPIRICALLY CALIBRATED on real bge-m3: a
  genuine cross-target layer-divergence *twin* scores ~0.665; unrelated modes
  ~0.46–0.47; 0.62 sits in the gap). ≥2 distinct targets (`GRADUATION_MIN_TARGETS`)
  graduates the richest-dossier representative. Idempotent by sha256 of member
  finding-ids.
- **curated** (`seed_global_lesson` + `scripts/seed_global_lessons.py`): bootstrap +
  safety valve; `graduation_kind="curated"`, honest provenance (only the targets it
  was ACTUALLY confirmed on — NOT a false multi-target claim).

**Read-paths (both scope-tagged target|global; never-raise):**
- **PULL:** `search_lessons` MCP tool now unions per-target (`lessons_index`) +
  global (`search_lessons_merged`).
- **PUSH:** independent `inject_global_lessons` flag (DEFAULT OFF; higher blast
  radius than per-target → separate rollout) threaded request→run_brief→3 flows→4
  builders→`_lessons_block`; renders even with 0 per-target lessons.

**Batch-0 finding (decisive):** fleet has **1 confirmed lesson on 1 target**
(beaverhabits rest-days streak; ecommerce ledger empty), so recurrence has **0
cross-target recurrence** to fire on yet.

**Proofs (no-overclaim, [[feedback_no_scope_overclaim]]):**
- Read-path PUSH **`[x]` LIVE-PROVEN**: global block renders into a REAL ecommerce
  engineer prompt (0 per-target lessons).
- Read-path PULL **`[x]` LIVE-PROVEN**: from ecommerce a neutral hazard-pattern
  query pulls the beaverhabits global lesson at **0.669 (scope=global)**; a
  distant-domain pricing query at **0.483 correctly below the 0.55 floor**.
- Recurrence write-path **`[x]` mechanism / `[~]` organic**: real-embedding twin
  graduates, unrelated rejected; never organically fired (no cross-target
  recurrence in the fleet).
- Curated seed **`[x]` LIVE**: beaverhabits layer-divergence seeded + indexed.
- Tests: `test_global_lessons.py` (20) + `test_global_lessons_wiring.py` (10). Full
  backend suite **467 passed, 0 regressions**.

**Open follow-ups:** (1) recurrence never organically fired — live-proof gated on
≥2 targets sharing a confirmed mode (data, not code). (2) cross-domain PULL is
floor-limited: a single concrete lesson matches its own domain ~0.65 but a distant
domain ~0.48–0.51 (<0.55); a separately-calibrated lower global-pull floor may help
but NOT lowered blind (needs cross-target data). (3) Batch-E smoke + flag-flip
remains. See [[arch_cumulative_loop_closed]], [[feedback_improve_crew_not_accommodate]].
