"""Read `.agile-v/BACKLOG.md` produced by the PO agent into structured items.

The format is the agentic-skills convention:

    # Backlog: <Project>

    ## BL-0001: Short Title
    **Type:** Feature · **Priority:** CRITICAL
    **Story:** As a user, I want ...
    **Acceptance:**
    1. ...
    2. ...
    **Effort:** 3 · **Dependencies:** none · **Status:** Ready

    ## BL-0002: ...
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


BL_HEADING_RE = re.compile(r"^##\s+(BL-\d{4}):\s+(.+?)\s*$", re.MULTILINE)
META_RE = re.compile(r"\*\*(\w+(?:\s+\w+)*):\*\*\s*([^*\n]+?)(?=\s*(?:·|\*\*|\n|$))")

# The `**Acceptance:**` block is a numbered list. Each numbered item is one
# acceptance criterion. The block ends at the next standalone `**Meta:**` marker
# (Effort/Dependencies/Status/Risk/Spike…) that begins a line.
ACCEPTANCE_MARKER_RE = re.compile(r"\*\*Acceptance\s*:?\*\*", re.IGNORECASE)
_NEXT_META_RE = re.compile(r"\n[ \t]*\*\*[A-Z][\w &/]*\s*:?\*\*")
_NUM_ITEM_RE = re.compile(
    r"^[ \t]*(\d+)\.[ \t]+(.*?)(?=\n[ \t]*\d+\.[ \t]|\Z)",
    re.DOTALL | re.MULTILINE,
)
# A criterion shorter than this (after whitespace-normalising) is too thin to be
# a real, testable acceptance criterion — it fails the PO comprehensiveness gate.
MIN_CRITERION_CHARS = 20


@dataclass
class BacklogItem:
    id: str
    title: str
    body: str            # full markdown section for this item, sans heading
    meta: dict[str, str]


@dataclass(frozen=True)
class AcceptanceCriterion:
    """One PO-authored acceptance criterion with a stable, traceable ID.

    The ID ``AC-<BL>-<n>`` is the unit of truth threaded through the whole
    chain: the PO writes it, the engineer's tests must reference it, and the
    acceptance agent must live-verify it. ``n`` is the 1-based position in the
    BL's ``**Acceptance:**`` numbered list.
    """
    id: str          # AC-BL-0003-2
    bl_id: str       # BL-0003
    index: int       # 2
    text: str        # the criterion prose, whitespace-normalised


def _body_of(item) -> tuple[str, str]:
    """Return (bl_id, body) tolerating both BacklogItem and dict shapes."""
    if isinstance(item, dict):
        return item.get("id") or "", item.get("body") or ""
    return getattr(item, "id", "") or "", getattr(item, "body", "") or ""


def extract_criteria(item) -> list[AcceptanceCriterion]:
    """Parse a BL's ``**Acceptance:**`` numbered list into criteria.

    Returns ``[]`` when the BL has no acceptance block (which the PO
    comprehensiveness gate then flags). Robust to multi-line criteria and to
    the block being followed by ``**Effort:** … **Status:** …`` meta.
    """
    bl_id, body = _body_of(item)
    if not bl_id or not body:
        return []
    m = ACCEPTANCE_MARKER_RE.search(body)
    if not m:
        return []
    tail = body[m.end():]
    stop = _NEXT_META_RE.search(tail)
    block = tail[: stop.start()] if stop else tail
    out: list[AcceptanceCriterion] = []
    for nm in _NUM_ITEM_RE.finditer(block):
        n = int(nm.group(1))
        text = " ".join(nm.group(2).split())
        if text:
            out.append(AcceptanceCriterion(
                id=f"AC-{bl_id}-{n}", bl_id=bl_id, index=n, text=text))
    return out


def all_criteria(items) -> dict[str, list[AcceptanceCriterion]]:
    """Map every BL id -> its acceptance criteria (in document order)."""
    return {bl_id: extract_criteria(it)
            for it in items
            for bl_id, _ in [_body_of(it)] if bl_id}


def criteria_for(text: str, bl_id: str) -> list[AcceptanceCriterion]:
    """Convenience: parse full BACKLOG.md text, return one BL's criteria."""
    for it in parse(text):
        if it.id == bl_id:
            return extract_criteria(it)
    return []


def thin_criteria_report(items) -> dict[str, str]:
    """Identify BLs whose acceptance criteria are missing or too thin.

    A BL passes the PO comprehensiveness gate only with **≥2** criteria, each at
    least ``MIN_CRITERION_CHARS`` after whitespace-normalisation. Returns
    ``{bl_id: reason}`` for every BL that fails (empty dict ⇒ all comprehensive).
    """
    bad: dict[str, str] = {}
    for it in items:
        bl_id, _ = _body_of(it)
        if not bl_id:
            continue
        crits = extract_criteria(it)
        substantive = [c for c in crits if len(c.text) >= MIN_CRITERION_CHARS]
        if len(crits) == 0:
            bad[bl_id] = "no **Acceptance:** criteria at all"
        elif len(substantive) < 2:
            bad[bl_id] = (
                f"only {len(substantive)} substantive criterion/criteria "
                f"(need >=2, each >= {MIN_CRITERION_CHARS} chars, specific & testable)"
            )
    return bad


def find_backlog(repo_path: Path, feature_slug: str | None = None) -> Path | None:
    """Locate the BACKLOG.md for this sprint.

    Resolution order:
    1. If feature_slug is given: ``_brownfield/features/<slug>/BACKLOG.md``
       (A18 per-feature isolation — canonical location going forward).
    2. Legacy: ``.agile-v/BACKLOG.md`` (pre-A18 sprints used this).
    3. Shallow filesystem walk for any BACKLOG.md (last resort).
    """
    if feature_slug:
        feat = repo_path / "_brownfield" / "features" / feature_slug / "BACKLOG.md"
        if feat.is_file():
            return feat
    legacy = repo_path / ".agile-v" / "BACKLOG.md"
    if legacy.is_file():
        return legacy
    for p in repo_path.glob("**/BACKLOG.md"):
        if ".venv" in p.parts or "node_modules" in p.parts:
            continue
        return p
    return None


def parse(text: str) -> list[BacklogItem]:
    items: list[BacklogItem] = []
    headings = list(BL_HEADING_RE.finditer(text))
    for i, m in enumerate(headings):
        bl_id, title = m.group(1), m.group(2).strip()
        body_start = m.end()
        body_end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = text[body_start:body_end].strip()
        meta = {k.strip().lower(): v.strip() for k, v in META_RE.findall(body)}
        items.append(BacklogItem(id=bl_id, title=title, body=body, meta=meta))
    return items


def parse_file(path: Path) -> list[BacklogItem]:
    return parse(path.read_text(encoding="utf-8", errors="replace"))


def extract_section(text: str, bl_id: str) -> str | None:
    """Return the heading + body of a single BL section for prompting the engineer."""
    headings = list(BL_HEADING_RE.finditer(text))
    for i, m in enumerate(headings):
        if m.group(1) == bl_id:
            body_end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
            return text[m.start():body_end].rstrip()
    return None
