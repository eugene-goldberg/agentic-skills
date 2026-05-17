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
from pathlib import Path
from typing import AsyncIterator


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


async def stream_agent_task(
    task: str,
    repo_path: str | Path,
    *,
    timeout_seconds: int = 1800,
    allowed_tools: str = "Bash,Read,Write,Edit",
) -> AsyncIterator[dict]:
    """Run `claude --print --output-format stream-json` and yield parsed events.

    Each yielded dict has at minimum a `type` field. Final event is
    `{"type":"_meta","exit_code":N,"duration_s":...}`. Caller handles the SSE
    framing.
    """
    repo_path = Path(repo_path)
    if not (repo_path / ".git").exists() and not (repo_path / ".git").is_file():
        # Allow worktrees (where .git is a file pointing at the gitdir).
        yield {"type": "_error", "error": f"not a git repo: {repo_path}"}
        return

    prompt = build_prompt(task)
    cmd = [
        _claude_binary(),
        "--print",
        "--dangerously-skip-permissions",
        "--output-format", "stream-json",
        "--verbose",
        "--allowedTools", allowed_tools,
        "-p", prompt,
    ]

    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": os.environ.get("GIT_AUTHOR_NAME", "Claude Agent"),
        "GIT_AUTHOR_EMAIL": os.environ.get("GIT_AUTHOR_EMAIL", "agent@webapp.local"),
        "GIT_COMMITTER_NAME": os.environ.get("GIT_COMMITTER_NAME", "Claude Agent"),
        "GIT_COMMITTER_EMAIL": os.environ.get("GIT_COMMITTER_EMAIL", "agent@webapp.local"),
    }

    yield {"type": "_meta", "phase": "spawn", "cmd": cmd[:4] + ["..."]}

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
                    yield {"type": "_error", "error": f"agent timed out after {timeout_seconds}s"}
                    return
                if not raw:
                    break
                line = raw.decode(errors="replace").strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    yield {"type": "_raw", "text": line}
        finally:
            await proc.wait()
            stderr_task.cancel()
            duration = loop.time() - start
            yield {
                "type": "_meta",
                "phase": "exit",
                "exit_code": proc.returncode,
                "duration_s": round(duration, 2),
            }
    except Exception as exc:  # noqa: BLE001
        proc.kill()
        yield {"type": "_error", "error": f"{type(exc).__name__}: {exc}"}
