"""ABL-0014 calibration smoke driver — invokes _acceptance_flow directly.

Bypasses uvicorn entirely so the operator's running server is untouched.
Drives orchestrator._acceptance_flow against an existing feature with a
brief.md and a merged agent_branch, logging every event to a file the
operator can `tail -F`.

Usage:
    python tools/run_acceptance_smoke.py <repo> <feature_slug> [<run_id>]

Example:
    python tools/run_acceptance_smoke.py full-stack-fastapi-template time-tracking

Writes events to:
    webapp/backend/traces_archive/<run_id>/acceptance-smoke.events.jsonl
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "webapp" / "backend"))

from app.services import orchestrator as orch  # noqa: E402


async def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    repo = sys.argv[1]
    feature_slug = sys.argv[2]
    run_id = (
        sys.argv[3] if len(sys.argv) > 3
        else f"smoke-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )

    repos_root = ROOT / "webapp" / "backend" / "repos"
    repo_dir = (repos_root / repo).resolve()
    if not repo_dir.exists():
        print(f"repo not found: {repo_dir}", file=sys.stderr)
        return 1

    log_dir = ROOT / "webapp" / "backend" / "traces_archive" / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "acceptance-smoke.events.jsonl"

    print(f"[smoke] repo         = {repo}")
    print(f"[smoke] feature_slug = {feature_slug}")
    print(f"[smoke] run_id       = {run_id}")
    print(f"[smoke] repo_dir     = {repo_dir}")
    print(f"[smoke] log          = {log_path}")
    print(f"[smoke] starting at  = {datetime.now(timezone.utc).isoformat()}")
    print("---")

    started = time.time()
    counts: dict[str, int] = {}
    with open(log_path, "w", encoding="utf-8") as fh:
        async for event in orch._acceptance_flow(
            repo_dir=repo_dir,
            repo_name=repo,
            run_id=run_id,
            feature_slug=feature_slug,
            timeout=3600,
        ):
            rec = dict(event)
            rec.setdefault("_persisted_at", datetime.now(timezone.utc).isoformat())
            fh.write(json.dumps(rec, default=str) + "\n")
            fh.flush()
            ph = event.get("phase") or event.get("type") or "?"
            counts[ph] = counts.get(ph, 0) + 1
            # echo phase events; suppress raw assistant chatter
            if event.get("type") == "_meta" or "phase" in event:
                short = {k: v for k, v in event.items() if k not in ("type",)
                         and not isinstance(v, (list, dict)) or isinstance(v, list) and len(v) < 5}
                print(f"[{time.time() - started:6.1f}s] {ph}: {short}")

    dur = time.time() - started
    print("---")
    print(f"[smoke] done in {dur:.1f}s")
    print(f"[smoke] event counts: {dict(sorted(counts.items()))}")
    print(f"[smoke] log: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
