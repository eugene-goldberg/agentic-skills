"""A7 — disk-persisted orchestrator run state.

Sprint 3 twice lost queue position when the driver script crashed mid-run.
Recovery worked but only because skip_po + R11 no_op + B12 partial_resume let
us reconstruct from git history. With this module, the orchestrator also
checkpoints {run_id, brief_hash, current_bl, bl_outcomes[]} to disk at every
milestone, so the next /run-brief can detect an orphaned run and choose to
resume instead of starting fresh.

Persistence shape (one file per run):

  webapp/backend/.orchestrator-state/<run_id>.json   (active)
  webapp/backend/.orchestrator-state/done/<run_id>.json   (terminated)

Writes are atomic via tmp + fsync + rename so a crash mid-write can't leave
a corrupt active file.

This module is pure-function; the orchestrator + router both import it.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[2]
STATE_DIR = Path(os.environ.get("ORCH_STATE_DIR", BACKEND_DIR / ".orchestrator-state")).resolve()
DONE_DIR = STATE_DIR / "done"


def _ensure_dirs() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DONE_DIR.mkdir(parents=True, exist_ok=True)


def _state_path(run_id: str) -> Path:
    return STATE_DIR / f"{run_id}.json"


def _done_path(run_id: str) -> Path:
    return DONE_DIR / f"{run_id}.json"


def write_checkpoint(
    *,
    run_id: str,
    repo: str,
    brief_hash: str,
    started_at: datetime,
    current_bl: str | None,
    bl_outcomes: list[dict[str, Any]],
    status: str = "active",
) -> Path:
    """Atomically write the run's current state. Returns the file path.

    Atomic write: open tmp file, write+fsync, then rename → never leaves a
    half-written active file even on crash.
    """
    _ensure_dirs()
    payload = {
        "run_id": run_id,
        "repo": repo,
        "brief_hash": brief_hash,
        "started_at": started_at.isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "current_bl": current_bl,
        "bl_outcomes": list(bl_outcomes),
        "status": status,
    }
    dst = _state_path(run_id)
    tmp = dst.with_suffix(".json.tmp")
    with tmp.open("w") as f:
        json.dump(payload, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(dst)
    return dst


def mark_terminated(run_id: str, status: str) -> Path | None:
    """Move the active state file into done/ with the given terminal status.

    `status` should be one of: "sprint_complete", "aborted". Best-effort —
    returns None if the active file doesn't exist (already moved, or never
    written).
    """
    _ensure_dirs()
    src = _state_path(run_id)
    if not src.exists():
        return None
    try:
        data = json.loads(src.read_text())
    except (OSError, ValueError):
        data = {}
    data["status"] = status
    data["terminated_at"] = datetime.now(timezone.utc).isoformat()
    dst = _done_path(run_id)
    tmp = dst.with_suffix(".json.tmp")
    with tmp.open("w") as f:
        json.dump(data, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(dst)
    try:
        src.unlink()
    except OSError:
        pass
    return dst


def find_active(repo: str, brief_hash: str | None = None) -> dict | None:
    """Return the most-recently-updated active state for this repo (and
    optionally matching brief_hash), or None.

    "Active" means the file is in STATE_DIR (not done/). The orchestrator
    moves files into done/ on terminal events, so anything left in STATE_DIR
    is either currently running or orphaned by a process crash.
    """
    if not STATE_DIR.exists():
        return None
    best: dict | None = None
    best_updated = ""
    for child in STATE_DIR.iterdir():
        if child.is_dir() or child.suffix != ".json":
            continue
        try:
            data = json.loads(child.read_text())
        except (OSError, ValueError):
            continue
        if data.get("repo") != repo:
            continue
        if brief_hash is not None and data.get("brief_hash") != brief_hash:
            continue
        updated = data.get("updated_at") or data.get("started_at") or ""
        if updated > best_updated:
            best_updated = updated
            best = data
    return best
