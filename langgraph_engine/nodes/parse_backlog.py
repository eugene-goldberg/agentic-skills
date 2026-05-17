"""Parse `.agile-v/BACKLOG.md` produced by the PO into ordered BL items."""

from __future__ import annotations

import re
from pathlib import Path

from ..state import BacklogItem, GraphState


BL_HEADING_RE = re.compile(r"^##\s+(BL-\d{4}):\s*(.+?)\s*$", re.MULTILINE)
STATUS_RE = re.compile(r"\*\*Status:\*\*\s*(\w[\w -]*?)(?=\s*(?:·|\||$))", re.IGNORECASE | re.MULTILINE)
DEPS_RE = re.compile(r"\*\*Dependencies:\*\*\s*([^\n|·]+)", re.IGNORECASE)
REQ_RE = re.compile(r"\*\*REQ:\*\*\s*([^\n|·]+)", re.IGNORECASE)
BL_ID_RE = re.compile(r"BL-\d{4}")
REQ_ID_RE = re.compile(r"REQ-\d{4}")


def _split_blocks(text: str) -> list[tuple[str, str, str]]:
    """Return list of (bl_id, title, raw_block) in document order."""
    matches = list(BL_HEADING_RE.finditer(text))
    blocks = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        raw = text[start:end].rstrip() + "\n"
        blocks.append((m.group(1), m.group(2).strip(), raw))
    return blocks


def parse_backlog(state: GraphState) -> GraphState:
    backlog_path = Path(state["backlog_path"])
    if not backlog_path.exists():
        return {**state, "error": f"BACKLOG.md not found at {backlog_path}", "backlog_items": []}

    text = backlog_path.read_text(encoding="utf-8")
    items: list[BacklogItem] = []
    for bl_id, title, raw in _split_blocks(text):
        status_match = STATUS_RE.search(raw)
        deps_match = DEPS_RE.search(raw)
        req_match = REQ_RE.search(raw)
        status = status_match.group(1).strip() if status_match else "Backlog"
        # Extract BL-XXXX / REQ-XXXX patterns directly so the parser is robust to
        # any inline-list separator the PO chose (commas, ' · ', '|', etc.).
        deps_text = deps_match.group(1) if deps_match else "none"
        deps = BL_ID_RE.findall(deps_text)
        reqs_text = req_match.group(1) if req_match else ""
        reqs = REQ_ID_RE.findall(reqs_text)
        items.append({
            "bl_id": bl_id,
            "title": title,
            "raw": raw,
            "status": status,
            "dependencies": deps,
            "req_ids": reqs,
        })

    return {**state, "backlog_items": items, "current_index": -1}


def has_more(state: GraphState) -> str:
    """Conditional edge: are there ready BL items left to process?"""
    items = state.get("backlog_items", [])
    next_idx = state.get("current_index", -1) + 1
    # Skip to next Ready item whose deps are satisfied by already-completed cycles.
    completed_ids = {c["bl_id"] for c in state.get("completed_cycles", [])}
    while next_idx < len(items):
        item = items[next_idx]
        if item["status"].lower().startswith("ready") and all(d in completed_ids for d in item["dependencies"]):
            return "engineering"
        next_idx += 1
    return "finalize"


def advance_index(state: GraphState) -> GraphState:
    """Pick the index of the next eligible BL item."""
    items = state.get("backlog_items", [])
    next_idx = state.get("current_index", -1) + 1
    completed_ids = {c["bl_id"] for c in state.get("completed_cycles", [])}
    while next_idx < len(items):
        item = items[next_idx]
        if item["status"].lower().startswith("ready") and all(d in completed_ids for d in item["dependencies"]):
            return {**state, "current_index": next_idx}
        next_idx += 1
    return {**state, "current_index": next_idx}  # past end
