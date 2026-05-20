"""Subprocess-based Claude Code Agent invocation with SSE streaming.

Implements Option A from the integration design:
- shells out to the `claude` binary in --print mode
- requests --output-format stream-json (newline-delimited JSON)
- streams parsed messages back to the caller as an async iterator
- prompt enforces a final `git commit` + JSON summary on the agent

Caller wraps each yielded event into an SSE frame.

## Auth

The subprocess inherits the parent process environment (HOME, USER, PATH, all
claude-related vars) via `env={**os.environ, ...}` below. That means whichever
way you already authenticate `claude` from a terminal works here unchanged:

- `claude /login` (OAuth, incl. company SSO): credentials live in `~/.claude/`
  and are picked up automatically — NO `ANTHROPIC_API_KEY` required.
- `ANTHROPIC_API_KEY` env var: exported in the shell that launches uvicorn.
- `CLAUDE_CODE_USE_BEDROCK=1` / `CLAUDE_CODE_USE_VERTEX=1`: with the relevant
  cloud provider env vars set, claude routes through your corporate proxy.

If `claude` works in your terminal, it works here.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import AsyncIterator

BACKEND_DIR = Path(__file__).resolve().parents[2]  # webapp/backend/
RETRIEVAL_SERVER_MODULE = "mcp_servers.retrieval_server"
RETRIEVAL_MCP_TOOLS = [
    "mcp__retrieval__target_status",
    "mcp__retrieval__semantic_search",
    "mcp__retrieval__graph_neighbors",
    "mcp__retrieval__graph_find_similar",
    "mcp__retrieval__graph_summary",
]


def build_prompt(task: str) -> str:
    """Wrap the user task with non-negotiable completion + commit protocol."""
    return f"""You are an autonomous software agent operating on a git repository.

## Task
{task}

## Execution Protocol
- Work incrementally. Read files before editing them.
- Use bash to run tests after making changes if a test suite exists.
- Do not ask clarifying questions. Make reasonable decisions and document them.

## Required Completion Steps
After the task is complete, you MUST:
1. Run `git status` to review all changes.
2. Run `git diff --stat` to confirm scope.
3. Run `git add -A` (or stage selectively).
4. Commit with a structured message of the form:
   `<type>(<scope>): <short description>` plus a body explaining what changed and why,
   ending with `Agent-Task: <one-line summary>`.
5. Run `git log --oneline -1` to confirm the commit.
6. Print ONLY this JSON as your final assistant output, no extra prose:
   {{"status":"complete","commit_sha":"<full sha>","files_changed":<n>,"summary":"<brief>"}}
"""


def _claude_binary() -> str:
    """Resolve the claude CLI binary, allowing override via $CLAUDE_BIN."""
    return os.environ.get("CLAUDE_BIN") or shutil.which("claude") or "claude"


def _build_retrieval_mcp_config(
    reference_repo: Path | None,
    target_repo: Path | None,
    log_path: Path | None,
) -> tuple[Path, list[str]] | None:
    """Materialize an MCP config file pointing at the local retrieval server.

    Returns (config_path, mcp_tool_names) or None if no sources were provided.
    Caller is responsible for deleting the temp file when the agent finishes.
    """
    if not reference_repo and not target_repo:
        return None
    python_bin = os.environ.get("RETRIEVAL_PYTHON") or sys.executable
    server_env: dict[str, str] = {
        # Make `import mcp_servers.retrieval_server` resolvable regardless of
        # the spawned subprocess's cwd (some MCP hosts don't honor the cwd
        # field, which leaves `python -m mcp_servers...` unable to find the
        # module). PYTHONPATH wins over cwd-based discovery and is independent
        # of where the host process was launched from.
        "PYTHONPATH": str(BACKEND_DIR),
    }
    if reference_repo:
        server_env["RETRIEVAL_REFERENCE_REPO"] = str(Path(reference_repo).resolve())
    if target_repo:
        server_env["RETRIEVAL_TARGET_REPO"] = str(Path(target_repo).resolve())
    if log_path:
        server_env["RETRIEVAL_LOG_PATH"] = str(Path(log_path).resolve())
    # Inherit retrieval-relevant env (Azure / Milvus / budget).
    for k in (
        "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_VERSION",
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "EMBEDDING_PROVIDER", "EMBEDDING_MODEL",
        "EMBEDDING_DIMENSION", "OPENAI_API_KEY", "MILVUS_ADDRESS", "MILVUS_TOKEN",
        "RETRIEVAL_TOOL_BUDGET", "PATH", "HOME",
    ):
        if k in os.environ:
            server_env.setdefault(k, os.environ[k])
    config = {
        "mcpServers": {
            "retrieval": {
                "command": python_bin,
                "args": ["-m", RETRIEVAL_SERVER_MODULE],
                "cwd": str(BACKEND_DIR),
                "env": server_env,
            }
        }
    }
    fd, path = tempfile.mkstemp(prefix="retrieval-mcp-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(config, f)
    return Path(path), list(RETRIEVAL_MCP_TOOLS)


async def stream_agent_task(
    task: str,
    repo_path: str | Path,
    *,
    timeout_seconds: int = 1800,
    allowed_tools: str = "Bash,Read,Write,Edit",
    reference_repo: str | Path | None = None,
    target_repo: str | Path | None = None,
    retrieval_log_path: str | Path | None = None,
    trace=None,  # app.services.traces.TraceWriter | None
) -> AsyncIterator[dict]:
    """Run `claude --print --output-format stream-json` and yield parsed events.

    Each yielded dict has at minimum a `type` field. Final event is
    `{"type":"_meta","exit_code":N,"duration_s":...}`. Caller handles the SSE
    framing.
    """
    repo_path = Path(repo_path)
    if not (repo_path / ".git").exists() and not (repo_path / ".git").is_file():
        # Allow worktrees (where .git is a file pointing at the gitdir).
        evt = {"type": "_error", "error": f"not a git repo: {repo_path}"}
        if trace is not None:
            trace.write_event(evt)
        yield evt
        return

    prompt = build_prompt(task)

    mcp_config_path: Path | None = None
    effective_allowed = allowed_tools
    extra_cli: list[str] = []
    retrieval = _build_retrieval_mcp_config(
        Path(reference_repo) if reference_repo else None,
        Path(target_repo) if target_repo else Path(repo_path),
        Path(retrieval_log_path) if retrieval_log_path else None,
    )
    if retrieval is not None:
        mcp_config_path, mcp_tools = retrieval
        extra_cli += ["--mcp-config", str(mcp_config_path)]
        effective_allowed = ",".join([allowed_tools, *mcp_tools])

    cmd = [
        _claude_binary(),
        "--print",
        "--dangerously-skip-permissions",
        "--output-format", "stream-json",
        "--verbose",
        "--allowedTools", effective_allowed,
        *extra_cli,
        "-p", prompt,
    ]

    if trace is not None:
        trace.set_prompt(prompt)
        trace.set_cmd(cmd)

    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": os.environ.get("GIT_AUTHOR_NAME", "Claude Agent"),
        "GIT_AUTHOR_EMAIL": os.environ.get("GIT_AUTHOR_EMAIL", "agent@webapp.local"),
        "GIT_COMMITTER_NAME": os.environ.get("GIT_COMMITTER_NAME", "Claude Agent"),
        "GIT_COMMITTER_EMAIL": os.environ.get("GIT_COMMITTER_EMAIL", "agent@webapp.local"),
    }

    spawn_evt = {"type": "_meta", "phase": "spawn", "cmd": cmd[:4] + ["..."]}
    if trace is not None:
        trace.write_event(spawn_evt)
    yield spawn_evt

    loop = asyncio.get_event_loop()
    start = loop.time()

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(repo_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    async def _drain_stderr() -> None:
        # Surface stderr lines so the UI can show install or auth errors.
        assert proc.stderr is not None
        async for raw in proc.stderr:
            txt = raw.decode(errors="replace").rstrip()
            if txt:
                # We can't yield from a separate task into our outer generator
                # without a queue; log to stderr of the parent process instead.
                # The outer loop is what the UI consumes; stderr ends up in
                # uvicorn's log for debugging.
                print(f"[claude stderr] {txt}")

    stderr_task = asyncio.create_task(_drain_stderr())

    try:
        assert proc.stdout is not None
        try:
            while True:
                # readline with timeout so a hung claude process doesn't hang us.
                try:
                    raw = await asyncio.wait_for(
                        proc.stdout.readline(),
                        timeout=timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    proc.kill()
                    evt = {"type": "_error", "error": f"agent timed out after {timeout_seconds}s"}
                    if trace is not None:
                        trace.write_event(evt)
                    yield evt
                    return
                if not raw:
                    break
                line = raw.decode(errors="replace").strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    evt = {"type": "_raw", "text": line}
                if trace is not None:
                    trace.write_event(evt)
                yield evt
        finally:
            await proc.wait()
            stderr_task.cancel()
            duration = loop.time() - start
            exit_evt = {
                "type": "_meta",
                "phase": "exit",
                "exit_code": proc.returncode,
                "duration_s": round(duration, 2),
            }
            if trace is not None:
                trace.write_event(exit_evt)
            yield exit_evt
    except Exception as exc:  # noqa: BLE001
        proc.kill()
        err_evt = {"type": "_error", "error": f"{type(exc).__name__}: {exc}"}
        if trace is not None:
            trace.write_event(err_evt)
        yield err_evt
    finally:
        if mcp_config_path is not None:
            try:
                mcp_config_path.unlink()
            except OSError:
                pass
