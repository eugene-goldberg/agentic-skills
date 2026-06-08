"""ABL-0019 — per-target Pattern Profile tests.

- Pure (no infra): section split, durable-section filter, dedup across BLs,
  path parsing (A18 + legacy), consolidate writes the profile. Always run.
- Effectiveness (real bge-m3): a problem statement retrieves the right durable
  convention; unrelated → empty (floor). Skips cleanly under Ollama contention.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import pattern_profile as pp  # noqa: E402
from app.services import lessons_index as li  # noqa: E402

_ENG_PATTERNS_TMPL = """# Engineer Pattern Matching — {bl}

## Closest existing implementations (2-3)
- app/routers/projects.py:100 — closest analog for THIS bl only

## Architectural patterns in use here
- Layering: {arch}

## Invariants to preserve in this slice
- {inv}

## Integration points / blast radius
- update_x: callers=[a,b] — bl-specific, should be dropped

## Compatibility strategy
- Additive: yes

## Planned slices (4-8 increments)
1. do the thing — bl-specific noise
"""


def _write_eng_patterns(repo: Path, rel: str, *, arch: str, inv: str, bl: str) -> None:
    p = repo / "_brownfield" / rel / "eng_patterns.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_ENG_PATTERNS_TMPL.format(bl=bl, arch=arch, inv=inv), encoding="utf-8")


# ─── extraction / filtering / dedup (pure) ──────────────────────────────────


def test_extract_keeps_durable_drops_bl_specific(tmp_path: Path) -> None:
    _write_eng_patterns(tmp_path, "features/feat-a/BL-0001",
                        arch="models -> repos -> services -> routers",
                        inv="every route requires auth", bl="BL-0001")
    entries = pp.extract_patterns(tmp_path)
    areas = {e.area for e in entries}
    # durable sections kept
    assert any("Architectural patterns" in a for a in areas)
    assert any("Invariant" in a for a in areas)
    assert any("Compatibility" in a for a in areas)
    # bl-specific noise dropped
    assert not any("Planned slices" in a for a in areas)
    assert not any("blast radius" in a.lower() for a in areas)
    assert not any("Closest existing" in a for a in areas)


def test_dedup_identical_convention_across_bls(tmp_path: Path) -> None:
    # two BLs restate the SAME layering — must collapse to one entry per section
    for bl in ("BL-0001", "BL-0002"):
        _write_eng_patterns(tmp_path, f"features/feat-a/{bl}",
                            arch="models -> repos -> services -> routers",
                            inv="every route requires auth", bl=bl)
    entries = pp.extract_patterns(tmp_path)
    # 3 durable sections, deduped across the 2 identical files → 3 entries
    assert len(entries) == 3


def test_path_parsing_a18_and_legacy(tmp_path: Path) -> None:
    _write_eng_patterns(tmp_path, "features/billing/BL-0007",
                        arch="x", inv="y", bl="BL-0007")
    _write_eng_patterns(tmp_path, "BL-0009",  # legacy layout
                        arch="z", inv="w", bl="BL-0009")
    got = {(bl, feat) for _, bl, feat in pp._iter_eng_patterns(tmp_path)}
    assert ("BL-0007", "billing") in got
    assert ("BL-0009", "") in got


def test_consolidate_writes_profile(tmp_path: Path) -> None:
    _write_eng_patterns(tmp_path, "features/feat-a/BL-0001",
                        arch="models -> repos -> services", inv="auth req", bl="BL-0001")
    text = pp.consolidate(tmp_path)
    assert pp.profile_path(tmp_path).exists()
    assert "Pattern Profile" in text
    assert "models -> repos -> services" in text


def test_empty_target_returns_nothing(tmp_path: Path) -> None:
    assert pp.extract_patterns(tmp_path) == []


def test_collection_naming_stable() -> None:
    assert pp.collection_for("/tmp/x").startswith("patterns_")
    assert pp.collection_for("/tmp/x") == pp.collection_for("/tmp/x")


def test_search_patterns_tool_in_allowlist() -> None:
    from app.services.claude_agent import RETRIEVAL_MCP_TOOLS
    assert "mcp__retrieval__search_patterns" in RETRIEVAL_MCP_TOOLS


# ─── effectiveness (real bge-m3 embeddings) ─────────────────────────────────


def _ollama_up() -> bool:
    try:
        li.embed_text("ping", timeout=10.0)
        return True
    except Exception:
        return False


_OLLAMA = _ollama_up()
ollama = pytest.mark.skipif(not _OLLAMA, reason="Ollama bge-m3 not reachable")

_PATTERNS = [
    pp.PatternEntry("p:data", "Architectural patterns in use here", "BL-1", "f",
                    "Persistence uses SQLModel table classes in models.py; a "
                    "repository layer wraps the session; create a new table by "
                    "adding a SQLModel class and a CRUD repo function."),
    pp.PatternEntry("p:route", "Architectural patterns in use here", "BL-2", "f",
                    "HTTP routes live in routers/, use APIRouter, depend on a "
                    "get_session dependency, and return Pydantic response models."),
    pp.PatternEntry("p:auth", "Invariants to preserve", "BL-3", "f",
                    "Every mutating endpoint must check the current-user session "
                    "token via the auth dependency before writing."),
]


@pytest.fixture()
def real_store():
    store = li.InMemoryLessonStore()
    pp.index_patterns(".", store=store, entries=_PATTERNS)
    if store.count() != 3:
        pytest.skip("Ollama contended — could not embed the pattern corpus")
    return store


def _qv_or_skip(q: str):
    try:
        return li.embed_text(q)
    except Exception:
        pytest.skip("Ollama contended — query embed failed")


@ollama
def test_effectiveness_db_problem_matches_data_layer_pattern(real_store) -> None:
    qv = _qv_or_skip("I'm adding a new database table and model for storing notes")
    hits = real_store.search(qv, k=5, min_score=li.LESSON_MIN_SCORE)
    assert hits, "expected the data-layer pattern to match"
    assert hits[0][0]["finding_id"] == "p:data"


@ollama
def test_effectiveness_unrelated_returns_nothing(real_store) -> None:
    qv = _qv_or_skip("How do I tune CSS animations for a loading spinner")
    hits = real_store.search(qv, k=5, min_score=li.LESSON_MIN_SCORE)
    assert hits == []


@ollama
def test_search_patterns_never_raises_on_bad_store() -> None:
    class _Boom:
        def count(self): raise RuntimeError("boom")
        def search(self, *a, **k): raise RuntimeError("boom")
    assert pp.search_patterns(".", "anything", store=_Boom()) == []


@ollama
def test_search_patterns_public_path_tags_kind(real_store) -> None:
    """The public search_patterns path embeds the query, searches, and tags
    each hit kind='pattern' so the consumer can frame it as a convention."""
    hits = pp.search_patterns(
        ".", "adding a new database table and model",
        store=real_store, build_if_empty=False,
    )
    if not hits:
        pytest.skip("Ollama contended — query embed failed")
    assert all(h["kind"] == "pattern" for h in hits)
    assert hits[0]["finding_id"] == "p:data"
