"""ABL-0016 Stage 1.5 — semantic lessons retrieval tests.

Two layers:
- **Pure / synthetic** (no infra): floor+rank, normalize/cosine, in-memory
  round-trip, lesson→embed-text. Always run.
- **Effectiveness (real bge-m3 embeddings)**: the actual proof that a problem
  statement matches the right lesson and the relevance floor rejects unrelated
  problems. Skipped cleanly when Ollama is unavailable.
- **Milvus smoke**: round-trips one lesson through the production backend.
  Skipped when Milvus is unreachable.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import lessons_index as li  # noqa: E402
from app.services.lessons import Lesson  # noqa: E402


def _mk(fid: str, cls: str, root_cause: str, *, fix_locus: str = "", summary: str = "") -> Lesson:
    return Lesson(
        lesson_id=fid, kind="finding", feature_slug=fid, classification=cls,
        summary=summary, verdict="confirmed", seen_count=1, last_seen_ts="t",
        source_run_id="r", report_path="p", root_cause=root_cause, fix_locus=fix_locus,
    )


# ─── pure / synthetic (always run) ──────────────────────────────────────────


def test_select_above_floor_sorts_filters_caps() -> None:
    scored = [("a", 0.9), ("b", 0.4), ("c", 0.7), ("d", 0.55)]
    kept = li.select_above_floor(scored, k=2, min_score=0.55)
    assert [p for p, _ in kept] == ["a", "c"]  # 0.4 dropped, 0.55-tie kept-then-capped


def test_select_above_floor_empty_when_all_below() -> None:
    assert li.select_above_floor([("a", 0.3), ("b", 0.5)], k=5, min_score=0.55) == []


def test_normalize_is_unit_and_cosine_bounds() -> None:
    import math
    v = li._normalize([3.0, 4.0] + [0.0] * 1022)
    assert abs(math.sqrt(sum(x * x for x in v)) - 1.0) < 1e-9
    a = li._normalize([1.0, 0.0]); b = li._normalize([1.0, 0.0]); c = li._normalize([0.0, 1.0])
    assert abs(li._cosine(a, b) - 1.0) < 1e-9
    assert abs(li._cosine(a, c) - 0.0) < 1e-9


def test_inmemory_store_roundtrip_synthetic() -> None:
    store = li.InMemoryLessonStore()
    store.upsert("x", li._normalize([1.0, 0.0, 0.0]), {"finding_id": "x", "body": "bx"})
    store.upsert("y", li._normalize([0.0, 1.0, 0.0]), {"finding_id": "y", "body": "by"})
    assert store.count() == 2
    hits = store.search(li._normalize([1.0, 0.1, 0.0]), k=5, min_score=0.55)
    assert [p["finding_id"] for p, _ in hits] == ["x"]  # y is orthogonal → below floor


def test_lesson_embed_text_prefers_dossier() -> None:
    l = _mk("d", "product_bug", root_cause="rest-aware streak not used by UI badge",
            fix_locus="components.py:843", summary='{"status":"fail"}')
    t = li.lesson_embed_text(l)
    assert "rest-aware streak not used by UI badge" in t
    assert "[product_bug]" in t
    assert '{"status":"fail"}' not in t  # the status blob is NOT what we embed


def test_upsert_lesson_default_collection_naming() -> None:
    assert li.collection_for("/tmp/foo").startswith("lessons_")
    assert li.collection_for("/tmp/foo") == li.collection_for("/tmp/foo")  # stable


def test_embed_text_retries_transient_failure(monkeypatch) -> None:
    """During a sprint Ollama is contended; a single embed attempt intermittently
    times out. embed_text must retry transient failures rather than give up
    (which would silently null the pull tool exactly when the system is busy)."""
    import contextlib
    calls = {"n": 0}

    class _Resp:
        def read(self): return b'{"embedding": %s}' % str([0.1] * li.EMBED_DIM).encode()
    @contextlib.contextmanager
    def _fake_urlopen(req, timeout=0):
        calls["n"] += 1
        if calls["n"] < 3:                      # fail twice, succeed on the 3rd
            raise TimeoutError("contended")
        yield _Resp()
    monkeypatch.setattr(li.urllib.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(li.time, "sleep", lambda *_: None)  # no real backoff in test
    vec = li.embed_text("x", retries=3)
    assert len(vec) == li.EMBED_DIM and calls["n"] == 3


def test_embed_text_raises_after_exhausting_retries(monkeypatch) -> None:
    import contextlib
    @contextlib.contextmanager
    def _always_fail(req, timeout=0):
        raise TimeoutError("down")
        yield  # pragma: no cover
    monkeypatch.setattr(li.urllib.request, "urlopen", _always_fail)
    monkeypatch.setattr(li.time, "sleep", lambda *_: None)
    with pytest.raises(Exception):
        li.embed_text("x", retries=3)


# ─── Batch B: MCP tool + env wiring ─────────────────────────────────────────


def test_search_lessons_tool_in_allowlist() -> None:
    from app.services.claude_agent import RETRIEVAL_MCP_TOOLS
    assert "mcp__retrieval__search_lessons" in RETRIEVAL_MCP_TOOLS


def test_mcp_config_sets_lessons_repo_env(tmp_path: Path) -> None:
    """The STABLE lessons key reaches the retrieval server env."""
    import json as _json
    from app.services import claude_agent as ca
    main = tmp_path / "main"; wt = tmp_path / "wt"
    main.mkdir(); wt.mkdir()
    cfg_path, tools = ca._build_retrieval_mcp_config(None, wt, None, lessons_repo=main)
    env = _json.loads(cfg_path.read_text())["mcpServers"]["retrieval"]["env"]
    assert env["RETRIEVAL_LESSONS_REPO"] == str(main.resolve())
    assert env["RETRIEVAL_TARGET_REPO"] == str(wt.resolve())  # worktree for code search
    assert "mcp__retrieval__search_lessons" in tools
    cfg_path.unlink(missing_ok=True)


def test_mcp_config_lessons_repo_defaults_to_target(tmp_path: Path) -> None:
    import json as _json
    from app.services import claude_agent as ca
    wt = tmp_path / "wt"; wt.mkdir()
    cfg_path, _ = ca._build_retrieval_mcp_config(None, wt, None)
    env = _json.loads(cfg_path.read_text())["mcpServers"]["retrieval"]["env"]
    assert env["RETRIEVAL_LESSONS_REPO"] == str(wt.resolve())  # falls back to target
    cfg_path.unlink(missing_ok=True)


# ─── effectiveness: real bge-m3 embeddings (the actual proof) ───────────────


def _ollama_up() -> bool:
    try:
        li.embed_text("ping", timeout=10.0)
        return True
    except Exception:
        return False


_OLLAMA = _ollama_up()
ollama = pytest.mark.skipif(not _OLLAMA, reason="Ollama bge-m3 not reachable")

_LESSONS = [
    _mk("streak", "product_bug",
        "The rest-aware streak count is computed in the API but the frontend streak "
        "badge and Best Streaks chart still call the legacy non-rest-aware function, "
        "so the UI shows the wrong streak number."),
    _mk("auth", "product_bug",
        "Login session token was not invalidated on logout, so a copied cookie kept "
        "working after the user signed out."),
    _mk("paginate", "product_bug",
        "The list endpoint returned all rows with no limit/offset, causing slow "
        "responses and unbounded payloads on large projects."),
]


@pytest.fixture()
def real_store():
    """Index the corpus with real embeddings. If Ollama is too contended to
    embed all lessons even with retries (e.g. a live sprint is saturating it),
    SKIP — an infra timeout is not a mechanism failure."""
    store = li.InMemoryLessonStore()
    li.index_lessons(".", store=store, lessons=_LESSONS)
    if store.count() != 3:
        pytest.skip("Ollama contended — could not embed the corpus")
    return store


def _query_vec_or_skip(query: str) -> list[float]:
    """Embed a query for the effectiveness assertion; skip (not fail) if Ollama
    is unavailable mid-run. This is what separates 'mechanism returned the wrong
    lesson' (a real failure) from 'infra timed out this run' (a skip)."""
    try:
        return li.embed_text(query)
    except Exception:
        pytest.skip("Ollama contended — query embed failed after retries")


@ollama
def test_effectiveness_streak_problem_matches_streak_lesson(real_store) -> None:
    qv = _query_vec_or_skip(
        "I'm changing how habit streak counting works and need it to skip rest "
        "days; will the UI show the right number?")
    hits = real_store.search(qv, k=5, min_score=li.LESSON_MIN_SCORE)
    assert hits, "expected the streak lesson to match"
    assert hits[0][0]["finding_id"] == "streak"
    # the floor leaves only the genuinely-relevant lesson, not the whole corpus
    assert [p["finding_id"] for p, _ in hits] == ["streak"]
    assert hits[0][1] >= li.LESSON_MIN_SCORE


@ollama
def test_effectiveness_auth_problem_matches_auth_lesson(real_store) -> None:
    qv = _query_vec_or_skip(
        "After a user logs out their session token should no longer be valid")
    hits = real_store.search(qv, k=5, min_score=li.LESSON_MIN_SCORE)
    assert hits and hits[0][0]["finding_id"] == "auth"


@ollama
def test_effectiveness_unrelated_problem_returns_nothing(real_store) -> None:
    """The floor is the guard: a problem with no relevant lesson must surface
    NOTHING rather than the deceptively-close nearest neighbour."""
    for q in ("How do I send a confirmation email with an SMTP server",
              "Center a div with flexbox and change the button color"):
        qv = _query_vec_or_skip(q)
        hits = real_store.search(qv, k=5, min_score=li.LESSON_MIN_SCORE)
        assert hits == [], f"unrelated query should be filtered by the floor: {q!r} -> {hits}"


@ollama
def test_search_never_raises_on_bad_store(real_store) -> None:
    class _Boom:
        def count(self): raise RuntimeError("boom")
        def search(self, *a, **k): raise RuntimeError("boom")
    assert li.search_lessons(".", "anything", store=_Boom()) == []


# ─── Milvus production backend smoke (skipped if Milvus down) ───────────────


def _milvus_up() -> bool:
    try:
        from pymilvus import MilvusClient
        MilvusClient(uri="http://127.0.0.1:19530").list_collections()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not (_milvus_up() and _OLLAMA), reason="Milvus or Ollama not reachable")
def test_milvus_backend_roundtrip() -> None:
    store = li.MilvusLessonStore("lessons_pytest_smoke")
    import time as _t
    try:
        store.drop(); store = li.MilvusLessonStore("lessons_pytest_smoke")
        vec = li.embed_text(li.lesson_embed_text(_LESSONS[0]))
        store.upsert("streak", vec, {"finding_id": "streak", "classification": "product_bug",
                                     "feature_slug": "f", "verdict": "confirmed",
                                     "scope": "target", "body": "b", "source_run_id": "r"})
        # Milvus is near-real-time: flush + load so the just-upserted row is
        # queryable, then a bounded retry for index/consistency lag.
        store.client.flush("lessons_pytest_smoke")
        store.client.load_collection("lessons_pytest_smoke")
        qv = li.embed_text("habit streak counting should skip rest days in the UI")
        found = False
        for _ in range(10):
            hits = store.search(qv, k=5, min_score=li.LESSON_MIN_SCORE)
            if any(p.get("finding_id") == "streak" for p, _ in hits):
                found = True
                break
            _t.sleep(1)
        assert found
    finally:
        store.drop()
