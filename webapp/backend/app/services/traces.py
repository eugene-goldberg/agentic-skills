"""Persistent agent-run tracing.

Every agent invocation gets its own directory under
`webapp/backend/traces/<repo>/<YYYYMMDDTHHMMSSZ>-<role>[-<bl_id>]-<task_id>/`
containing:

  meta.json        - role, repo, bl_id, branch, task_id, prompt, cmd, started_at,
                     finished_at, exit_code, duration_s, final_result_frame,
                     done_payload (commit sha, files changed, summary).
  stream.jsonl     - every frame yielded by the `claude` subprocess, plus
                     orchestration _meta events emitted by the router.
  retrieval.jsonl  - per-call retrieval-tool audit log written by the MCP
                     server (mirrors the langgraph treatment-arm format).

These directories are written outside the worktree so they survive cleanup.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[2]
TRACES_ROOT = Path(os.environ.get("AGENT_TRACES_ROOT", BACKEND_DIR / "traces")).resolve()
HARNESS_REPO_ROOT = BACKEND_DIR.parents[1]  # agentic-skills checkout root


def _harness_sha() -> str:
    """Capture the agentic-skills repo SHA once per process. B14 forensic field."""
    try:
        out = subprocess.run(
            ["git", "-C", str(HARNESS_REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=1.0, check=False,
        )
        sha = (out.stdout or "").strip()
        return sha or "unknown"
    except (subprocess.SubprocessError, OSError):
        return "unknown"


_HARNESS_SHA: str = _harness_sha()


_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(s: str) -> str:
    return _SAFE.sub("-", s).strip("-") or "x"


class TraceWriter:
    """One trace dir per agent run. Cheap, append-only, JSONL-based."""

    def __init__(
        self,
        *,
        repo: str,
        role: str,
        bl_id: str | None = None,
        task_id: str | None = None,
    ):
        self.repo = repo
        self.role = role
        self.bl_id = bl_id
        self.task_id = task_id or uuid.uuid4().hex[:8]
        self.started_at = datetime.now(timezone.utc)
        ts = self.started_at.strftime("%Y%m%dT%H%M%SZ")
        bl_part = f"-{_slug(bl_id)}" if bl_id else ""
        self.dir = TRACES_ROOT / _slug(repo) / f"{ts}-{_slug(role)}{bl_part}-{self.task_id}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.stream_path = self.dir / "stream.jsonl"
        self.meta_path = self.dir / "meta.json"
        self.retrieval_path = self.dir / "retrieval.jsonl"
        self._stream_fh = self.stream_path.open("a", buffering=1)
        self._meta: dict[str, Any] = {
            "repo": repo,
            "role": role,
            "bl_id": bl_id,
            "task_id": self.task_id,
            "started_at": self.started_at.isoformat(),
            "trace_dir": str(self.dir),
            "harness_sha": _HARNESS_SHA,
        }
        self._final_result: dict | None = None
        self._done: dict | None = None
        self._n_events = 0
        self._n_tool_use = 0
        self._n_tool_result = 0
        self._write_meta()

    # ------------------------------------------------------------------
    def set_prompt(self, prompt: str) -> None:
        self._meta["prompt"] = prompt
        self._write_meta()

    def set_cmd(self, cmd: list[str]) -> None:
        self._meta["cmd"] = list(cmd)
        self._write_meta()

    def write_event(self, event: dict) -> None:
        self._n_events += 1
        t = event.get("type")
        if t == "tool_use" or (t == "assistant" and self._is_tool_call(event)):
            self._n_tool_use += 1
        if t == "tool_result":
            self._n_tool_result += 1
        if t == "result":
            self._final_result = event
        if t == "done":
            self._done = event
        rec = {"_ts": datetime.now(timezone.utc).isoformat(), **event}
        try:
            self._stream_fh.write(json.dumps(rec, default=str) + "\n")
        except (ValueError, TypeError):
            # Defensive: if some payload isn't JSON-serializable, store its repr.
            self._stream_fh.write(json.dumps({"_ts": rec["_ts"], "type": "_unencodable", "repr": repr(event)}) + "\n")

    @staticmethod
    def _is_tool_call(event: dict) -> bool:
        msg = event.get("message") or {}
        for blk in (msg.get("content") or []):
            if isinstance(blk, dict) and blk.get("type") == "tool_use":
                return True
        return False

    # ------------------------------------------------------------------
    def close(self) -> None:
        try:
            self._stream_fh.close()
        except Exception:  # noqa: BLE001
            pass
        finished = datetime.now(timezone.utc)
        self._meta["finished_at"] = finished.isoformat()
        self._meta["duration_s"] = round((finished - self.started_at).total_seconds(), 3)
        self._meta["n_events"] = self._n_events
        self._meta["n_tool_use"] = self._n_tool_use
        self._meta["n_tool_result"] = self._n_tool_result
        if self._final_result is not None:
            self._meta["final_result_frame"] = self._final_result
        if self._done is not None:
            self._meta["done"] = self._done
        # Count retrieval calls if the MCP server wrote any.
        if self.retrieval_path.exists():
            try:
                self._meta["n_retrieval_calls"] = sum(1 for _ in self.retrieval_path.open())
            except OSError:
                pass
        self._write_meta()

    def _write_meta(self) -> None:
        tmp = self.meta_path.with_suffix(".json.tmp")
        with tmp.open("w") as f:
            json.dump(self._meta, f, indent=2, default=str)
        tmp.replace(self.meta_path)


def list_traces(repo: str | None = None, limit: int = 100) -> list[dict]:
    """Return recent trace summaries (newest first)."""
    if not TRACES_ROOT.exists():
        return []
    repos = [TRACES_ROOT / _slug(repo)] if repo else [p for p in TRACES_ROOT.iterdir() if p.is_dir()]
    rows: list[dict] = []
    for r in repos:
        if not r.exists():
            continue
        for d in r.iterdir():
            meta = d / "meta.json"
            if not meta.exists():
                continue
            try:
                rec = json.loads(meta.read_text())
                rec["_dir"] = str(d)
                rows.append(rec)
            except (OSError, json.JSONDecodeError):
                continue
    rows.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return rows[:limit]
