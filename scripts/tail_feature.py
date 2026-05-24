#!/usr/bin/env python3
"""tail_feature.py — follow a feature's events.jsonl in real time (A18).

Usage:
    python scripts/tail_feature.py <repo> <feature-slug>
    python scripts/tail_feature.py <repo> <feature-slug> --raw       # dump every JSON line verbatim
    python scripts/tail_feature.py <repo> <feature-slug> --replay    # show backfill before tailing

The framework / harness should be able to follow a feature's progress
regardless of how the sprint was kicked off (webapp UI or curl POST).
This script tails the per-feature events.jsonl that A18's /run-brief
writes to:

    <target>/_brownfield/features/<feature-slug>/events.jsonl

By default it renders a milestone summary; pass --raw to dump verbatim
JSON for piping into other tools.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

AGENTIC_ROOT = Path(__file__).resolve().parents[1]
REPOS_ROOT = AGENTIC_ROOT / "webapp" / "backend" / "repos"


def _resolve_events_path(repo: str, feature_slug: str) -> Path:
    """Resolve <target>/_brownfield/features/<slug>/events.jsonl.

    `repo` is the symlinked name under webapp/backend/repos/. The symlink
    target is the actual target repo on disk.
    """
    link = REPOS_ROOT / repo
    if not link.exists():
        raise SystemExit(f"error: webapp/backend/repos/{repo} does not exist")
    target_root = link.resolve()
    return target_root / "_brownfield" / "features" / feature_slug / "events.jsonl"


def _render(evt: dict) -> str:
    """One-line milestone-friendly rendering of an event."""
    phase = evt.get("phase", "")
    bl = evt.get("bl_id", "")
    bl_prefix = f"[{bl}] " if bl else ""
    ts = evt.get("_persisted_at") or evt.get("_ts") or ""
    if ts:
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%H:%M:%S")
        except (ValueError, AttributeError):
            ts = ts[11:19] if len(ts) > 11 else ts

    # Key events get their own renderers.
    if phase == "orchestrator.start":
        return f"{ts}  ▶ start  run_id={evt.get('run_id', '')}  brief={evt.get('brief_chars', 0)} chars"
    if phase == "orchestrator.index_initial.start":
        return f"{ts}  ⌗ indexing target …"
    if phase == "orchestrator.index_initial.done":
        return f"{ts}  ✓ indexing done"
    if phase == "orchestrator.po.start":
        return f"{ts}  📋 PO start"
    if phase == "orchestrator.po.done":
        return f"{ts}  ✓ PO done   doctrine_ok={evt.get('doctrine_ok')}"
    if phase == "orchestrator.brief_persisted":
        return f"{ts}  💾 brief persisted  path={evt.get('path')}  bytes={evt.get('bytes')}"
    if phase == "orchestrator.backlog_parsed":
        bls = evt.get("bls") or []
        return f"{ts}  📑 backlog parsed  count={evt.get('count')}  {[b.get('id') for b in bls]}"
    if phase == "orchestrator.bl.start":
        return f"{ts}  ┌─ BL.start  {bl}  {evt.get('title', '')}"
    if phase == "orchestrator.engineer.start":
        return f"{bl_prefix}{ts}  🔧 engineer start"
    if phase == "orchestrator.engineer.done":
        return f"{bl_prefix}{ts}  ✓ engineer done  merged={evt.get('merged')}  no_op={evt.get('no_op')}"
    if phase == "orchestrator.qa.start":
        return f"{bl_prefix}{ts}  🧪 qa start"
    if phase == "orchestrator.qa.done":
        return f"{bl_prefix}{ts}  ✓ qa done  merged={evt.get('merged')}"
    if phase == "orchestrator.scorer.start":
        return f"{bl_prefix}{ts}  ⚖ scorer start"
    if phase == "orchestrator.scorer.done":
        return f"{bl_prefix}{ts}  ✓ scorer done  doctrine_ok={evt.get('doctrine_ok')}"
    if phase == "orchestrator.bl.done":
        return f"{ts}  └─ BL.done   {bl}  outcome={evt.get('outcome')}"
    if phase == "doctrine_check":
        return f"{bl_prefix}{ts}  · doctrine_check {evt.get('kind')}  attempts={evt.get('attempts', evt.get('attempt'))}"
    if phase == "regression_gate":
        return f"{bl_prefix}{ts}  · regression_gate {evt.get('kind')}  ok={evt.get('ok')}"
    if phase == "forbidden_git_op":
        return f"{bl_prefix}{ts}  🚫 R13 forbidden_git_op killed  command={evt.get('command', '')[:80]}"
    if phase == "orchestrator.sprint_complete":
        return f"{ts}  🏁 sprint_complete"
    if phase == "orchestrator.aborted":
        return f"{ts}  ✗ aborted  reason={evt.get('reason')}"
    if phase == "orchestrator.closure_check.start":
        return f"{ts}  🔒 closure_check start"
    if phase == "orchestrator.closure_violation":
        return f"{ts}  ⚠ closure_violation  kind={evt.get('kind')}  resource={evt.get('resource')}"
    if phase == "orchestrator.closure_check.done":
        return f"{ts}  ✓ closure_check done  violation_count={evt.get('violation_count')}"
    if phase == "orchestrator.doctrine_meta.proposals":
        return f"{ts}  📝 doctrine_meta {evt.get('proposals_count')} proposals"

    # Default — only show non-noisy events.
    if phase and phase.startswith("orchestrator."):
        return f"{ts}  · {phase}"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("repo", help="repo name under webapp/backend/repos/")
    ap.add_argument("feature_slug", help="feature slug; matches _brownfield/features/<slug>/")
    ap.add_argument("--raw", action="store_true", help="dump verbatim JSON instead of milestone summary")
    ap.add_argument("--replay", action="store_true", help="show existing content before tailing")
    ap.add_argument("--once", action="store_true", help="print existing content and exit (no tail)")
    args = ap.parse_args()

    events = _resolve_events_path(args.repo, args.feature_slug)
    if not events.exists():
        print(f"waiting for {events} to be created …", file=sys.stderr)
        while not events.exists():
            time.sleep(1.0)
        print(f"found {events}", file=sys.stderr)

    pos = 0
    if args.replay or args.once:
        with events.open("r", encoding="utf-8") as fh:
            for line in fh:
                _emit(line, raw=args.raw)
            pos = fh.tell()
    else:
        pos = events.stat().st_size

    if args.once:
        return 0

    print(f"— tailing {events} —", file=sys.stderr)
    while True:
        try:
            with events.open("r", encoding="utf-8") as fh:
                fh.seek(pos)
                chunk = fh.read()
                if chunk:
                    for line in chunk.splitlines(keepends=True):
                        _emit(line, raw=args.raw)
                    pos = fh.tell()
            time.sleep(0.5)
        except FileNotFoundError:
            time.sleep(1.0)
        except KeyboardInterrupt:
            return 0


def _emit(line: str, *, raw: bool) -> None:
    line = line.strip()
    if not line:
        return
    if raw:
        print(line)
        return
    try:
        evt = json.loads(line)
    except json.JSONDecodeError:
        return
    rendered = _render(evt)
    if rendered:
        print(rendered)


if __name__ == "__main__":
    sys.exit(main())
