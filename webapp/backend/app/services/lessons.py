"""ABL-0016 Batch A — lessons reader + renderer (cumulative learning Stage 1).

Surfaces prior operator-CONFIRMED (and deferred) acceptance findings as
*advisory* context for the agent roles, closing the cumulative read-path
gap: today the §I.3 findings ledger is read by the acceptance agent only.

v1 source is the findings ledger; the reader is **target-scoped** — it
unions findings across *all* feature ledgers in the repo
(``_brownfield/features/*/acceptance/findings_log.jsonl``). This is
deliberate: the ledger is keyed per feature and written at sprint *end*,
so feature-scoped lessons are useless within a sprint; the value is
cross-feature memory on the same target (feature B learns from feature A's
confirmed bugs). See ABL-0016_LESSONS_AS_CONTEXT.md §2.4.

Lessons are **advisory, not binding** ("falsification priors, not bans" —
the §I.3 framing): evidence the agent weighs against its own grounding,
never a rule. No new R-rule lands here (I-2 unaffected).

Dormant until ABL-0016 Batch B wires ``render_lessons_block`` into the
brownfield role prompts. Zero call sites in this batch.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from app.services.findings_ledger import Finding


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# Verdicts that make a finding a durable lesson worth remembering. ``refuted``
# (operator said false positive) and ``None`` (untriaged) are excluded — only
# operator-blessed real bugs become advisory lessons. This is the conservative
# gate that keeps the read path trustworthy.
LESSON_VERDICTS = frozenset({"confirmed", "deferred"})

# Default cap on lessons rendered into a single prompt. Guards against prompt
# bloat crowding the role's actual task; the highest-ranked survive.
DEFAULT_LESSON_CAP = 8


@dataclass
class Lesson:
    """A durable, advisory record the crew can consult. Source-agnostic so
    later stages (gate failures, doctrine rules, pattern profiles) can add
    kinds; v1 only produces ``kind="finding"`` from the ledger."""
    lesson_id: str          # reuse finding_id (stable across runs)
    kind: str               # "finding" (v1)
    feature_slug: str       # provenance: which feature produced it
    classification: str     # product_bug | test_bug | data_bug | infra_bug | uncertain
    summary: str
    verdict: str            # confirmed | deferred
    seen_count: int
    last_seen_ts: str
    source_run_id: str
    report_path: str
    # A63: the A61 verified dossier, when the finding carries one. The
    # ``root_cause`` (causal chain) and ``fix_locus`` (the surfaces the defect
    # touched) are the durable, actionable knowledge a future agent should
    # learn — far richer than the thin ``evidence_summary`` (which is often a
    # serialized status blob). Empty for pre-A61 findings.
    root_cause: str = ""
    fix_locus: str = ""

    @classmethod
    def from_finding(cls, f: Finding) -> "Lesson":
        return cls(
            lesson_id=f.finding_id,
            kind="finding",
            feature_slug=f.feature_slug,
            classification=f.classification,
            summary=f.evidence_summary,
            verdict=f.verdict or "",
            seen_count=f.seen_count,
            last_seen_ts=f.last_seen_ts,
            source_run_id=f.run_id,
            report_path=f.report_path,
            # getattr keeps this tolerant of older Finding shapes in tests.
            root_cause=(getattr(f, "root_cause", "") or ""),
            fix_locus=(getattr(f, "fix_locus", "") or ""),
        )


def _iter_feature_ledgers(repo_root: Path) -> Iterator[Path]:
    """Yield every per-feature findings ledger under the target."""
    base = repo_root / "_brownfield" / "features"
    if not base.exists():
        return
    yield from sorted(base.glob("*/acceptance/findings_log.jsonl"))


def _read_findings(path: Path) -> list[Finding]:
    """Tolerant read of one ledger file; skips malformed lines (mirrors
    FindingsLedger._read_all_unlocked)."""
    out: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(Finding.from_jsonl(line))
        except Exception:
            continue
    return out


def list_lessons(
    repo_root: Path | str,
    feature_slug: Optional[str] = None,
    *,
    cap: Optional[int] = None,
) -> list[Lesson]:
    """Return target-scoped lessons, ranked for prompt injection.

    Unions confirmed/deferred findings across every feature ledger in the
    target, dedups by ``finding_id`` (keeping the higher ``seen_count``),
    and ranks: same-``feature_slug`` first (if given), then by recency,
    then by ``seen_count`` — so the most relevant, most-recurring lessons
    survive the ``cap``.

    Read-only; never raises on a missing/corrupt ledger (returns what it
    can). Empty list when the target has no lessons yet.
    """
    repo_root = Path(repo_root)
    by_id: dict[str, Finding] = {}
    for ledger_path in _iter_feature_ledgers(repo_root):
        for f in _read_findings(ledger_path):
            if f.verdict not in LESSON_VERDICTS:
                continue
            existing = by_id.get(f.finding_id)
            if existing is None or f.seen_count > existing.seen_count:
                by_id[f.finding_id] = f

    findings = list(by_id.values())
    # Stable multi-key sort: recency first (ISO-8601 sorts lexically), then a
    # stable pass on (same-feature, -seen_count) so same-feature + high-recur
    # lessons rise without losing the recency tiebreak.
    findings.sort(key=lambda f: f.last_seen_ts, reverse=True)
    findings.sort(
        key=lambda f: (
            0 if (feature_slug and f.feature_slug == feature_slug) else 1,
            -f.seen_count,
        )
    )
    lessons = [Lesson.from_finding(f) for f in findings]
    if cap is not None:
        lessons = lessons[:cap]
    return lessons


# A63: per-lesson body cap. The verified root_cause can be long; bound it so a
# handful of lessons can't crowd out the agent's actual task. Generous enough to
# carry the causal chain + fix locus, not the whole dossier.
_LESSON_BODY_CAP = 600


def _lesson_body(lesson: Lesson) -> str:
    """A63: the most useful description of a lesson.

    Prefer the A61 verified ``root_cause`` (the causal chain) + ``fix_locus``
    (the surfaces the defect touched) — that is the durable, actionable
    knowledge. Fall back to the thin ``evidence_summary`` only when no dossier
    exists (pre-A61 findings). This connects A61's dossiers to the ABL-0016
    read-path so the crew learns *why* and *where*, not a status code."""
    if lesson.root_cause.strip():
        body = lesson.root_cause.strip()
        if lesson.fix_locus.strip():
            body = f"{body}  (fix locus: {lesson.fix_locus.strip()})"
    else:
        body = (lesson.summary or "").strip()
    if len(body) > _LESSON_BODY_CAP:
        body = body[: _LESSON_BODY_CAP - 1].rstrip() + "…"
    return body


def render_lessons_block(lessons: list[Lesson], *, bl_id: Optional[str] = None) -> str:
    """Render lessons as an advisory markdown block for prompt injection.

    Returns the empty string when there are no lessons — silent injection,
    no prompt noise (mirrors ``_build_priors_block``). The block leads with
    the advisory framing so the agent treats lessons as falsification
    priors, not bans. Each lesson renders its richest available body (A63:
    verified root_cause + fix_locus, else the thin evidence summary).
    """
    if not lessons:
        return ""
    out: list[str] = [
        "",
        "---",
        "",
        "## Relevant prior lessons (advisory)",
        "",
        "These are operator-confirmed findings from prior work on THIS "
        "codebase. Treat them as **falsification priors — evidence to weigh, "
        "not rules that bind**. Ground each against the current code before "
        "acting; a lesson is a pointer to a hazard, not a verdict, and an "
        "honest assessment of the code in front of you always takes "
        "precedence.",
        "",
    ]
    for lesson in lessons:
        out.append(
            f"- **[{lesson.classification}]** ({lesson.feature_slug}) "
            f"{_lesson_body(lesson)}"
        )
    # ABL-0016 Stage 1.5: push→pull bridge. The list above is the top recurring
    # lessons; more may exist. Tell the agent it can retrieve lessons matched to
    # its SPECIFIC problem via the search_lessons tool.
    out.append("")
    out.append(
        "> More prior lessons may exist for this codebase. When you hit a "
        "specific problem, call the **`search_lessons`** retrieval tool with a "
        "short description of that problem to pull the closest-matching prior "
        "lesson(s) — same advisory weight as above."
    )
    out.append("")
    return "\n".join(out)


# ─── ABL-0016 Batch C: injection provenance ────────────────────────────────
# Records WHICH lessons were injected into WHICH role's prompt, per run. This
# is the hook Stage 2 (ABL-0017 closed-loop efficacy) consumes to attribute
# outcomes: "BL-0007's engineer was advised of lesson X — did it avoid the
# class X warns about?". Provenance is framework telemetry, not a target
# artifact, so it lives under the backend logs dir (never in the target repo).


def _default_injection_log_dir() -> Path:
    # webapp/backend/logs/lessons/  (parents[2] of app/services/lessons.py)
    return Path(__file__).resolve().parents[2] / "logs" / "lessons"


def injection_log_path(run_id: str, *, log_dir: Optional[Path] = None) -> Path:
    base = Path(log_dir) if log_dir is not None else _default_injection_log_dir()
    return base / f"{run_id}.jsonl"


def record_injection(
    run_id: str,
    role: str,
    lessons: list[Lesson],
    *,
    bl_id: Optional[str] = None,
    log_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Append one provenance record for a lessons injection.

    No-op (returns ``None``) when ``lessons`` is empty — so the log only ever
    holds *actual* injections, and a flag-ON sprint on a target with no
    lessons writes nothing. Never raises: provenance is advisory telemetry
    and must not perturb a sprint.
    """
    if not lessons:
        return None
    path = injection_log_path(run_id, log_dir=log_dir)
    record = {
        "ts": _now_iso(),
        "run_id": run_id,
        "role": role,
        "bl_id": bl_id,
        "count": len(lessons),
        "lesson_ids": [l.lesson_id for l in lessons],
        "classifications": [l.classification for l in lessons],
        "feature_slugs": sorted({l.feature_slug for l in lessons}),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")
    except Exception:
        return None
    return path
