"""Tool wrappers exposed to LLM-driven role nodes.

Mirrors what the Claude Code Agent tool gives us: read_file, write_file,
edit_file, list_dir, bash. Every call is restricted to paths under the
configured workspace_root so an agent can't escape the project tree. Bash runs
unrestricted shell within that root.

Each tool returns a dict the LangChain tool-call protocol can serialize. Errors
are returned as a string in `error`, not raised, so the model sees the failure
and can retry or escalate.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Any

from langchain_core.tools import tool


# Output caps to keep tool messages from blowing up the model's context window.
# Tuned for providers with tighter request-size limits (e.g., HF Novita).
READ_FILE_MAX_BYTES = 8_000
BASH_STDOUT_MAX_BYTES = 4_000
BASH_STDERR_MAX_BYTES = 2_000
LIST_DIR_MAX_ENTRIES = 200


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    """Truncate text to `limit` bytes; return (text, was_truncated)."""
    if text is None:
        return "", False
    data = text.encode("utf-8", errors="replace")
    if len(data) <= limit:
        return text, False
    head = data[: limit - 200] if limit > 200 else data[:limit]
    tail = data[-100:] if limit > 200 else b""
    marker = f"\n... [truncated {len(data) - limit} bytes] ...\n".encode("utf-8")
    out = head + marker + tail
    return out.decode("utf-8", errors="replace"), True


def _resolve_inside(workspace: Path, path: str) -> Path:
    """Resolve `path` against the workspace; reject paths that escape it."""
    p = Path(path)
    if not p.is_absolute():
        p = workspace / p
    p = p.resolve()
    workspace = workspace.resolve()
    try:
        p.relative_to(workspace)
    except ValueError as exc:
        raise PermissionError(
            f"Path {p} is outside workspace {workspace}"
        ) from exc
    return p


def make_tools(workspace: Path, *, bash_timeout: int = 600) -> list:
    """Build the bound tool set for a given workspace root."""

    @tool
    def read_file(path: str, offset: int = 0, limit: int | None = None) -> dict:
        """Read a file from the workspace.

        Args:
            path: Workspace-relative or absolute path under the workspace.
            offset: Optional starting line (0-indexed).
            limit: Optional max number of lines to return.
        """
        try:
            p = _resolve_inside(workspace, path)
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 - surface to model
            return {"ok": False, "error": str(exc)}
        all_lines = text.splitlines(keepends=True)
        total_lines = len(text.splitlines())
        if offset or limit is not None:
            end = None if limit is None else offset + limit
            lines = all_lines[offset:end]
        else:
            lines = all_lines
        content, truncated = _truncate("".join(lines), READ_FILE_MAX_BYTES)
        result = {"ok": True, "content": content, "total_lines": total_lines}
        if truncated:
            result["truncated"] = True
            result["hint"] = "Output truncated. Use offset/limit args to read specific line ranges."
        return result

    @tool
    def write_file(path: str, content: str) -> dict:
        """Write a file in the workspace, overwriting if it exists.

        Args:
            path: Workspace-relative or absolute path under the workspace.
            content: Full file contents to write.
        """
        try:
            p = _resolve_inside(workspace, path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
            return {"ok": True, "path": str(p), "bytes": len(content), "sha256": sha}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    @tool
    def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> dict:
        """Find-and-replace inside an existing file. `old_string` must be unique unless replace_all.

        Args:
            path: Workspace-relative or absolute path under the workspace.
            old_string: Exact text to find.
            new_string: Text to replace it with.
            replace_all: If true, replace every occurrence; else require unique match.
        """
        try:
            p = _resolve_inside(workspace, path)
            text = p.read_text(encoding="utf-8")
            count = text.count(old_string)
            if count == 0:
                return {"ok": False, "error": "old_string not found"}
            if count > 1 and not replace_all:
                return {"ok": False, "error": f"old_string not unique ({count} matches); pass replace_all=true to replace all"}
            new_text = text.replace(old_string, new_string) if replace_all else text.replace(old_string, new_string, 1)
            p.write_text(new_text, encoding="utf-8")
            return {"ok": True, "replacements": count if replace_all else 1}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    @tool
    def list_dir(path: str = ".") -> dict:
        """List directory entries under the workspace.

        Args:
            path: Workspace-relative or absolute path under the workspace.
        """
        try:
            p = _resolve_inside(workspace, path)
            if not p.exists():
                return {"ok": False, "error": "path does not exist"}
            if not p.is_dir():
                return {"ok": False, "error": "path is not a directory"}
            all_children = sorted(p.iterdir())
            entries = []
            for child in all_children[:LIST_DIR_MAX_ENTRIES]:
                entries.append({
                    "name": child.name,
                    "is_dir": child.is_dir(),
                    "size": child.stat().st_size if child.is_file() else None,
                })
            result = {"ok": True, "entries": entries, "total": len(all_children)}
            if len(all_children) > LIST_DIR_MAX_ENTRIES:
                result["truncated"] = True
            return result
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    @tool
    def bash(command: str, cwd: str | None = None, timeout: int | None = None) -> dict:
        """Run a shell command inside the workspace.

        Args:
            command: Full shell command line.
            cwd: Optional working directory (must be under workspace). Defaults to workspace root.
            timeout: Optional timeout in seconds; capped at bash_timeout.
        """
        try:
            run_cwd = _resolve_inside(workspace, cwd) if cwd else workspace
            actual_timeout = min(timeout, bash_timeout) if timeout else bash_timeout
            proc = subprocess.run(
                command,
                shell=True,
                cwd=run_cwd,
                capture_output=True,
                text=True,
                timeout=actual_timeout,
            )
            stdout, stdout_trunc = _truncate(proc.stdout, BASH_STDOUT_MAX_BYTES)
            stderr, stderr_trunc = _truncate(proc.stderr, BASH_STDERR_MAX_BYTES)
            result = {
                "ok": True,
                "exit_code": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
            }
            if stdout_trunc or stderr_trunc:
                result["truncated"] = True
            return result
        except subprocess.TimeoutExpired as exc:
            stdout, _ = _truncate((exc.stdout or "") if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", "replace"), BASH_STDOUT_MAX_BYTES)
            stderr, _ = _truncate((exc.stderr or "") if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", "replace"), BASH_STDERR_MAX_BYTES)
            return {
                "ok": False,
                "error": f"timeout after {actual_timeout}s",
                "stdout": stdout,
                "stderr": stderr,
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    @tool
    def copy_path(source: str, destination: str) -> dict:
        """Copy a file or directory tree inside the workspace.

        Args:
            source: Workspace-relative or absolute source path.
            destination: Workspace-relative or absolute destination path.
        """
        try:
            src = _resolve_inside(workspace, source)
            dst = _resolve_inside(workspace, destination)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
            return {"ok": True, "source": str(src), "destination": str(dst)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    @tool
    def sha256_file(path: str) -> dict:
        """Compute SHA-256 of a file in the workspace.

        Args:
            path: Workspace-relative or absolute file path.
        """
        try:
            p = _resolve_inside(workspace, path)
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            return {"ok": True, "sha256": digest, "bytes": p.stat().st_size}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    return [read_file, write_file, edit_file, list_dir, bash, copy_path, sha256_file]
