"""ABL-0019 — per-target Pattern Profile (cumulative learning, Stage 4).

Every engineer writes ``_brownfield/{bl_id}/eng_patterns.md`` (this target's
layering, naming, DI idioms, invariants, compatibility strategy) — and today it
is written, existence-checked (R10/R11), and then DISCARDED: nothing reads its
content back, so each new engineer re-derives the same conventions from scratch.

This module consolidates those per-BL artifacts into a durable, semantically
retrievable per-target **pattern profile**: the engineer about to touch the data
layer pulls "how this codebase does persistence/validation/DI" by problem
statement, instead of re-deriving it. Pattern Fidelity compounds per target.

Symmetric to the findings→lessons loop (A62/A63 + ABL-0016 Stage 1.5): this is
the eng_patterns→patterns loop, and it REUSES Stage 1.5's machinery
(``lessons_index``: embed via Ollama bge-m3, Milvus store, relevance floor).
Advisory only — a pattern is "how this codebase does X", not a binding rule; the
agent grounds against the current code. Read path NEVER raises into a sprint.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from app.services import lessons_index as _li

# Sections of eng_patterns.md that carry DURABLE, cross-BL codebase knowledge
# (vs BL-specific noise like "planned slices" / this-BL blast radius / the
# closest-analog-to-THIS-bl list). Matched as case-insensitive substrings of the
# `##` header. See prompts_brownfield.py:308-334 for the authored structure.
DURABLE_SECTION_HINTS = (
    "architectural pattern",
    "invariant",
    "compatibility",
    "naming",
    "layering",
)

_BODY_CAP = 800  # per-entry body cap (mirrors lessons; bounds prompt bloat)


@dataclass
class PatternEntry:
    pattern_id: str       # stable: sha256(area + normalized body)
    area: str             # the eng_patterns.md section header
    bl_id: str            # provenance
    feature_slug: str
    text: str             # the section body (capped)


def _stable_id(area: str, text: str) -> str:
    norm = re.sub(r"\s+", " ", f"{area}\n{text}").strip().lower()
    return "pat:" + hashlib.sha256(norm.encode("utf-8")).hexdigest()[:24]


def _iter_eng_patterns(repo_root: Path) -> Iterator[tuple[Path, str, str]]:
    """Yield (path, bl_id, feature_slug) for every eng_patterns.md in the target.
    Handles both the A18 per-feature layout
    (``_brownfield/features/<slug>/<bl_id>/eng_patterns.md``) and the legacy
    ``_brownfield/<bl_id>/eng_patterns.md``."""
    base = repo_root / "_brownfield"
    if not base.exists():
        return
    for p in sorted(base.rglob("eng_patterns.md")):
        parts = p.relative_to(base).parts
        bl_id = p.parent.name
        feature_slug = ""
        if "features" in parts:
            i = parts.index("features")
            if i + 1 < len(parts):
                feature_slug = parts[i + 1]
        yield p, bl_id, feature_slug


def _split_sections(md_text: str) -> list[tuple[str, str]]:
    """Split markdown into (header, body) on ``## `` lines. The leading
    ``# Title`` and any preamble are ignored."""
    out: list[tuple[str, str]] = []
    cur_header: Optional[str] = None
    cur_body: list[str] = []
    for line in md_text.splitlines():
        if line.startswith("## "):
            if cur_header is not None:
                out.append((cur_header, "\n".join(cur_body).strip()))
            cur_header = line[3:].strip()
            cur_body = []
        elif cur_header is not None:
            cur_body.append(line)
    if cur_header is not None:
        out.append((cur_header, "\n".join(cur_body).strip()))
    return out


def _is_durable(header: str) -> bool:
    h = header.lower()
    return any(hint in h for hint in DURABLE_SECTION_HINTS)


def extract_patterns(repo_root: Path | str) -> list[PatternEntry]:
    """Glob eng_patterns.md across the target, keep the durable convention
    sections, and dedup near-identical conventions (the common case: every BL
    restates the same layering). Returns ranked-stable entries."""
    repo_root = Path(repo_root)
    by_id: dict[str, PatternEntry] = {}
    for path, bl_id, feature_slug in _iter_eng_patterns(repo_root):
        try:
            md = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for header, body in _split_sections(md):
            if not body or not _is_durable(header):
                continue
            text = body[:_BODY_CAP]
            pid = _stable_id(header, text)
            if pid not in by_id:  # dedup: identical convention across BLs
                by_id[pid] = PatternEntry(
                    pattern_id=pid, area=header, bl_id=bl_id,
                    feature_slug=feature_slug, text=text,
                )
    return list(by_id.values())


# ─── consolidated human-readable profile ────────────────────────────────────


def profile_path(repo_root: Path | str) -> Path:
    return Path(repo_root) / "_brownfield" / "_pattern_profile" / "PATTERN_PROFILE.md"


def consolidate(repo_root: Path | str, *, entries: Optional[list[PatternEntry]] = None) -> str:
    """Write a deduped, area-grouped PATTERN_PROFILE.md (human/operator readable +
    a fallback push source). Returns the rendered text."""
    repo_root = Path(repo_root)
    if entries is None:
        entries = extract_patterns(repo_root)
    by_area: dict[str, list[PatternEntry]] = {}
    for e in entries:
        by_area.setdefault(e.area, []).append(e)
    lines = ["# Pattern Profile (consolidated, advisory)", "",
             "Durable conventions distilled from prior engineers' "
             "`eng_patterns.md` on THIS codebase. Advisory — ground against the "
             "current code; a convention is a pointer, not a rule.", ""]
    for area in sorted(by_area):
        lines.append(f"## {area}")
        for e in by_area[area]:
            src = f"{e.feature_slug}/{e.bl_id}" if e.feature_slug else e.bl_id
            lines.append(f"\n_(from {src})_\n{e.text}")
        lines.append("")
    text = "\n".join(lines)
    try:
        p = profile_path(repo_root)
        p.parent.mkdir(parents=True, exist_ok=True)
        # A65: PATTERN_PROFILE.md is a per-sprint RUNTIME artifact — it must NEVER
        # dirty the target's tracked working tree. A modified tracked file fails
        # the merge precondition ("main checkout has modified tracked files; not
        # merging") and silently blocks any merge that follows the refresh (it
        # blocked the acceptance-followup merge in run-20260609T133620Z-fb16cc).
        # Drop a .gitignore so the dir's contents are never tracked on ANY target
        # — generalizing A58's events.jsonl/graphify-out fix to the standing rule
        # "no harness runtime artifact leaves the target's tracked tree dirty".
        # (The Milvus index is the functional read path; the .md is an operator
        # bonus that does not need version control.)
        gi = p.parent / ".gitignore"
        if not gi.exists():
            gi.write_text(
                "# A65: harness runtime artifact (ABL-0019 pattern profile) —\n"
                "# regenerated every sprint; never track it (a modified tracked\n"
                "# file dirties the tree and blocks subsequent merges).\n*\n",
                encoding="utf-8",
            )
        p.write_text(text, encoding="utf-8")
    except Exception:
        pass  # the vector index is the functional read path; the .md is a bonus
    return text


# ─── vector store (reuses lessons_index primitives) ─────────────────────────


def collection_for(repo_root: Path | str) -> str:
    h = hashlib.md5(str(Path(repo_root).resolve()).encode("utf-8")).hexdigest()[:8]
    return f"patterns_{h}"


def _default_store(repo_root: Path | str):
    try:
        return _li.MilvusLessonStore(collection_for(repo_root))
    except Exception:
        return _li.InMemoryLessonStore()


def _payload(e: PatternEntry) -> dict:
    # Map onto lessons_index's store field names so the backends work unchanged.
    # area is folded into body so it survives Milvus output_fields.
    return {
        "finding_id": e.pattern_id,
        "feature_slug": e.feature_slug,
        "classification": "pattern",
        "verdict": "",
        "scope": "target",
        "body": f"({e.area}) {e.text}",
        "source_run_id": e.bl_id,
    }


def index_patterns(repo_root: Path | str, *, store=None,
                   entries: Optional[list[PatternEntry]] = None) -> int:
    """Embed + upsert the target's durable patterns into the vector store.
    Returns count indexed. Skips an entry whose embedding fails (never aborts)."""
    if store is None:
        store = _default_store(repo_root)
    if entries is None:
        entries = extract_patterns(repo_root)
    n = 0
    for e in entries:
        try:
            vec = _li.embed_text(f"[{e.area}] {e.text}")
        except Exception:
            continue
        store.upsert(e.pattern_id, vec, _payload(e))
        n += 1
    return n


def search_patterns(
    repo_root: Path | str,
    query: str,
    *,
    k: int = _li.DEFAULT_SEARCH_K,
    min_score: float = _li.LESSON_MIN_SCORE,
    store=None,
    build_if_empty: bool = True,
) -> list[dict]:
    """Return durable conventions nearest the problem ``query`` above the floor.
    NEVER raises — any infra failure yields ``[]`` (advisory; never perturbs a
    sprint). Each hit: {pattern_id, area(in body), body, score, kind:'pattern'}."""
    try:
        if store is None:
            store = _default_store(repo_root)
        if build_if_empty and store.count() == 0:
            index_patterns(repo_root, store=store)
        qvec = _li.embed_text(query)
        hits = store.search(qvec, k=k, min_score=min_score)
    except Exception:
        return []
    out = []
    for payload, score in hits:
        out.append({**payload, "kind": "pattern", "score": round(float(score), 4)})
    return out
