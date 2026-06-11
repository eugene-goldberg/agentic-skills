#!/usr/bin/env python3
"""ABL-0018 Stage 3 — curated cross-target lesson seed (the operator-approved
bootstrap of the global "community" store).

Per the ABL-0018 §3 decision (operator, 2026-06-11, option C), recurrence
graduation is the canonical mechanism, AND the architect/operator may CURATE an
obviously-stack-agnostic lesson into the global store to bootstrap it (so the
read-path is live-demonstrable before organic cross-target recurrence
accumulates). Curated seeds are honestly provenance-tagged
(``graduation_kind="curated"``) so the store stays un-poisoned and auditable.

HONESTY (no-overclaim): each seed below records ONLY the targets it was actually
CONFIRMED on. The "this generalizes across stacks" judgment lives in the
``graduation_kind="curated"`` tag + the ``note`` — it is an architect
generalization from a real confirmed instance, NOT a false multi-target
recurrence claim. As the same mode is later confirmed on more targets, the
recurrence pass will graduate it organically (a separate record) and the
``target_count`` will reflect genuine recurrence.

Idempotent: re-running does not duplicate (the global store dedups by content id).
Writes to the COMMITTED source of truth ``webapp/backend/.crew-memory/
global_lessons.jsonl`` and indexes into the Milvus ``lessons_global`` collection.

Run:  python scripts/seed_global_lessons.py            # seed + index
      python scripts/seed_global_lessons.py --no-index # seed only (no Milvus/Ollama)
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "webapp" / "backend"
sys.path.insert(0, str(BACKEND))

from app.services import global_lessons as gl  # noqa: E402


# Each curated seed = a real, operator-confirmed lesson the architect judges to be
# a GENERAL (stack-agnostic) failure mode. ``origin_targets`` lists ONLY where it
# was actually confirmed (honest provenance); ``origin_finding_ids`` cite the real
# ledger finding(s).
SEEDS = [
    dict(
        classification="product_bug",
        # Body anchored in the REAL confirmed instance (concrete evidence embeds
        # better than abstraction, and matches how per-target lessons embed) +
        # the general rule. No terms from any other domain (honest provenance).
        body=(
            "Layer divergence from an incomplete migration of callers: a new "
            "computation was added at the core/API layer but pre-existing UI "
            "consumers still call the LEGACY function, so the displayed value "
            "diverges from what the new code returns. Concretely: the rest-aware "
            "streak was added in core/streak.py and the API route, but the frontend "
            "streak badge and Best Streaks chart still called the legacy "
            "non-rest-aware compose_habit_streaks, so the UI showed 1 while the API "
            "returned 3. Unit tests passed because they called the new path directly. "
            "General rule: when you add or change behavior at one layer, grep for "
            "EVERY existing caller/reader of the old function or field and repoint or "
            "update them — not just the new path."
        ),
        origin_targets=["beaverhabits"],
        origin_finding_ids=[
            "sha256:f8579dd8bd1392fc9b203c9c617666ab0f4b9c6f0dedddaa255e7cbac8fd9a1a"
        ],
        note=(
            "Confirmed once on beaverhabits (rest-days-streak-freeze): the rest-aware "
            "streak was added in core/streak.py + the API route, but the frontend "
            "streak badge + Best Streaks chart still called the legacy non-rest-aware "
            "compose_habit_streaks, so the UI showed '1' while the API returned '3'. "
            "Architect-curated as a stack-agnostic class (recurs identically across "
            "languages/frameworks); awaiting organic recurrence to graduate by count."
        ),
    ),
]


def main() -> int:
    index = "--no-index" not in sys.argv
    print(f"global store: {gl.global_lessons_path()}")
    print(f"index into Milvus '{gl.GLOBAL_COLLECTION}': {index}")
    for seed in SEEDS:
        g = gl.seed_global_lesson(index=index, **seed)
        print(f"  seeded {g.global_lesson_id} [{g.classification}] "
              f"kind={g.graduation_kind} targets={g.origin_targets}")
    total = gl.list_global_lessons()
    print(f"global store now holds {len(total)} lesson(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
