#!/usr/bin/env python3
"""Driver script for POST /api/projects/<repo>/run-brief.

Reads brief from $ORCH_BRIEF (default /tmp/sprint_brief.md), streams SSE
events from the orchestrator, and tees a milestone-friendly one-line
summary to stdout AND to a timestamped run.log under
webapp/backend/logs/orchestrator/<ts>/.

Override the log location via $ORCH_LOG_DIR. A symlink at
webapp/backend/logs/orchestrator/.latest is rewritten on each launch so
operators can `tail -f .latest/run.log`.
"""
import os
import json
import time
import urllib.request
from pathlib import Path

REPO = os.environ.get("ORCH_REPO", "full-stack-fastapi-template")
PROJECT_NAME = os.environ.get("ORCH_PROJECT_NAME", "notifications-activity-system")
BRIEF_PATH = Path(os.environ.get("ORCH_BRIEF", "/tmp/sprint_brief.md"))
ENDPOINT = os.environ.get(
    "ORCH_ENDPOINT",
    f"http://127.0.0.1:8000/api/projects/{REPO}/run-brief",
)
SKIP_PO = os.environ.get("ORCH_SKIP_PO", "true").lower() in ("1", "true", "yes")
STOP_ON_FAILURE = os.environ.get("ORCH_STOP_ON_FAILURE", "true").lower() in ("1", "true", "yes")
TIMEOUT_PER_ROLE = int(os.environ.get("ORCH_TIMEOUT_PER_ROLE", "2400"))

if "ORCH_LOG_DIR" in os.environ:
    LOG_DIR = Path(os.environ["ORCH_LOG_DIR"])
else:
    LOG_BASE = Path(__file__).resolve().parents[1] / "logs" / "orchestrator"
    LOG_DIR = LOG_BASE / time.strftime("%Y%m%d-%H%M%S")
LOG_DIR.mkdir(parents=True, exist_ok=True)
RUN_LOG = LOG_DIR / "run.log"

latest = LOG_DIR.parent / ".latest"
try:
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(LOG_DIR.name)
except OSError:
    pass

log_fp = RUN_LOG.open("a", buffering=1)


def emit(line: str) -> None:
    print(line, flush=True)
    log_fp.write(line + "\n")


emit(f"[{time.strftime('%H:%M:%S')}] LOG_DIR={LOG_DIR}")
brief = BRIEF_PATH.read_text()
body = json.dumps({
    "brief": brief,
    "project_name": PROJECT_NAME,
    "skip_po": SKIP_PO,
    "stop_on_failure": STOP_ON_FAILURE,
    "timeout_per_role": TIMEOUT_PER_ROLE,
}).encode()
req = urllib.request.Request(
    ENDPOINT,
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)
emit(
    f"[{time.strftime('%H:%M:%S')}] POST {ENDPOINT} skip_po={SKIP_PO} "
    f"brief={len(brief)} chars"
)

with urllib.request.urlopen(req, timeout=None) as resp:
    for raw in resp:
        line = raw.decode("utf-8", errors="replace").rstrip()
        if not line.startswith("data:"):
            continue
        try:
            evt = json.loads(line[5:].strip())
        except Exception:
            continue
        phase = evt.get("phase") or evt.get("type") or "?"
        bl = evt.get("bl_id") or ""
        extra = ""
        try:
            if phase == "orchestrator.backlog_parsed":
                extra = f"count={evt.get('count')}"
            elif phase == "regression_gate":
                extra = f"kind={evt.get('kind')} ok={evt.get('ok')}"
            elif phase == "merge_to_target":
                sha = evt.get("merged_sha") or ""
                base = f"ok={evt.get('ok')} sha={sha[:8] if sha else 'none'}"
                if not evt.get("ok"):
                    base += (
                        f" kind={evt.get('kind')!r} branch={evt.get('branch')} "
                        f"error={evt.get('error')!r}"
                    )
                extra = base
            elif phase == "doctrine_check":
                extra = f"{evt.get('kind')} attempts={evt.get('attempts') or evt.get('attempt')}"
            elif phase.startswith("orchestrator.") and phase.endswith(".done"):
                extra = json.dumps(
                    {k: v for k, v in evt.items() if k not in ("type", "phase", "orchestrator_step")}
                )[:200]
        except Exception as exc:
            extra = f"<formatter error: {exc}>"
        if phase in ("assistant", "user", "system", "tool_use", "tool_result"):
            continue
        emit(f"[{time.strftime('%H:%M:%S')}] {phase:48} {bl:9} {extra}")

        # A6: on any failure-shaped event, dump the full event JSON so no
        # diagnostic data is lost to formatter omissions.
        ok = evt.get("ok")
        is_failure_phase = (
            phase == "orchestrator.aborted"
            or phase.endswith("_error")
            or (phase in ("merge_to_target", "regression_gate") and ok is False)
        )
        if is_failure_phase:
            try:
                emit(f"[{time.strftime('%H:%M:%S')}] FULL_EVENT {json.dumps(evt)[:1500]}")
            except Exception as exc:
                emit(f"[{time.strftime('%H:%M:%S')}] FULL_EVENT <dump error: {exc}>")
