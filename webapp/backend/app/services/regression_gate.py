"""Regression-gated auto-merge for brownfield doctrine.

Before fast-forwarding the agent branch into the configured target branch,
run the repo's full test suite both BEFORE the merge (against the current
target) and AFTER a dry-run merge into a disposable worktree. Compare the
pass/fail sets and reject the auto-merge if any test that was previously
passing now fails.

This function returns a structured dict the router emits to the SSE log as
a `_meta phase=regression_gate` event. The caller decides whether to call
`fast_forward_target` on a green verdict.

Greenfield (or when the resolved agent_branch == "main" AND no .agentic-skills.json
file exists AND no `_brownfield` artifact dir exists) is treated as "not gated"
and returns `{ok: True, kind: "skipped", reason: "greenfield"}`.
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.services.brownfield import detect_test_command, pick_artifact_dir
from app.services import repo_config as repo_config_svc


PYTEST_RESULT_RE = re.compile(r"^(?P<file>tests?/[\w./-]+)::(?P<name>[\w.\[\]-]+)\s+(?P<verdict>PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)", re.MULTILINE)


@dataclass
class TestSet:
    passed: set[str]
    failed: set[str]
    raw_exit: int
    raw_tail: str

    def to_dict(self) -> dict:
        return {
            "n_passed": len(self.passed),
            "n_failed": len(self.failed),
            "exit_code": self.raw_exit,
        }


async def _run_capture(cmd: list[str], cwd: Path, timeout: int = 1800) -> tuple[int, str, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        # Command binary not on PATH — surface a structured error instead of
        # crashing the SSE stream. Caller treats this as kind="error".
        return 127, "", f"command not found: {cmd[0]!r}: {exc}"
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return -1, "", f"test command timed out after {timeout}s"
    return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")


def _parse_pytest(stdout: str, stderr: str) -> tuple[set[str], set[str]]:
    """Extract per-test verdicts from pytest output. Best-effort.

    pytest with the default `-v` formatting emits one line per test like:
        tests/test_x.py::test_y PASSED
    With `-q` (quiet) we instead get a single status-bar summary; in that
    case we fall back to a single bucket and treat unparseable runs as
    `{passed: ['<summary>'], failed: []}` on exit_code == 0 and the inverse
    on non-zero. That's not perfect for differential gating, but it's the
    realistic floor for arbitrary repos.
    """
    text = stdout + "\n" + stderr
    passed: set[str] = set()
    failed: set[str] = set()
    for m in PYTEST_RESULT_RE.finditer(text):
        nodeid = f"{m['file']}::{m['name']}"
        v = m["verdict"]
        if v in ("PASSED", "XPASS"):
            passed.add(nodeid)
        elif v in ("FAILED", "ERROR"):
            failed.add(nodeid)
    return passed, failed


async def _run_tests(cwd: Path, cmd: list[str]) -> TestSet:
    # If pytest is the runner and the user hasn't pinned `-v`, add it so we
    # get parseable per-test verdicts.
    effective = list(cmd)
    if effective and effective[0] == "pytest" and "-v" not in effective and "--verbose" not in effective:
        effective.append("-v")
    exit_code, stdout, stderr = await _run_capture(effective, cwd)
    passed, failed = _parse_pytest(stdout, stderr)
    tail = (stdout + "\n" + stderr).splitlines()[-30:]
    return TestSet(passed=passed, failed=failed, raw_exit=exit_code, raw_tail="\n".join(tail))


async def _git(args: list[str], cwd: Path) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "git", *args, cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return proc.returncode or 0, (out + err).decode(errors="replace")


async def run_gate(repo_root: Path, agent_branch: str, target_ref: str) -> dict:
    """Run pre/post differential test suite around a dry-run merge.

    Returns a dict suitable for the SSE log:

        {
          "ok": <bool>,
          "kind": "green" | "regressed" | "skipped" | "error",
          "pre":  {n_passed, n_failed, exit_code},
          "post": {n_passed, n_failed, exit_code},
          "regressions": [<test nodeid>, ...],
          "new_failures": [<test nodeid>, ...],   # not previously passing
          "command": ["pytest", "-v", ...],
          "reason": "<one-line summary>",
        }
    """
    cfg = repo_config_svc.load(repo_root)
    # Skip gating when the repo is unmistakably greenfield AND no override
    # config exists. Heuristic: no .agentic-skills.json AND no _brownfield dir
    # AND agent_branch defaulted to "main".
    has_cfg_file = (repo_root / repo_config_svc.CONFIG_FILENAME).exists()
    artifact_dir = pick_artifact_dir(repo_root)
    has_artifact = (repo_root / artifact_dir).exists()
    if not has_cfg_file and not has_artifact and cfg.agent_branch == "main":
        return {"ok": True, "kind": "skipped", "reason": "greenfield (no config, no artifact dir)", "command": []}

    test_cmd = cfg.test_cmd or detect_test_command(repo_root)
    # Sanity: the binary must exist on PATH (or be an absolute path) before we
    # bother creating worktrees. Saves ~5s and a confusing FileNotFoundError.
    if test_cmd:
        binary = test_cmd[0]
        if "/" not in binary and not shutil.which(binary):
            return {
                "ok": False, "kind": "error",
                "reason": (f"test binary {binary!r} not found on PATH. "
                           f"Set 'test_cmd' in {repo_root / '.agentic-skills.json'} "
                           "to a working command (e.g. ['docker','compose','exec','-T','backend','pytest','-q'])."),
                "command": test_cmd,
            }

    # Pre-merge baseline: run against the current target_ref (i.e. what
    # production looks like before this agent's commits).
    code, _ = await _git(["rev-parse", "--verify", target_ref], cwd=repo_root)
    if code != 0:
        return {"ok": False, "kind": "error", "reason": f"target ref {target_ref} not found", "command": test_cmd}
    code, _ = await _git(["rev-parse", "--verify", agent_branch], cwd=repo_root)
    if code != 0:
        return {"ok": False, "kind": "error", "reason": f"agent branch {agent_branch} not found", "command": test_cmd}

    # Use a disposable worktree to avoid mutating the active checkout.
    wt_id = uuid.uuid4().hex[:8]
    wt_pre = repo_root.parent / ".gate-worktrees" / f"pre-{wt_id}"
    wt_post = repo_root.parent / ".gate-worktrees" / f"post-{wt_id}"
    wt_pre.parent.mkdir(parents=True, exist_ok=True)

    try:
        code, msg = await _git(["worktree", "add", "--detach", str(wt_pre), target_ref], cwd=repo_root)
        if code != 0:
            return {"ok": False, "kind": "error", "reason": f"pre worktree add failed: {msg.strip()}", "command": test_cmd}
        pre = await _run_tests(wt_pre, test_cmd)

        code, msg = await _git(["worktree", "add", "--detach", str(wt_post), target_ref], cwd=repo_root)
        if code != 0:
            return {"ok": False, "kind": "error", "reason": f"post worktree add failed: {msg.strip()}", "command": test_cmd}
        # Dry-run merge inside the post worktree (does NOT touch repo_root).
        code, msg = await _git(["-C", str(wt_post), "merge", "--ff-only", agent_branch], cwd=repo_root)
        if code != 0:
            # Try a regular merge in the disposable worktree — if it conflicts,
            # surface that as `error` and let the caller decide.
            code2, msg2 = await _git(["-C", str(wt_post), "merge", "--no-edit", agent_branch], cwd=repo_root)
            if code2 != 0:
                return {
                    "ok": False, "kind": "error",
                    "reason": f"dry-run merge failed: {msg2.strip()[:400]}",
                    "command": test_cmd,
                }
        post = await _run_tests(wt_post, test_cmd)

        # A test that was passing pre-merge but is now failing (or missing) is a regression.
        regressions = sorted(pre.passed - post.passed)
        new_failures = sorted(post.failed - pre.failed)
        # Distinguish "tests ran clean" from "tests never ran". If post exited
        # non-zero but emitted no parseable results, the gate is inconclusive
        # (e.g. backend container down, missing fixture, import error) — that
        # is NOT 'green'.
        post_executed = bool(post.passed or post.failed)
        if regressions:
            kind, reason = "regressed", f"{len(regressions)} regression(s); post exit={post.raw_exit}"
        elif not post_executed and post.raw_exit != 0:
            kind, reason = "inconclusive", f"tests did not execute (post exit={post.raw_exit}); fix the test command or the runtime, then retry"
        elif not post_executed:
            kind, reason = "inconclusive", "tests did not execute (no pass/fail parsed); verify test_cmd"
        else:
            kind, reason = "green", f"post suite green ({len(post.passed)} passed)"
        ok = (kind == "green")
        return {
            "ok": ok,
            "kind": kind,
            "pre": pre.to_dict(),
            "post": post.to_dict(),
            "regressions": regressions[:50],
            "new_failures": new_failures[:50],
            "command": test_cmd,
            "reason": reason,
            "post_tail": post.raw_tail[-2000:],
        }
    finally:
        for wt in (wt_pre, wt_post):
            await _git(["worktree", "remove", "--force", str(wt)], cwd=repo_root)
