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


# ── R21: dependency DAG + interface contracts (wave-execution Phase 1) ────────
# The PO declares, per BL, a structured **Dependencies:** list of BL-ids and the
# interface contracts each BL **Exposes:** / **Consumes:**. This is the artifact
# the future wave scheduler reads to parallelize independent BLs and sequence
# dependent ones; in Phase 1 we only PRODUCE + VALIDATE it (execution unchanged).

_BL_ID_RE = re.compile(r"BL-\d{4}")
_NONE_TOKENS = {"none", "n/a", "na", "-", "", "—"}
_EXPOSES_RE = re.compile(
    r"\*\*Exposes\s*:?\*\*\s*(.+?)(?=\n[ \t]*\*\*[A-Z]|\Z)", re.IGNORECASE | re.DOTALL)
_CONSUMES_RE = re.compile(
    r"\*\*Consumes\s*:?\*\*\s*(.+?)(?=\n[ \t]*\*\*[A-Z]|\Z)", re.IGNORECASE | re.DOTALL)


def _meta_of(item) -> dict:
    if isinstance(item, dict):
        return item.get("meta") or {}
    return getattr(item, "meta", {}) or {}


def declared_dependencies(item) -> list[str] | None:
    """BL-ids this BL declares it depends on, from its ``**Dependencies:**`` meta.

    Returns ``None`` when the field is ABSENT (a distinct, flaggable state), ``[]``
    when present and "none". Self-references are kept here and flagged by
    :func:`dependency_report`. The BACKLOG meta parser already lower-cases keys.
    """
    meta = _meta_of(item)
    if "dependencies" not in meta:
        return None
    raw = (meta.get("dependencies") or "").strip()
    if raw.lower() in _NONE_TOKENS:
        return []
    return _BL_ID_RE.findall(raw)


def _normalize_contract(token: str) -> str:
    """Reduce an interface token to a comparable key: the identifier head before
    any ``(`` / ``->`` / ``:`` , whitespace-stripped and lower-cased. So
    ``IRepo.TryDecrement(a,b)->bool`` and ``IRepo.TryDecrement`` compare equal."""
    head = re.split(r"\(|->|::|:|\{|\[", token, maxsplit=1)[0]
    return "".join(head.split()).lower()


def _split_top_level(raw: str) -> list[str]:
    """Split a contract block on top-level ``;`` ``,`` or newline ONLY — never on a
    separator nested inside ``()`` ``[]`` ``{}``. Entity field-lists and method
    arg-lists legitimately contain ``;``/``,`` (e.g. ``Question{id; text}``,
    ``Repo.Try(a, b)``); splitting blindly shattered them into broken tokens and
    produced false R21 contract_errors (a Q&A sprint aborted on this)."""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in raw:
        if ch in "([{":
            depth += 1
            buf.append(ch)
        elif ch in ")]}":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch in ";,\n" and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return parts


def _contract_tokens(item, rx: re.Pattern) -> set[str]:
    _, body = _body_of(item)
    if not body:
        return set()
    m = rx.search(body)
    if not m:
        return set()
    raw = m.group(1)
    parts = _split_top_level(raw)
    out = set()
    for p in parts:
        p = p.strip().lstrip("-*0123456789. \t")
        if p and p.lower() not in _NONE_TOKENS:
            out.add(_normalize_contract(p))
    return out


def adjacency(items) -> dict[str, list[str]]:
    """{bl_id: [declared dep ids]} over all BLs (absent field → [])."""
    adj: dict[str, list[str]] = {}
    for it in items:
        bl_id, _ = _body_of(it)
        if bl_id:
            adj[bl_id] = declared_dependencies(it) or []
    return adj


def topological_waves(items) -> list[list[str]]:
    """Kahn-layer the dependency DAG into execution **waves**: wave[0] are BLs
    with no (in-graph) dependencies; each later wave depends only on earlier ones.

    Raises ``ValueError`` if the graph has a cycle (the unscheduled remainder is
    named in the message). Dangling refs (deps to unknown BLs) are ignored here —
    :func:`dependency_report` flags them separately — so this stays a pure
    scheduling primitive the wave scheduler (Phase 2) can reuse directly.
    """
    adj = adjacency(items)
    known = set(adj)
    indeg = {b: len({d for d in deps if d in known}) for b, deps in adj.items()}
    waves: list[list[str]] = []
    placed: set[str] = set()
    while len(placed) < len(adj):
        layer = sorted(b for b in adj if b not in placed and indeg[b] == 0)
        if not layer:
            remaining = sorted(b for b in adj if b not in placed)
            raise ValueError(f"dependency cycle among {remaining}")
        waves.append(layer)
        placed.update(layer)
        for b in adj:
            if b not in placed:
                indeg[b] = len({d for d in adj[b] if d in known and d not in placed})
    return waves


def dag_width(items) -> int:
    """Max wave width (parallelism degree) of the dependency DAG — the size of the
    widest topological wave. 1 ⇒ fully serial (one BL per wave); ≥2 ⇒ the schedule
    can fan out. 0 for an empty backlog. A cyclic (unschedulable) DAG returns 1 —
    :func:`dependency_report` flags the cycle separately. Contract-First Phase B
    fan-out metric (emitted on ``backlog_parsed``)."""
    if not items:
        return 0
    try:
        waves = topological_waves(items)
    except ValueError:
        return 1
    return max((len(w) for w in waves), default=0)


def dependency_report(items) -> dict[str, str]:
    """R21 DAG validation. Returns ``{bl_id: reason}`` for every BL with a
    dependency defect (empty ⇒ the DAG is well-formed). Checks, per BL:
    missing ``**Dependencies:**`` field, dangling refs (dep to a non-existent
    BL), self-dependency; plus a single ``__cycle__`` entry if the graph is
    cyclic. All are unambiguous and machine-checkable — zero false-positive risk.
    """
    ids = {bl for it in items for bl, _ in [_body_of(it)] if bl}
    bad: dict[str, str] = {}
    for it in items:
        bl_id, _ = _body_of(it)
        if not bl_id:
            continue
        deps = declared_dependencies(it)
        if deps is None:
            bad[bl_id] = ("no **Dependencies:** field (declare 'none' or a list of "
                          "BL-ids this BL builds on — the wave scheduler needs it)")
            continue
        dangling = [d for d in deps if d not in ids]
        if bl_id in deps:
            bad[bl_id] = "declares itself as a dependency (self-loop)"
        elif dangling:
            bad[bl_id] = f"depends on unknown BL-id(s): {', '.join(sorted(set(dangling)))}"
    if not bad:
        try:
            topological_waves(items)
        except ValueError as e:
            bad["__cycle__"] = str(e)
    return bad


def contract_report(items, contract_first: bool = False) -> dict[str, str]:
    """R21 contract-coverage validation. For every interface a BL ``**Consumes:**``,
    that contract must be ``**Exposes:**``d by a BL this one declares as a
    dependency. Returns ``{bl_id: reason}`` for violations (empty ⇒ coherent).

    Contract-First (Phase A, 2026-06-15): when ``contract_first`` is True, an
    interface a BL ``**Consumes:**`` that ANY BL ``**Exposes:**`` is satisfied by
    the materialized contract/stub seam (R22 proves the stubs compile + conform
    BEFORE any slice runs), so it NO LONGER requires the consumer to declare the
    producer as a ``**Dependencies:**`` edge — the keystone that lets the wave
    scheduler (which keys only on Dependencies) fan contract-bound slices out.
    Only a Consumed interface NO BL exposes (a real contract gap) still fails.

    Only fires for BLs that actually declare ``**Consumes:**`` — a BL may depend
    on another purely for ordering (e.g. a migration) without a code interface, so
    absence of Consumes is never an error. This catches the real defect: consuming
    an interface that no declared dependency produces (the cross-BL contract gap).
    """
    producers: dict[str, str] = {}      # normalized contract -> producing BL
    for it in items:
        bl_id, _ = _body_of(it)
        for tok in _contract_tokens(it, _EXPOSES_RE):
            producers.setdefault(tok, bl_id)
    bad: dict[str, str] = {}
    for it in items:
        bl_id, _ = _body_of(it)
        if not bl_id:
            continue
        consumes = _contract_tokens(it, _CONSUMES_RE)
        if not consumes:
            continue
        deps = set(declared_dependencies(it) or [])
        problems = []
        for tok in sorted(consumes):
            prod = producers.get(tok)
            if prod is None:
                problems.append(f"'{tok}' is exposed by no BL")
            elif not contract_first and prod != bl_id and prod not in deps:
                problems.append(f"'{tok}' is exposed by {prod}, which is not a declared dependency")
        if problems:
            bad[bl_id] = "consumes interface(s) without a contract link: " + "; ".join(problems)
    return bad


def extract_section(text: str, bl_id: str) -> str | None:
    """Return the heading + body of a single BL section for prompting the engineer."""
    headings = list(BL_HEADING_RE.finditer(text))
    for i, m in enumerate(headings):
        if m.group(1) == bl_id:
            body_end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
            return text[m.start():body_end].rstrip()
    return None
