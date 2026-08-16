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
import signal
import sys
import tempfile
from pathlib import Path
from typing import AsyncIterator


# A44: asyncio's default StreamReader line buffer is 64 KiB (_DEFAULT_LIMIT =
# 2**16). The `claude` CLI emits `--output-format stream-json` as ONE
# newline-delimited JSON event per line, and a single line legitimately carries
# large payloads — a `Read` tool_result echoes the file content TWICE (the
# cat -n render in message.content[].tool_result AND the raw file in a top-level
# tool_use_result.file field), giving ~2.3x inflation, so a ~29 KB source file
# already produces a >64 KiB line. At the default limit, `proc.stdout.readline()`
# raises asyncio.LimitOverrunError ("Separator is found, but chunk is longer than
# limit"), which the broad `except` below converts into a pgroup SIGTERM (exit
# 143) — killing the agent mid-read before it can write any code. This is exactly
# what aborted the intelligent_kanban sprint at BL-0004 (boards.py had grown to
# 32 KB → ~73 KB line). Raise the ceiling far above any realistic stream-json
# line (large diffs, multi-file tool_results) so readline never trips it.
STREAM_READER_LIMIT = 64 * 1024 * 1024  # 64 MiB


async def _kill_pgroup(proc: asyncio.subprocess.Process, grace_seconds: float = 10.0) -> None:
    """B1: terminate the subprocess AND its descendants via the process group.

    `proc.kill()` only signals the immediate child, leaking any MCP servers
    or shell helpers it spawned. We spawn claude with `preexec_fn=os.setsid`
    so the whole tree shares a process group; this helper signals that pgroup.
    Best-effort — never raises.
    """
    if proc.returncode is not None:
        return
    try:
        pgid = os.getpgid(proc.pid)
    except (ProcessLookupError, PermissionError, OSError):
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=grace_seconds)
        return
    except asyncio.TimeoutError:
        pass
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        pass

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


# ─── Batch 7-3 (A52): agent env allowlist ────────────────────────────────────
#
# Before this the agent subprocess inherited the ENTIRE server environment
# ({**os.environ}) under --dangerously-skip-permissions — every retrieval
# secret (AZURE_OPENAI_API_KEY, OPENAI_API_KEY, MILVUS_TOKEN, ...) was
# visible to an agent whose inputs include UNTRUSTED target-repo content.
# The agent needs none of them: retrieval secrets flow to the MCP *server*
# via its own config env (see _build_retrieval_mcp_config). What the agent
# process legitimately needs: shell basics, git identity, claude auth
# (~/.claude via HOME, or ANTHROPIC_/AWS_/GOOGLE_ vars for API/Bedrock/
# Vertex routing), and proxy settings.
#
# Escape hatches (operator-controlled):
# - AGENT_ENV_ALLOWLIST="VAR1,VAR2"  — extend with specific extra vars
# - AGENT_ENV_PASSTHROUGH_ALL=1      — restore full inheritance (emergency
#   rollback without a redeploy; logged via the spawn event)

_ENV_EXACT = {
    "HOME", "PATH", "USER", "LOGNAME", "SHELL", "TMPDIR", "TERM", "LANG",
    "TZ", "COLUMNS", "NODE_OPTIONS",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "no_proxy",
}
_ENV_PREFIXES = (
    "CLAUDE_", "ANTHROPIC_", "AWS_", "GOOGLE_", "VERTEX_", "GIT_",
    "LC_", "XDG_", "SSL_",
)


def _agent_env() -> dict[str, str]:
    """Build the agent subprocess environment (A52 allowlist)."""
    if os.environ.get("AGENT_ENV_PASSTHROUGH_ALL") == "1":
        return dict(os.environ)
    extra = {v.strip() for v in os.environ.get("AGENT_ENV_ALLOWLIST", "").split(",")
             if v.strip()}
    env: dict[str, str] = {}
    for k, v in os.environ.items():
        if k in _ENV_EXACT or k in extra or k.startswith(_ENV_PREFIXES):
            env[k] = v
    return env


def _agent_model() -> str | None:
    """A56 (Batch 2-4): explicit model pin for agent spawns. Without it the
    crew's behavior (and every rubric calibration) silently changes with
    the operator's CLI default. Set AGENT_MODEL (e.g. in webapp/.env);
    unset preserves the CLI default but the spawn event records that."""
    return os.environ.get("AGENT_MODEL") or None


def _build_retrieval_mcp_config(
    reference_repo: Path | None,
    target_repo: Path | None,
    log_path: Path | None,
    *,
    tool_budget: int | None = None,
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
    if tool_budget is not None:
        # A57 (Batch 2-4): the MCP server enforces the R8 budget GRACEFULLY
        # (returns "budget exhausted; use what you have" as a tool result,
        # letting the agent finish with the evidence it has). Keep it in
        # sync with the harness's max_retrieval_calls; the harness kill is
        # only a 2× backstop for an agent that ignores repeated denials.
        server_env["RETRIEVAL_TOOL_BUDGET"] = str(tool_budget)
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


GROUNDED_RETRIEVAL_TOOLS = {
    "mcp__retrieval__semantic_search",
    "mcp__retrieval__graph_neighbors",
    "mcp__retrieval__graph_find_similar",
    "mcp__retrieval__graph_summary",
}
MUTATING_TOOLS = {"Write", "Edit", "NotebookEdit"}

# R13: history-rewriting git commands the agent must NEVER run on its own
# branch. The orchestrator owns ref lineage (A1 non-FF auto-rebase exists);
# agents trying to do it themselves create the exact non-FF state A1 is meant
# to recover from. Surfaced by doctrine-meta-agent against the api-keys sprint
# (proposal: sprint-run-20260524T014937Z-agent-initiated-rebase.md), where
# QA agents in BL-0004 and BL-0006 both rebased mid-retry and produced
# doctrine_check incomplete attempt=2 with "agent rebased or reset history".
#
# Anchored on the mutation verbs only — read-only git (log/diff/status/show/
# blame/rev-parse/branch --list) is unaffected. Tier-1.5-style streaming kill
# on the Bash tool_use BEFORE the command executes.
import re as _re

FORBIDDEN_GIT_RE = _re.compile(
    r"\bgit\s+("
    r"rebase\b"
    r"|reset\s+--hard\b"
    r"|push\s+(--force\b|--force-with-lease\b|-f\b)"
    r"|filter-branch\b"
    r"|commit\s+--amend\b"
    r"|update-ref\b"
    r"|tag\s+-d\b"
    r"|branch\s+-D\b"
    r")",
    _re.IGNORECASE,
)


def _tool_uses_in_event(evt: dict) -> list[dict]:
    """Extract tool_use blocks from an assistant event. Returns [] for non-assistant events."""
    if evt.get("type") != "assistant":
        return []
    content = (evt.get("message") or {}).get("content") or []
    if not isinstance(content, list):
        return []
    return [c for c in content if isinstance(c, dict) and c.get("type") == "tool_use"]


def _tool_result_ids_in_event(evt: dict) -> list[str]:
    """Batch 2-3 (A45): extract tool_use_ids acknowledged by a user event's
    tool_result blocks. Pairing these against emitted tool_use ids tells the
    idle-timeout whether the agent is *busy* (a tool is in flight — e.g. a
    long pytest/playwright/docker child) versus genuinely *silent*."""
    if evt.get("type") != "user":
        return []
    content = (evt.get("message") or {}).get("content") or []
    if not isinstance(content, list):
        return []
    return [
        c.get("tool_use_id") for c in content
        if isinstance(c, dict) and c.get("type") == "tool_result" and c.get("tool_use_id")
    ]


MAX_RETRIEVAL_CALLS_DEFAULT = 30  # brownfield SKILLS.md states this budget


async def stream_agent_task(
    task: str,
    repo_path: str | Path,
    *,
    timeout_seconds: int = 1800,
    idle_timeout: int | None = 600,
    allowed_tools: str = "Bash,Read,Write,Edit",
    reference_repo: str | Path | None = None,
    target_repo: str | Path | None = None,
    retrieval_log_path: str | Path | None = None,
    min_pregrounding: int = 0,
    max_retrieval_calls: int = MAX_RETRIEVAL_CALLS_DEFAULT,
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
        tool_budget=max_retrieval_calls,  # A57: server denies gracefully first
    )
    if retrieval is not None:
        mcp_config_path, mcp_tools = retrieval
        extra_cli += ["--mcp-config", str(mcp_config_path)]
        effective_allowed = ",".join([allowed_tools, *mcp_tools])

    model = _agent_model()  # A56: pin, and record in the spawn event
    if model:
        extra_cli += ["--model", model]

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

    # A52 (Batch 7-3): allowlisted env — retrieval secrets never reach the
    # agent process (they flow to the MCP server via its own config env).
    env = {
        **_agent_env(),
        "GIT_AUTHOR_NAME": os.environ.get("GIT_AUTHOR_NAME", "Claude Agent"),
        "GIT_AUTHOR_EMAIL": os.environ.get("GIT_AUTHOR_EMAIL", "agent@webapp.local"),
        "GIT_COMMITTER_NAME": os.environ.get("GIT_COMMITTER_NAME", "Claude Agent"),
        "GIT_COMMITTER_EMAIL": os.environ.get("GIT_COMMITTER_EMAIL", "agent@webapp.local"),
    }

    spawn_evt = {"type": "_meta", "phase": "spawn", "cmd": cmd[:4] + ["..."],
                 # A56: model identity travels with the trace (harness_sha's
                 # sibling — code version AND model version per run).
                 "model": model or "(cli default)"}
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
        # A44: raise the StreamReader line-buffer ceiling from asyncio's 64 KiB
        # default. stream-json lines routinely exceed 64 KiB (a Read tool_result
        # for a ~29 KB+ file already does); the default made readline() raise
        # LimitOverrunError and kill the agent mid-read (the BL-0004 abort).
        limit=STREAM_READER_LIMIT,
        # B1: spawn in a new session/process-group so we can pgroup-kill the
        # whole subtree (claude + MCP servers + any shell helpers) on cleanup
        # rather than leaking children when SSE disconnects.
        start_new_session=True,
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

    grounded_count = 0  # running tally of grounded retrieval calls in this run
    retrieval_call_count = 0  # ALL mcp__retrieval__* calls (incl. target_status)
    pregrounding_violated = False
    budget_exceeded = False
    forbidden_git_op: str | None = None  # R13: captures the offending command for the kill event
    try:
        assert proc.stdout is not None
        try:
            # Batch 2-3 (A45): the idle clock is suspended while a tool is
            # in flight. B5's original heuristic equated "no stream token
            # for N seconds" with "hung" — but an agent blocking on a long
            # synchronous child (gate / pytest / playwright, routinely
            # 10–25 min) is fully alive and stream-silent. We track
            # tool_use ids without a matching tool_result: while that set
            # is non-empty the agent is *busy*, and only the wall timeout
            # applies. Genuine silence (no tool in flight) still hits the
            # idle timeout as before. Wall time is now also enforced
            # cumulatively across the whole run, not per-readline.
            in_flight_tools: set[str] = set()
            while True:
                remaining_wall = timeout_seconds - (loop.time() - start)
                if remaining_wall <= 0:
                    await _kill_pgroup(proc)
                    evt = {
                        "type": "_error",
                        "error": (
                            f"agent exceeded wall timeout {timeout_seconds}s "
                            f"(in_flight_tools={len(in_flight_tools)})"
                        ),
                        "kind": "wall_timeout",
                        "in_flight_tools": len(in_flight_tools),
                    }
                    if trace is not None:
                        trace.write_event(evt)
                    yield evt
                    return
                if idle_timeout is not None and not in_flight_tools:
                    effective_timeout = min(idle_timeout, remaining_wall)
                else:
                    # Busy (tool in flight) or no idle timeout configured:
                    # wait out the remaining wall budget.
                    effective_timeout = remaining_wall
                # readline with timeout so a hung claude process doesn't hang us.
                try:
                    raw = await asyncio.wait_for(
                        proc.stdout.readline(),
                        timeout=max(1.0, effective_timeout),
                    )
                except asyncio.TimeoutError:
                    await _kill_pgroup(proc)
                    idle_fired = (
                        idle_timeout is not None
                        and not in_flight_tools
                        and effective_timeout < remaining_wall
                    )
                    kind = "idle_timeout" if idle_fired else "wall_timeout"
                    evt = {
                        "type": "_error",
                        "error": (
                            f"agent silent for {round(effective_timeout)}s "
                            f"({kind}; idle={idle_timeout} wall={timeout_seconds}; "
                            f"in_flight_tools={len(in_flight_tools)})"
                        ),
                        "kind": kind,
                        "idle_seconds": round(effective_timeout),
                        "in_flight_tools": len(in_flight_tools),
                    }
                    if trace is not None:
                        trace.write_event(evt)
                    yield evt
                    return
                except ValueError as exc:
                    # A44 defense-in-depth: with STREAM_READER_LIMIT raised to
                    # 64 MiB this should never fire, but if a single stream-json
                    # line ever exceeds even that, label it honestly. NOTE:
                    # StreamReader.readline() catches the underlying
                    # asyncio.LimitOverrunError and RE-RAISES it as
                    # `ValueError(e.args[0])` — which is precisely the
                    # "ValueError: Separator is found, but chunk is longer than
                    # limit" seen in the BL-0004 trace — so we catch ValueError
                    # here, not LimitOverrunError. The buffer is NOT recoverable,
                    # so we kill and surface a distinct event rather than letting
                    # the broad `except Exception` mislabel it as a generic error
                    # the orchestrator reads as "agent produced no source change".
                    if "chunk is longer than limit" not in str(exc):
                        raise  # not the overrun ValueError — let it propagate
                    await _kill_pgroup(proc)
                    over_evt = {
                        "type": "_meta",
                        "phase": "stream_overrun",
                        "kind": "killed",
                        "limit_bytes": STREAM_READER_LIMIT,
                        "error": f"{type(exc).__name__}: {exc}",
                        "reason": (
                            "A single claude stream-json line exceeded the "
                            f"{STREAM_READER_LIMIT}-byte reader limit. This is a "
                            "harness I/O failure, NOT agent non-compliance. See "
                            "A44 in DESIGN_SHORTCOMINGS.md."
                        ),
                    }
                    if trace is not None:
                        trace.write_event(over_evt)
                    yield over_evt
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

                # ─── A45: in-flight tool tracking for the idle clock ────────
                for _tu in _tool_uses_in_event(evt):
                    _tid = _tu.get("id")
                    if _tid:
                        in_flight_tools.add(_tid)
                for _rid in _tool_result_ids_in_event(evt):
                    in_flight_tools.discard(_rid)

                # ─── Pre-modification grounding + budget enforcement ────────
                # R5/Tier1.5: ≥min_pregrounding grounded calls before any
                # mutating tool (Write/Edit/NotebookEdit). target_status is
                # inventory only and does not count toward grounding.
                # R8: total mcp__retrieval__* calls capped at max_retrieval_calls.
                for tu in _tool_uses_in_event(evt):
                    name = tu.get("name", "")
                    if name.startswith("mcp__retrieval__"):
                        retrieval_call_count += 1
                        if name in GROUNDED_RETRIEVAL_TOOLS:
                            grounded_count += 1
                        # A57: the MCP server denies calls past the budget
                        # gracefully (agent keeps its in-flight work). The
                        # harness kill is a 2× BACKSTOP for an agent that
                        # ignores repeated denials — not the primary
                        # enforcement anymore.
                        if retrieval_call_count > max_retrieval_calls * 2:
                            budget_exceeded = True
                            break
                    elif (
                        min_pregrounding > 0
                        and name in MUTATING_TOOLS
                        and grounded_count < min_pregrounding
                    ):
                        pregrounding_violated = True
                        break
                    elif name == "Bash":
                        # R13: streaming-kill on history-rewriting git commands.
                        # Agents own files in their worktree, never refs.
                        cmd = (tu.get("input") or {}).get("command", "")
                        if isinstance(cmd, str) and FORBIDDEN_GIT_RE.search(cmd):
                            forbidden_git_op = cmd[:500]  # cap for the event
                            break

                if trace is not None:
                    trace.write_event(evt)
                yield evt

                # A44 companion: surface a CLI-side API error (e.g. the
                # `400 ... thinking blocks ... cannot be modified` that hit
                # BL-0004 attempt 3) as a distinct event. The orchestrator
                # otherwise only inspects files-on-disk after the run, so an API
                # failure is silently indistinguishable from "agent produced no
                # source change" — and burns an R10.1 retry / aborts the sprint
                # under a false label. This event lets the control flow and the
                # operator tell the two apart. Follow-up (tracked in A44): have
                # the orchestrator treat phase=api_error as a RETRIABLE infra
                # failure rather than a doctrine-incomplete attempt.
                if (
                    isinstance(evt, dict)
                    and evt.get("type") == "result"
                    and evt.get("is_error")
                ):
                    api_evt = {
                        "type": "_meta",
                        "phase": "api_error",
                        "api_error_status": evt.get("api_error_status"),
                        "subtype": evt.get("subtype"),
                        "num_turns": evt.get("num_turns"),
                        "detail": str(evt.get("result", ""))[:500],
                        "reason": (
                            "claude CLI returned an API error (not a doctrine "
                            "decision); distinct from 'agent did no work'. See A44."
                        ),
                    }
                    if trace is not None:
                        trace.write_event(api_evt)
                    yield api_evt

                if budget_exceeded:
                    await _kill_pgroup(proc)
                    bud_evt = {
                        "type": "_meta",
                        "phase": "retrieval",
                        "kind": "budget_exceeded",
                        "retrieval_call_count": retrieval_call_count,
                        "max": max_retrieval_calls,
                        "backstop": max_retrieval_calls * 2,
                        "reason": (
                            f"Agent exceeded the 2x retrieval backstop: "
                            f"{retrieval_call_count} > {max_retrieval_calls * 2} "
                            f"mcp__retrieval__* calls despite the MCP server "
                            f"denying every call past {max_retrieval_calls} (A57). "
                            f"Brownfield SKILLS.md states a 30-call budget."
                        ),
                    }
                    if trace is not None:
                        trace.write_event(bud_evt)
                    yield bud_evt
                    return

                if pregrounding_violated:
                    await _kill_pgroup(proc)
                    viol_evt = {
                        "type": "_meta",
                        "phase": "pre_grounding_violation",
                        "kind": "insufficient",
                        "grounded_count": grounded_count,
                        "required": min_pregrounding,
                        "reason": (
                            f"Agent attempted Write/Edit/NotebookEdit after only "
                            f"{grounded_count} grounded retrieval call(s); doctrine "
                            f"requires ≥{min_pregrounding} before any code mutation."
                        ),
                    }
                    if trace is not None:
                        trace.write_event(viol_evt)
                    yield viol_evt
                    return

                if forbidden_git_op is not None:
                    # R13: streaming-kill on history-rewriting git command.
                    # The orchestrator owns ref lineage (A1 non-FF auto-rebase).
                    # Agents own files in their worktree, not refs.
                    await _kill_pgroup(proc)
                    git_evt = {
                        "type": "_meta",
                        "phase": "forbidden_git_op",
                        "kind": "killed",
                        "command": forbidden_git_op,
                        "reason": (
                            "Agent attempted a history-rewriting git command on its "
                            "own branch (rebase / reset --hard / push -f / "
                            "commit --amend / filter-branch / update-ref / "
                            "tag -d / branch -D). The orchestrator owns ref "
                            "lineage and handles non-FF state via the A1 "
                            "auto-rebase path; agents own only files in the "
                            "worktree. See R13 in CLAUDE.md."
                        ),
                    }
                    if trace is not None:
                        trace.write_event(git_evt)
                    yield git_evt
                    return
        finally:
            # B1: if proc is still alive when we hit finally (cancelled,
            # GeneratorExit, exception), pgroup-kill before waiting so the
            # subsequent reap never blocks indefinitely.
            if proc.returncode is None:
                await _kill_pgroup(proc)
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass
            if not stderr_task.done():
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
            # On GeneratorExit (consumer disconnect), yielding raises — the
            # trace already captured the exit, so skip silently.
            try:
                yield exit_evt
            except GeneratorExit:
                pass
    except Exception as exc:  # noqa: BLE001
        await _kill_pgroup(proc)
        err_evt = {"type": "_error", "error": f"{type(exc).__name__}: {exc}"}
        if trace is not None:
            trace.write_event(err_evt)
        yield err_evt
    finally:
        # B1: guarantee no orphan subprocess on any exit path — including
        # consumer-cancelled (SSE disconnect → GeneratorExit) and unhandled
        # exceptions. _kill_pgroup is a no-op if proc has already exited.
        await _kill_pgroup(proc)
        if stderr_task is not None and not stderr_task.done():
            stderr_task.cancel()
        if mcp_config_path is not None:
            try:
                mcp_config_path.unlink()
            except OSError:
                pass
