"""ABL-0018 Stage 3 — cross-target ("community") cumulative learning.

The mission pillar *"what's learned on one target carries forward."* Stages 1/1.5/4
made learning cumulative WITHIN a target. This module makes it cumulative ACROSS
targets: a failure mode independently confirmed on ≥N distinct targets — or an
operator/architect-curated obviously-general lesson — **graduates** into a shared
GLOBAL store that every target's roles consult. A fresh target inherits the global
layer on day one.

Two crossing mechanisms (operator decision 2026-06-11 — ABL-0018 §3 option C):

- **recurrence** (canonical, un-gated, scaling): at ``sprint_complete`` a
  best-effort pass embeds each target's confirmed lessons and clusters them across
  targets (cosine ≥ ``GRADUATION_MIN_SCORE``); any cluster spanning ≥``N`` distinct
  targets graduates a representative. Recurrence across *independent* targets is a
  stronger generality signal than a single human glance.
- **curated** (bootstrap + safety valve): ``seed_global_lesson`` lets the architect/
  operator promote an obviously-stack-agnostic lesson, honestly provenance-tagged
  (``graduation_kind="curated"``) so the store stays un-poisoned.

**Substrate** lives in the CORE project, never in any target repo (it is cross-target
by definition): ``webapp/backend/.crew-memory/global_lessons.jsonl`` is the durable,
operator-auditable source of truth; the Milvus collection ``lessons_global`` (fixed
name — collision-free vs the per-target ``lessons_<md5>``) is the vector index for
the semantic pull.

Like per-target lessons, global lessons are **advisory evidence the agent weighs,
not rules that bind** (I-2 / doctrine untouched). Every public read NEVER raises
into a sprint — a global-store outage degrades to per-target (or empty), never
breaks a run.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.services import lessons as _lessons
from app.services import lessons_index as _li
from app.services.lessons import Lesson


# ─── master kill-switch (DORMANT BY DEFAULT) ────────────────────────────────
# Operator directive 2026-06-11: cross-target (Stage 3) transfer must stay
# DORMANT and not be used in any run. This single switch gates ALL three
# CONSUMPTION paths — the push block, the merged search_lessons pull, AND the
# sprint_complete graduation write — so none of them fire unless explicitly
# re-enabled. Default OFF. Reversible: set STAGE3_CROSS_TARGET=1 to reactivate.
# The curated/global store on disk is left intact (it just isn't consumed).
def enabled() -> bool:
    """True only when cross-target transfer has been explicitly re-enabled via
    the STAGE3_CROSS_TARGET=1 environment switch. Default OFF → fully dormant."""
    return os.getenv("STAGE3_CROSS_TARGET") == "1"

# Graduation is a STRONGER claim ("these are the same failure mode") than the
# search-relevance floor ("relevant to my problem"), so it sits above
# LESSON_MIN_SCORE (0.55). EMPIRICALLY CALIBRATED (test_global_lessons real bge-m3
# pass, 2026-06-11): a genuine cross-target *twin* (layer-divergence on two
# different stacks) measures cosine ~0.665; unrelated modes measure ~0.46–0.47.
# 0.62 sits in that gap — fires on real twins (headroom ~0.045) while rejecting
# unrelated pairs (margin ~0.15). Conservative by design: false-negatives are
# recovered by the curated-seed path + future recurrence; false-positives poison
# cross-target memory, so we bias high.
GRADUATION_MIN_SCORE = 0.62

# Minimum distinct targets a cluster must span to graduate. N=2 = the minimal
# generality signal (independently confirmed on ≥2 targets). Raising it later is a
# pure tightening.
GRADUATION_MIN_TARGETS = 2

# Fixed global collection name (NOT md5-keyed) — one shared store across all targets.
GLOBAL_COLLECTION = "lessons_global"

GLOBAL_PUSH_CAP = 6  # max global lessons in a single push block


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _target_id(repo_root: Path | str) -> str:
    """Stable, human-legible identity for a target (its resolved dir name)."""
    return Path(repo_root).resolve().name


# ─── model ──────────────────────────────────────────────────────────────────


@dataclass
class GlobalLesson:
    """A lesson that has crossed into cross-target memory. Carries the richest
    dossier body + Stage-3 provenance so the crossing is always auditable."""
    global_lesson_id: str       # idempotency key (see _recurrence_id / _curated_id)
    classification: str
    body: str                   # richest dossier (root_cause + fix_locus), capped
    origin_targets: list[str]   # distinct target ids the mode was confirmed on
    origin_finding_ids: list[str]
    target_count: int
    graduation_kind: str        # "recurrence" | "curated"
    graduated_ts: str
    note: str = ""              # curated rationale / provenance note

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> "GlobalLesson":
        d = json.loads(line)
        return cls(
            global_lesson_id=d["global_lesson_id"],
            classification=d.get("classification", "uncertain"),
            body=d.get("body", ""),
            origin_targets=list(d.get("origin_targets", [])),
            origin_finding_ids=list(d.get("origin_finding_ids", [])),
            target_count=int(d.get("target_count", len(d.get("origin_targets", [])) or 1)),
            graduation_kind=d.get("graduation_kind", "recurrence"),
            graduated_ts=d.get("graduated_ts", ""),
            note=d.get("note", ""),
        )


def _recurrence_id(finding_ids: list[str]) -> str:
    return "g-" + hashlib.sha256("|".join(sorted(finding_ids)).encode("utf-8")).hexdigest()[:22]


def _curated_id(slug: str, body: str) -> str:
    return "gc-" + hashlib.sha256((slug + "\n" + body).encode("utf-8")).hexdigest()[:21]


# ─── jsonl source of truth ──────────────────────────────────────────────────


def crew_memory_dir() -> Path:
    """webapp/backend/.crew-memory/  (parents[2] of app/services/global_lessons.py)."""
    return Path(__file__).resolve().parents[2] / ".crew-memory"


def global_lessons_path() -> Path:
    return crew_memory_dir() / "global_lessons.jsonl"


def _append_record(gl: GlobalLesson, *, path: Optional[Path] = None) -> bool:
    """Append-only write (event-log style; dedup happens on read). Never raises."""
    p = path if path is not None else global_lessons_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(gl.to_json() + "\n")
        return True
    except Exception:
        return False


def list_global_lessons(
    *, cap: Optional[int] = None, path: Optional[Path] = None
) -> list[GlobalLesson]:
    """Read the global store, dedup by ``global_lesson_id`` (latest record wins —
    append-only log semantics), rank by ``target_count`` desc then recency. Never
    raises; empty list when the store is absent/empty."""
    p = path if path is not None else global_lessons_path()
    by_id: dict[str, GlobalLesson] = {}
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            gl = GlobalLesson.from_json(line)
        except Exception:
            continue
        by_id[gl.global_lesson_id] = gl  # latest wins
    out = list(by_id.values())
    out.sort(key=lambda g: g.graduated_ts, reverse=True)
    out.sort(key=lambda g: g.target_count, reverse=True)
    return out[:cap] if cap is not None else out


# ─── render (push block, Stage-1 analog) ────────────────────────────────────

_GLOBAL_BODY_CAP = 600


def _cap_body(body: str) -> str:
    body = (body or "").strip()
    if len(body) > _GLOBAL_BODY_CAP:
        body = body[: _GLOBAL_BODY_CAP - 1].rstrip() + "…"
    return body


def render_global_lessons_block(
    global_lessons: list[GlobalLesson], *, cap: int = GLOBAL_PUSH_CAP
) -> str:
    """Advisory markdown block of cross-target lessons. Returns "" when empty
    (silent injection). Distinct framing from the per-target block: these recurred
    across MULTIPLE codebases/stacks, so they are general hazards — but still
    advisory, ground against the current code."""
    gls = (global_lessons or [])[:cap]
    if not gls:
        return ""
    out: list[str] = [
        "",
        "---",
        "",
        "## Cross-target lessons (advisory — learned across multiple codebases)",
        "",
        "These failure modes were confirmed on **multiple independent target "
        "codebases** (different stacks), so they are general hazards worth "
        "checking for here. Treat them as **falsification priors — evidence to "
        "weigh, not rules that bind**. An honest assessment of the code in front "
        "of you always takes precedence.",
        "",
    ]
    for gl in gls:
        tag = "seen across {n} targets".format(n=gl.target_count)
        if gl.graduation_kind == "curated":
            tag += ", curated"
        out.append(f"- **[{gl.classification}]** ({tag}) {_cap_body(gl.body)}")
    # push→pull bridge: even a fresh target with no per-target lessons gets the
    # nudge to pull problem-matched cross-target lessons during grounding.
    out.append("")
    out.append(
        "> When you hit a specific problem, call the **`search_lessons`** "
        "retrieval tool with a short description of it — results tagged "
        "`scope=global` are these cross-target lessons matched to your problem. "
        "Advisory: ground against the current code."
    )
    out.append("")
    return "\n".join(out)


# ─── curated seed (operator/architect crossing) ─────────────────────────────


def seed_global_lesson(
    *,
    classification: str,
    body: str,
    origin_targets: list[str],
    note: str,
    origin_finding_ids: Optional[list[str]] = None,
    path: Optional[Path] = None,
    index: bool = True,
) -> GlobalLesson:
    """Curated crossing: promote an obviously-general lesson into the global store
    with honest provenance (``graduation_kind="curated"``). Idempotent by content.
    Best-effort indexes into ``lessons_global`` unless ``index=False``."""
    slug = classification + ":" + "+".join(sorted(origin_targets))
    gl = GlobalLesson(
        global_lesson_id=_curated_id(slug, body),
        classification=classification,
        body=_cap_body(body),
        origin_targets=sorted(set(origin_targets)),
        origin_finding_ids=list(origin_finding_ids or []),
        target_count=len(set(origin_targets)),
        graduation_kind="curated",
        graduated_ts=_now_iso(),
        note=note,
    )
    _append_record(gl, path=path)
    if index:
        try:
            index_global_lessons([gl])
        except Exception:
            pass
    return gl


# ─── vector index + semantic pull (Milvus lessons_global) ───────────────────


def _global_store(store=None):
    if store is not None:
        return store
    try:
        return _li.MilvusLessonStore(GLOBAL_COLLECTION)
    except Exception:
        return _li.InMemoryLessonStore()


def _global_payload(gl: GlobalLesson) -> dict:
    return {
        "finding_id": gl.global_lesson_id,
        "feature_slug": "(global:%d)" % gl.target_count,
        "classification": gl.classification,
        "verdict": "confirmed",
        "scope": "global",
        "body": gl.body,
        "source_run_id": gl.graduation_kind,
    }


def index_global_lessons(global_lessons: Optional[list[GlobalLesson]] = None, *, store=None) -> int:
    """Embed + upsert global lessons into ``lessons_global``. Reads the jsonl store
    when not given an explicit list. Skips a lesson whose embedding fails."""
    store = _global_store(store)
    gls = global_lessons if global_lessons is not None else list_global_lessons()
    n = 0
    for gl in gls:
        try:
            vec = _li.embed_text(f"[{gl.classification}] {gl.body}".strip())
        except Exception:
            continue
        store.upsert(gl.global_lesson_id, vec, _global_payload(gl))
        n += 1
    return n


def search_global_lessons(
    query: str,
    *,
    k: int = _li.DEFAULT_SEARCH_K,
    min_score: float = _li.LESSON_MIN_SCORE,
    store=None,
    build_if_empty: bool = True,
) -> list[dict]:
    """Semantic pull from the global store. NEVER raises → ``[]`` on any failure.
    Each hit carries ``scope="global"`` so the agent can tell cross-target lessons
    from per-target ones."""
    try:
        store = _global_store(store)
        if build_if_empty and store.count() == 0:
            index_global_lessons(store=store)
        qvec = _li.embed_text(query)
        hits = store.search(qvec, k=k, min_score=min_score)
    except Exception:
        return []
    return [{**payload, "score": round(float(score), 4)} for payload, score in hits]


def search_lessons_merged(
    repo_root: Path | str,
    query: str,
    *,
    k: int = _li.DEFAULT_SEARCH_K,
    min_score: float = _li.LESSON_MIN_SCORE,
    target_store=None,
    global_store=None,
) -> list[dict]:
    """The Stage-3 read-path: union the per-target pull (Stage 1.5) with the global
    pull, each hit scope-tagged, sorted by score, capped at ``k``. A fresh target
    with zero per-target lessons still gets the global layer. Never raises."""
    target_hits = _li.search_lessons(
        repo_root, query, k=k, min_score=min_score, store=target_store
    )
    global_hits = search_global_lessons(
        query, k=k, min_score=min_score, store=global_store
    )
    merged = list(target_hits) + list(global_hits)
    # de-dup by finding_id (a curated seed can share an origin finding id), keep best score
    best: dict[str, dict] = {}
    for h in merged:
        fid = h.get("finding_id", "")
        if fid not in best or h.get("score", 0) > best[fid].get("score", 0):
            best[fid] = h
    out = sorted(best.values(), key=lambda h: h.get("score", 0.0), reverse=True)
    return out[:k]


# ─── recurrence graduation (the canonical write-path) ───────────────────────


@dataclass
class _CandidateLesson:
    target_id: str
    finding_id: str
    classification: str
    body: str
    vec: list[float] = field(default_factory=list)


def _gather_candidates(targets: list[Path | str]) -> list[_CandidateLesson]:
    """All confirmed lessons across the given targets, tagged with target id +
    embedded. Embedding failures drop that candidate (never abort)."""
    out: list[_CandidateLesson] = []
    for repo_root in targets:
        tid = _target_id(repo_root)
        for lesson in _lessons.list_lessons(repo_root, cap=None):
            try:
                vec = _li.embed_text(_li.lesson_embed_text(lesson))
            except Exception:
                continue
            out.append(_CandidateLesson(
                target_id=tid,
                finding_id=lesson.lesson_id,
                classification=lesson.classification,
                body=_lessons._lesson_body(lesson),
                vec=vec,
            ))
    return out


def _cluster(cands: list[_CandidateLesson], *, min_score: float) -> list[list[int]]:
    """Union-find over candidate indices: connect any pair with cosine ≥ floor.
    Returns clusters as lists of indices."""
    parent = list(range(len(cands)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(len(cands)):
        for j in range(i + 1, len(cands)):
            if _li._cosine(cands[i].vec, cands[j].vec) >= min_score:
                union(i, j)

    clusters: dict[int, list[int]] = {}
    for i in range(len(cands)):
        clusters.setdefault(find(i), []).append(i)
    return list(clusters.values())


def known_target_roots() -> list[Path]:
    """Resolved roots of every registered target carrying a findings-ledger tree.
    The crew's target registry is ``webapp/backend/repos/*`` (symlinks to the real
    brownfield targets). Graduation compares confirmed lessons across these."""
    repos = Path(__file__).resolve().parents[2] / "repos"
    out: list[Path] = []
    try:
        for entry in sorted(repos.iterdir()):
            try:
                root = entry.resolve()
            except Exception:
                continue
            if (root / "_brownfield" / "features").exists() and root not in out:
                out.append(root)
    except Exception:
        return []
    return out


def graduate_all(**kw) -> list[GlobalLesson]:
    """Run the recurrence graduation pass across every registered target."""
    return graduate(known_target_roots(), **kw)


def graduate(
    targets: list[Path | str],
    *,
    min_score: float = GRADUATION_MIN_SCORE,
    min_targets: int = GRADUATION_MIN_TARGETS,
    path: Optional[Path] = None,
    index: bool = True,
    candidates: Optional[list[_CandidateLesson]] = None,
) -> list[GlobalLesson]:
    """Recurrence graduation: cluster confirmed lessons across ``targets``; any
    cluster spanning ≥``min_targets`` DISTINCT targets graduates a representative
    (richest dossier = longest body) into the global store. Idempotent by
    ``_recurrence_id`` (the sorted member finding-ids). Best-effort: returns the
    list graduated this pass; never raises into a sprint.

    ``candidates`` is injectable so tests can drive synthetic vectors without
    Ollama; production gathers + embeds via ``_gather_candidates``.
    """
    try:
        cands = candidates if candidates is not None else _gather_candidates(targets)
        if len(cands) < 2:
            return []
        graduated: list[GlobalLesson] = []
        for cluster in _cluster(cands, min_score=min_score):
            members = [cands[i] for i in cluster]
            distinct_targets = sorted({m.target_id for m in members})
            if len(distinct_targets) < min_targets:
                continue
            rep = max(members, key=lambda m: len(m.body))
            finding_ids = sorted({m.finding_id for m in members})
            gl = GlobalLesson(
                global_lesson_id=_recurrence_id(finding_ids),
                classification=rep.classification,
                body=_cap_body(rep.body),
                origin_targets=distinct_targets,
                origin_finding_ids=finding_ids,
                target_count=len(distinct_targets),
                graduation_kind="recurrence",
                graduated_ts=_now_iso(),
            )
            _append_record(gl, path=path)
            graduated.append(gl)
        if index and graduated:
            try:
                index_global_lessons(graduated)
            except Exception:
                pass
        return graduated
    except Exception:
        return []
