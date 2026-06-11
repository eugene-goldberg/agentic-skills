"""ABL-0018 Stage 3 — cross-target ("community") cumulative learning tests.

Layers (mirrors test_lessons_index):
- **Pure / synthetic** (no infra): model round-trip, jsonl source-of-truth +
  dedup, render block, curated seed, graduation clustering (injected synthetic
  vectors), merge-logic union/dedup/sort/cap. Always run.
- **Effectiveness (real bge-m3 embeddings)**: the actual proof that a genuine
  cross-target *twin* failure mode clusters + graduates while two merely
  same-domain lessons do not — this calibrates GRADUATION_MIN_SCORE. Skipped
  cleanly when Ollama is unavailable.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import global_lessons as gl  # noqa: E402
from app.services import lessons_index as li  # noqa: E402
from app.services.lessons import Lesson  # noqa: E402


def _cand(target: str, fid: str, body: str, vec: list[float], cls: str = "product_bug") -> gl._CandidateLesson:
    return gl._CandidateLesson(
        target_id=target, finding_id=fid, classification=cls, body=body,
        vec=li._normalize(vec),
    )


def _glesson(**kw) -> gl.GlobalLesson:
    base = dict(
        global_lesson_id="g-x", classification="product_bug", body="b",
        origin_targets=["t1", "t2"], origin_finding_ids=["a", "b"], target_count=2,
        graduation_kind="recurrence", graduated_ts="2026-01-01T00:00:00Z", note="",
    )
    base.update(kw)
    return gl.GlobalLesson(**base)


# ─── Batch A: model + jsonl source of truth ─────────────────────────────────


def test_global_lesson_json_roundtrip() -> None:
    g = _glesson(note="why")
    g2 = gl.GlobalLesson.from_json(g.to_json())
    assert g2 == g


def test_append_and_list_dedup_latest_wins(tmp_path: Path) -> None:
    p = tmp_path / "global_lessons.jsonl"
    gl._append_record(_glesson(global_lesson_id="g-1", body="old", target_count=2), path=p)
    gl._append_record(_glesson(global_lesson_id="g-1", body="new", target_count=3,
                               graduated_ts="2026-02-01T00:00:00Z"), path=p)
    gl._append_record(_glesson(global_lesson_id="g-2", body="other", target_count=2), path=p)
    out = gl.list_global_lessons(path=p)
    by_id = {g.global_lesson_id: g for g in out}
    assert by_id["g-1"].body == "new"            # latest record wins
    assert len(out) == 2                          # deduped
    assert out[0].target_count >= out[1].target_count  # ranked by target_count desc


def test_list_global_lessons_missing_store_is_empty(tmp_path: Path) -> None:
    assert gl.list_global_lessons(path=tmp_path / "nope.jsonl") == []


def test_list_global_lessons_skips_malformed_lines(tmp_path: Path) -> None:
    p = tmp_path / "g.jsonl"
    p.write_text(_glesson(global_lesson_id="g-ok").to_json() + "\nnot json\n\n",
                 encoding="utf-8")
    out = gl.list_global_lessons(path=p)
    assert [g.global_lesson_id for g in out] == ["g-ok"]


# ─── Batch A: render (push block) ───────────────────────────────────────────


def test_render_empty_is_silent() -> None:
    assert gl.render_global_lessons_block([]) == ""


def test_render_carries_cross_target_framing_and_count() -> None:
    block = gl.render_global_lessons_block([
        _glesson(classification="product_bug", body="layer divergence", target_count=3),
    ])
    assert "Cross-target lessons" in block
    assert "multiple independent target" in block
    assert "seen across 3 targets" in block
    assert "falsification priors" in block       # advisory framing preserved


def test_render_marks_curated() -> None:
    block = gl.render_global_lessons_block([
        _glesson(graduation_kind="curated", target_count=1, body="seeded"),
    ])
    assert "curated" in block


def test_render_caps() -> None:
    many = [_glesson(global_lesson_id=f"g-{i}", body=f"b{i}") for i in range(20)]
    block = gl.render_global_lessons_block(many, cap=3)
    assert block.count("- **[") == 3


# ─── Batch A: curated seed ──────────────────────────────────────────────────


def test_seed_global_lesson_is_curated_and_idempotent(tmp_path: Path) -> None:
    p = tmp_path / "g.jsonl"
    a = gl.seed_global_lesson(
        classification="product_bug", body="new logic at one layer, old callers at another",
        origin_targets=["beaverhabits", "fullstack-ecommerce-app"],
        note="layer-divergence; stack-agnostic", path=p, index=False,
    )
    b = gl.seed_global_lesson(
        classification="product_bug", body="new logic at one layer, old callers at another",
        origin_targets=["fullstack-ecommerce-app", "beaverhabits"],  # order-insensitive
        note="re-seed", path=p, index=False,
    )
    assert a.graduation_kind == "curated"
    assert a.global_lesson_id == b.global_lesson_id        # idempotent by content
    assert a.target_count == 2
    out = gl.list_global_lessons(path=p)
    assert len(out) == 1                                    # deduped to one


# ─── Batch B: recurrence graduation (synthetic vectors, no Ollama) ──────────


def test_graduate_shared_mode_across_two_targets(tmp_path: Path) -> None:
    p = tmp_path / "g.jsonl"
    shared = [1.0, 0.0, 0.0]
    cands = [
        _cand("t1", "f1", "short body", shared),
        _cand("t2", "f2", "a much longer richer dossier body that should win as rep", shared),
        _cand("t3", "f3", "unrelated mode", [0.0, 1.0, 0.0]),   # orthogonal → own cluster
    ]
    out = gl.graduate([], path=p, index=False, candidates=cands)
    assert len(out) == 1                                    # only the shared cluster graduates
    g = out[0]
    assert sorted(g.origin_targets) == ["t1", "t2"]
    assert g.target_count == 2
    assert "richer dossier" in g.body                       # richest member is the representative
    assert g.graduation_kind == "recurrence"


def test_graduate_requires_distinct_targets_not_features(tmp_path: Path) -> None:
    """Two confirmed lessons that are the SAME mode but on the SAME target (e.g.
    two features) must NOT graduate — generality requires ≥2 distinct targets."""
    p = tmp_path / "g.jsonl"
    same = [1.0, 0.0, 0.0]
    cands = [_cand("t1", "f1", "x", same), _cand("t1", "f2", "y", same)]
    assert gl.graduate([], path=p, index=False, candidates=cands) == []


def test_graduate_unique_mode_does_not_graduate(tmp_path: Path) -> None:
    p = tmp_path / "g.jsonl"
    cands = [
        _cand("t1", "f1", "mode A", [1.0, 0.0, 0.0]),
        _cand("t2", "f2", "mode B", [0.0, 1.0, 0.0]),       # different mode, different target
    ]
    assert gl.graduate([], path=p, index=False, candidates=cands) == []


def test_graduate_idempotent_id(tmp_path: Path) -> None:
    p = tmp_path / "g.jsonl"
    shared = [1.0, 0.0, 0.0]
    cands = [_cand("t1", "f1", "x", shared), _cand("t2", "f2", "yy longer", shared)]
    a = gl.graduate([], path=p, index=False, candidates=cands)
    b = gl.graduate([], path=p, index=False, candidates=cands)
    assert a[0].global_lesson_id == b[0].global_lesson_id
    assert len(gl.list_global_lessons(path=p)) == 1         # second pass dedups, no dup row


def test_graduate_too_few_candidates_is_empty(tmp_path: Path) -> None:
    assert gl.graduate([], path=tmp_path / "g.jsonl", index=False,
                       candidates=[_cand("t1", "f1", "x", [1.0, 0.0])]) == []


# ─── Batch C: merged read-path (union/dedup/sort/cap — logic only) ──────────


def test_search_merged_unions_and_sorts(monkeypatch) -> None:
    monkeypatch.setattr(li, "search_lessons",
                        lambda *a, **k: [{"finding_id": "t-1", "scope": "target", "score": 0.6, "body": "tb"}])
    monkeypatch.setattr(gl, "search_global_lessons",
                        lambda *a, **k: [{"finding_id": "g-1", "scope": "global", "score": 0.9, "body": "gb"}])
    out = gl.search_lessons_merged("/repo", "q", k=5)
    assert [h["scope"] for h in out] == ["global", "target"]   # sorted by score desc
    assert {h["finding_id"] for h in out} == {"t-1", "g-1"}


def test_search_merged_dedups_by_finding_id_keeps_best(monkeypatch) -> None:
    monkeypatch.setattr(li, "search_lessons",
                        lambda *a, **k: [{"finding_id": "x", "scope": "target", "score": 0.6}])
    monkeypatch.setattr(gl, "search_global_lessons",
                        lambda *a, **k: [{"finding_id": "x", "scope": "global", "score": 0.8}])
    out = gl.search_lessons_merged("/repo", "q", k=5)
    assert len(out) == 1 and out[0]["score"] == 0.8           # best score wins


def test_search_merged_caps_at_k(monkeypatch) -> None:
    monkeypatch.setattr(li, "search_lessons",
                        lambda *a, **k: [{"finding_id": f"t{i}", "scope": "target", "score": 0.6} for i in range(5)])
    monkeypatch.setattr(gl, "search_global_lessons",
                        lambda *a, **k: [{"finding_id": f"g{i}", "scope": "global", "score": 0.9} for i in range(5)])
    out = gl.search_lessons_merged("/repo", "q", k=3)
    assert len(out) == 3


def test_search_global_never_raises(monkeypatch) -> None:
    def _boom(*a, **k):
        raise RuntimeError("milvus down")
    monkeypatch.setattr(gl, "_global_store", _boom)
    assert gl.search_global_lessons("q") == []               # advisory: degrades to empty


# ─── effectiveness: real bge-m3 embeddings (the graduation-floor calibration) ─


def _ollama_up() -> bool:
    try:
        li.embed_text("ping", timeout=10.0)
        return True
    except Exception:
        return False


_OLLAMA = _ollama_up()
ollama = pytest.mark.skipif(not _OLLAMA, reason="Ollama bge-m3 not reachable")


def _embed_cand(target: str, fid: str, body: str) -> gl._CandidateLesson:
    return gl._CandidateLesson(target_id=target, finding_id=fid, classification="product_bug",
                               body=body, vec=li.embed_text(f"[product_bug] {body}"))


# A genuine cross-target TWIN: the same abstract failure mode (new business logic
# added at one layer; pre-existing consumers at another layer still call the old
# path → user-visible divergence) expressed on two different stacks.
_BEAVER = ("beaverhabits", "f-streak",
           "The rest-aware streak count is computed in the new core/API function but the "
           "frontend streak badge and chart still call the legacy non-rest-aware function, "
           "so the UI shows a different (wrong) streak number than the API returns.")
_ECOM = ("fullstack-ecommerce-app", "f-price",
         "The new discounted price is computed in the new pricing service but the cart "
         "summary view still reads the old base-price field, so the UI shows a different "
         "(wrong) total than the checkout API charges.")
# An unrelated mode on a third target — same domain words, different failure.
_UNREL = ("notes-app", "f-auth",
          "The logout endpoint did not invalidate the session token, so a copied cookie "
          "kept working after the user signed out.")


@ollama
def test_effectiveness_cross_target_twin_graduates(tmp_path: Path) -> None:
    try:
        cands = [_embed_cand(*_BEAVER), _embed_cand(*_ECOM)]
    except Exception:
        pytest.skip("Ollama contended — could not embed corpus")
    out = gl.graduate([], path=tmp_path / "g.jsonl", index=False, candidates=cands)
    assert len(out) == 1, "the cross-target layer-divergence twin should cluster + graduate"
    assert sorted(out[0].origin_targets) == ["beaverhabits", "fullstack-ecommerce-app"]


@ollama
def test_effectiveness_unrelated_mode_does_not_graduate(tmp_path: Path) -> None:
    try:
        cands = [_embed_cand(*_BEAVER), _embed_cand(*_UNREL)]
    except Exception:
        pytest.skip("Ollama contended — could not embed corpus")
    out = gl.graduate([], path=tmp_path / "g.jsonl", index=False, candidates=cands)
    assert out == [], "an unrelated failure mode must not graduate (floor calibration)"
