"""ABL-0016 Stage 1.5 — semantic lessons retrieval (problem→lesson matching).

The agent derives a natural-language description of the problem it is facing and
queries this store for the nearest-neighbour prior lesson(s) **above a relevance
floor**. Match is on the PROBLEM (semantic), not the repo (Stage 1 Option A's
coarse target-scope) — and on the agent's *live* understanding, not a static
file list.

- **Embeddings:** local Ollama ``bge-m3`` (1024-dim) — the SAME embedder the code
  index uses (``OLLAMA_HOST`` / ``EMBEDDING_MODEL`` from ``webapp/.env``).
- **Store:** a dedicated per-target Milvus collection ``lessons_<md5(repo)[:8]>``
  (parallel to the code ``hybrid_code_chunks_<md5>`` collections), NOT routed
  through the code-file claude-context bridge. An in-memory cosine store is the
  test backend + no-Milvus fallback.
- **Relevance floor:** a lessons corpus is small + each lesson short; in a sparse
  space nearest-neighbour ALWAYS returns something with deceptively high score.
  ``search`` returns only hits ``>= LESSON_MIN_SCORE`` — below floor → empty.
  Without this guard the mechanism reintroduces the noise it exists to remove.

Advisory only (I-2 unaffected): a lesson is evidence to weigh, never a rule. The
public read path (``search_lessons``) NEVER raises into a sprint — any infra
failure yields an empty result.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.services import lessons as _lessons
from app.services.lessons import Lesson

EMBED_DIM = 1024
# Cosine floor below which a hit is not "really" relevant. Calibrated against
# bge-m3 in test_lessons_index's effectiveness test (related problem statements
# land well above; unrelated ones below).
LESSON_MIN_SCORE = 0.55
DEFAULT_SEARCH_K = 5


# ─── embedding (local Ollama bge-m3) ────────────────────────────────────────


def _ollama_host() -> str:
    return os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")


def _embed_model() -> str:
    return os.getenv("EMBEDDING_MODEL", "bge-m3")


def embed_text(text: str, *, timeout: float = 30.0) -> list[float]:
    """Embed ``text`` via local Ollama. Raises on failure (the public
    ``search_lessons`` boundary catches and treats failure as empty)."""
    req = urllib.request.Request(
        f"{_ollama_host()}/api/embeddings",
        data=json.dumps({"model": _embed_model(), "prompt": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        d = json.loads(resp.read().decode("utf-8"))
    vec = d.get("embedding") or []
    if len(vec) != EMBED_DIM:
        raise ValueError(f"unexpected embedding dim {len(vec)} != {EMBED_DIM}")
    return _normalize([float(x) for x in vec])


def _normalize(vec: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in vec))
    return [x / n for x in vec] if n else vec


def _cosine(a: list[float], b: list[float]) -> float:
    # vectors are stored normalized → inner product == cosine
    return sum(x * y for x, y in zip(a, b))


def select_above_floor(scored, *, k: int, min_score: float):
    """Pure ranking + floor: sort (payload, score) by score desc, drop below
    ``min_score``, cap at ``k``. The deterministic heart of the mechanism."""
    kept = [(p, s) for (p, s) in scored if s >= min_score]
    kept.sort(key=lambda ps: ps[1], reverse=True)
    return kept[:k]


# ─── lesson → embeddable text ───────────────────────────────────────────────


def lesson_embed_text(lesson: Lesson) -> str:
    """The text we embed for a lesson: classification + the A63 rich body
    (verified root_cause + fix_locus, else the thin summary). This is what a
    problem statement is matched against."""
    body = _lessons._lesson_body(lesson)
    return f"[{lesson.classification}] {body}".strip()


def _payload(lesson: Lesson, *, scope: str = "target") -> dict:
    return {
        "finding_id": lesson.lesson_id,
        "feature_slug": lesson.feature_slug,
        "classification": lesson.classification,
        "verdict": lesson.verdict,
        "scope": scope,
        "body": _lessons._lesson_body(lesson),
        "source_run_id": lesson.source_run_id,
    }


# ─── store backends (one interface) ─────────────────────────────────────────


class InMemoryLessonStore:
    """Cosine store for tests + a no-Milvus fallback. Same surface as
    ``MilvusLessonStore``."""

    def __init__(self) -> None:
        self._rows: dict[str, tuple[list[float], dict]] = {}

    def upsert(self, finding_id: str, vec: list[float], payload: dict) -> None:
        self._rows[finding_id] = (vec, payload)

    def count(self) -> int:
        return len(self._rows)

    def search(self, qvec: list[float], *, k: int, min_score: float) -> list[tuple[dict, float]]:
        scored = [(payload, _cosine(qvec, vec)) for (vec, payload) in self._rows.values()]
        return select_above_floor(scored, k=k, min_score=min_score)

    def drop(self) -> None:
        self._rows.clear()


class MilvusLessonStore:
    """Production backend — a per-target Milvus collection. Normalized vectors +
    IP metric ⇒ score is cosine. Best-effort: construction/ops raise on infra
    failure; the public boundary catches."""

    def __init__(self, collection: str, *, host: str = "127.0.0.1", port: str = "19530") -> None:
        from pymilvus import MilvusClient  # local import: optional dep at runtime
        self.collection = collection
        self.client = MilvusClient(uri=f"http://{host}:{port}")
        self._ensure()

    def _ensure(self) -> None:
        if self.client.has_collection(self.collection):
            return
        from pymilvus import DataType
        schema = self.client.create_schema(auto_id=False, enable_dynamic_field=True)
        schema.add_field("finding_id", DataType.VARCHAR, is_primary=True, max_length=128)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=EMBED_DIM)
        index = self.client.prepare_index_params()
        index.add_index(field_name="embedding", index_type="AUTOINDEX", metric_type="IP")
        self.client.create_collection(self.collection, schema=schema, index_params=index)

    def upsert(self, finding_id: str, vec: list[float], payload: dict) -> None:
        row = {"finding_id": finding_id, "embedding": vec, **payload}
        self.client.upsert(self.collection, [row])

    def count(self) -> int:
        try:
            self.client.flush(self.collection)
            return int(self.client.get_collection_stats(self.collection).get("row_count", 0))
        except Exception:
            return 0

    def search(self, qvec: list[float], *, k: int, min_score: float) -> list[tuple[dict, float]]:
        res = self.client.search(
            self.collection, data=[qvec], limit=max(k, 1),
            output_fields=["finding_id", "feature_slug", "classification",
                           "verdict", "scope", "body", "source_run_id"],
            search_params={"metric_type": "IP"},
        )
        scored: list[tuple[dict, float]] = []
        for hit in (res[0] if res else []):
            ent = hit.get("entity", hit) if isinstance(hit, dict) else {}
            scored.append((dict(ent), float(hit.get("distance", 0.0)) if isinstance(hit, dict) else 0.0))
        return select_above_floor(scored, k=k, min_score=min_score)

    def drop(self) -> None:
        if self.client.has_collection(self.collection):
            self.client.drop_collection(self.collection)


# ─── collection naming + store factory ──────────────────────────────────────


def collection_for(repo_root: Path | str) -> str:
    h = hashlib.md5(str(Path(repo_root).resolve()).encode("utf-8")).hexdigest()[:8]
    return f"lessons_{h}"


def _default_store(repo_root: Path | str):
    """Milvus if reachable, else in-memory (graceful degradation)."""
    try:
        return MilvusLessonStore(collection_for(repo_root))
    except Exception:
        return InMemoryLessonStore()


# ─── index + search (public) ────────────────────────────────────────────────


def index_lessons(repo_root: Path | str, *, store=None, lessons: Optional[list[Lesson]] = None) -> int:
    """Embed + upsert the target's confirmed lessons into ``store``. Returns the
    count indexed. Reads the ledger via ``lessons.list_lessons`` when not given
    an explicit list. Skips a lesson whose embedding fails (never aborts)."""
    if store is None:
        store = _default_store(repo_root)
    if lessons is None:
        lessons = _lessons.list_lessons(repo_root, cap=None)
    n = 0
    for lesson in lessons:
        try:
            vec = embed_text(lesson_embed_text(lesson))
        except Exception:
            continue
        store.upsert(lesson.lesson_id, vec, _payload(lesson))
        n += 1
    return n


def search_lessons(
    repo_root: Path | str,
    query: str,
    *,
    k: int = DEFAULT_SEARCH_K,
    min_score: float = LESSON_MIN_SCORE,
    store=None,
    build_if_empty: bool = True,
) -> list[dict]:
    """Return lessons whose embedding is nearest the problem ``query`` and above
    the relevance floor. NEVER raises — any infra failure yields ``[]`` so a
    sprint is never perturbed. Each hit: {finding_id, classification,
    feature_slug, body, score, …}."""
    try:
        if store is None:
            store = _default_store(repo_root)
        if build_if_empty and store.count() == 0:
            index_lessons(repo_root, store=store)
        qvec = embed_text(query)
        hits = store.search(qvec, k=k, min_score=min_score)
    except Exception:
        return []
    out = []
    for payload, score in hits:
        out.append({**payload, "score": round(float(score), 4)})
    return out


def upsert_lesson(repo_root: Path | str, lesson: Lesson, *, store=None) -> bool:
    """Write-through: index a single just-confirmed lesson. Best-effort —
    returns False on any failure (advisory telemetry must never perturb a run)."""
    try:
        if store is None:
            store = _default_store(repo_root)
        vec = embed_text(lesson_embed_text(lesson))
        store.upsert(lesson.lesson_id, vec, _payload(lesson))
        return True
    except Exception:
        return False
