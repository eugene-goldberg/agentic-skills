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


@dataclass
class BacklogItem:
    id: str
    title: str
    body: str            # full markdown section for this item, sans heading
    meta: dict[str, str]


def find_backlog(repo_path: Path) -> Path | None:
    candidate = repo_path / ".agile-v" / "BACKLOG.md"
    if candidate.is_file():
        return candidate
    # Fallback: search shallow.
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
