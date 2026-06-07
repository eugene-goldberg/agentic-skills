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
import os
import re
import shlex
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.services.brownfield import detect_test_command, pick_artifact_dir
from app.services import repo_config as repo_config_svc
from app.services import volume_reaper as volume_reaper_svc
from app.services.doctrine_validator import detect_infra_failure

# A26: minimum free disk space (in GB) on the docker storage mount before
# the gate is willing to spin up another pre/post worktree + docker compose
# stack. Below this floor, gates routinely fail mid-run with ENOSPC during
# `bun install` / image build / volume create, masquerading as code
# regressions and exhausting engineer retry budget on unfixable problems.
_MIN_FREE_GB = 5.0


def _free_gb(path: Path) -> float:
    """Return free disk space (GB) on the filesystem containing path."""
    try:
        s = shutil.disk_usage(str(path))
        return s.free / (1024 ** 3)
    except Exception:
        return float("inf")  # don't block on diagnostic failure


def _compose_project_prefix(run_id: str | None) -> str | None:
    """M2-1: build a stable docker-compose project-name prefix encoding the
    run_id, so closure_check (Move 2) can scan for orphan gate containers by
    name pattern. Returns None if run_id is unavailable — call sites then
    skip the override and let docker-compose use its directory-basename
    default (the prior behavior).

    Format: ``agentic-skills-<run_id_short>``. Compose appends ``-<service>-1``
    per container, so a scan filter of ``name=agentic-skills-<run_id_short>-``
    matches the full container set from one run.
    """
    if not run_id:
        return None
    # run_id is already short-ish (e.g. "run-20260523T212548Z-5bfff3"); strip
    # the "run-" prefix to keep the docker name under the 63-char ceiling
    # docker-compose imposes on project names.
    # A22: docker-compose project names must be lowercase alphanumeric+hyphen/underscore.
    # ISO-8601 timestamps include uppercase T/Z which compose rejects with
    # "invalid project name: must consist only of lowercase ...". Lowercase
    # the whole prefix so any future run_id schema also passes validation.
    short = run_id.removeprefix("run-")[:40].lower()
    return f"agentic-skills-{short}"


# A48 fix #3 (2026-06-01): DiskFull-aware classifier. When the gate's
# `post_tail` carries a disk-exhaustion error, the canonical SQLAlchemy
# surface error is `PendingRollbackError` — the *cascade* failure caused
# by the session going DEACTIVE after the original ENOSPC. The operator-
# valuable signal is the original `psycopg.errors.DiskFull` (or analog)
# line, which sits ~3 KB deeper in the tail. These patterns pull that
# original line out so the orchestrator's `infra_fail` payload carries
# the *cause*, not the *cascade*.
_DISK_FULL_PATTERNS = (
    # postgres-via-psycopg, the empirical signal from BL-0003 abort
    re.compile(
        r"^.*psycopg\.errors\.DiskFull:.*$",
        re.MULTILINE,
    ),
    # postgres direct: "could not extend file" is the canonical wording
    re.compile(
        r'^.*could not extend file ".*": No space left on device.*$',
        re.MULTILINE,
    ),
    # SQLAlchemy/SQLite/other DBs
    re.compile(
        r"^.*OperationalError.*(?:disk full|disk I/O error|no space).*$",
        re.MULTILINE | re.IGNORECASE,
    ),
    # POSIX-level ENOSPC (last-resort; matches even non-DB code paths)
    re.compile(
        r"^.*No space left on device.*$",
        re.MULTILINE,
    ),
    # Filesystem quota (typical of CI quota'd workspaces; user reports as
    # "disk full" experientially even though the host has space)
    re.compile(
        r"^.*[Dd]isk quota exceeded.*$",
        re.MULTILINE,
    ),
)


def extract_disk_full_reason(post_tail: str) -> str | None:
    """A48 fix #3: pull the original disk-exhaustion line out of a noisy
    cascade tail. Returns the trimmed line (≤300 chars) or None when
    nothing matches.

    Patterns scanned in priority order; the first hit wins. This is
    deliberately a separate scan from `detect_infra_failure` so the
    orchestrator can distinguish "host_disk_full" specifically (a
    completely different operator action — free space, prune volumes —
    versus generic infra noise).
    """
    if not post_tail:
        return None
    for pat in _DISK_FULL_PATTERNS:
        m = pat.search(post_tail)
        if m:
            return m.group(0).strip()[:300]
    return None


# A49 (2026-06-03/04, invoice-soft-delete dispatch; fix #2 2026-06-06,
# operator-approved): the regression gate is non-deterministic. Transient
# network/IO errors AND Playwright timing flakes (element-stability /
# 90s test-timeout) can fail a test on ALL per-test retries and surface as a
# `regressed`/`inconclusive` verdict that blocks a CORRECT change from merging —
# a verdict that is NOT a function of the diff under test (second live instance:
# item-comments BL-0001, a dark-mode E2E timed out on the QA re-gate of a tree
# that had gated GREEN an hour earlier).
#
# The Playwright markers below are AMBIGUOUS — a "Test timeout exceeded" can also
# be a *real* break (a page that never renders; cf. Horizon's auth break).
# Treating them as merely *suspected* transient is safe ONLY because the chosen
# A49 strategy never blind-flips a red to green: run_gate either (a) finds the
# identical tree already gated green this run, or (b) re-samples by re-running the
# gate once and takes the re-run as authoritative. A reproducible real failure is
# therefore still caught. `detect_transient_markers` decides only *whether to
# arbitrate*, never the final verdict.
_TRANSIENT_MARKERS = (
    re.compile(r"socket hang up", re.IGNORECASE),
    re.compile(r"\bECONNRESET\b", re.IGNORECASE),
    re.compile(r"\bECONNREFUSED\b", re.IGNORECASE),
    re.compile(r"\bETIMEDOUT\b", re.IGNORECASE),
    re.compile(r"\bNetwork Error\b", re.IGNORECASE),
    # Playwright timing flakes (A49 fix #2):
    re.compile(r"Test timeout of \d+ms exceeded", re.IGNORECASE),
    re.compile(r"waiting for element to be visible, enabled and stable", re.IGNORECASE),
    re.compile(r"Target (?:page|frame), context or browser has been closed", re.IGNORECASE),
)


def detect_transient_markers(post_tail: str) -> list[str]:
    """A49: return the distinct suspected-transient markers present in the gate
    tail, in first-seen order (network/IO errors + Playwright timing flakes).

    This decides only whether run_gate should *arbitrate* a red verdict (via the
    same-SHA green memory or a single gate re-run) — it never flips the verdict
    itself, so it cannot mask a reproducible real regression. Returns ``[]`` when
    none match.
    """
    if not post_tail:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for pat in _TRANSIENT_MARKERS:
        m = pat.search(post_tail)
        if m:
            tok = m.group(0).lower()
            if tok not in seen:
                seen.add(tok)
                found.append(m.group(0))
    return found


# A49 fix #2 (2026-06-06, operator-approved): same-SHA green memory. Keyed by
# run_id → set of agent-branch head SHAs that produced a GREEN gate this run.
# A later regressed/inconclusive verdict on an IDENTICAL tree whose only
# failures are suspected-transient is gate non-determinism (the code is
# byte-identical to a run we already saw pass), so it is disregarded. Process-
# local and run-scoped; the orchestrator calls clear_green_shas() at run end.
_GREEN_SHAS: dict[str, set[str]] = {}


def _record_green_sha(run_id: str | None, head_sha: str | None) -> None:
    if run_id and head_sha:
        _GREEN_SHAS.setdefault(run_id, set()).add(head_sha)


def _sha_was_green(run_id: str | None, head_sha: str | None) -> bool:
    return bool(run_id and head_sha and head_sha in _GREEN_SHAS.get(run_id, set()))


def clear_green_shas(run_id: str | None) -> None:
    """Drop a run's green-SHA memory at termination (orchestrator calls this)."""
    if run_id:
        _GREEN_SHAS.pop(run_id, None)


def _suspected_transient(result: dict) -> bool:
    """A49: the verdict is red/inconclusive AND its tail carries suspected-
    transient markers, so it warrants arbitration (same-SHA green or a re-run)
    rather than being taken at face value."""
    return (result.get("kind") in ("regressed", "inconclusive")
            and bool(result.get("transient_markers")))


# Item #1 fix (2026-06-07): allow an optional directory prefix before the
# `tests/` segment so node-ids like `backend/tests/test_x.py::test_y` parse —
# the prior `^tests?/` anchor silently matched ZERO on targets that run pytest
# from the repo root (e.g. `pytest backend/tests`), yielding "0 passed" and the
# acceptance regression_checkpoint `inconclusive`. The `(?:[\w.-]+/)*` prefix is
# backward-compatible (matches zero segments for bare `tests/...`).
PYTEST_RESULT_RE = re.compile(r"^(?P<file>(?:[\w.-]+/)*tests?/[\w./-]+)::(?P<name>[\w.\[\]-]+)\s+(?P<verdict>PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)", re.MULTILINE)

# A39 (2026-06-04 BL-0006 wedge): the gate template (regression_gate.sh)
# collapses every Playwright E2E failure into ONE synthetic pytest-format
# line, `tests/playwright::e2e_suite FAILED`. The parser above then reports
# a single regression nodeid no matter how many distinct E2E tests broke.
# The engineer retry prompt therefore says "1 regression:
# tests/playwright::e2e_suite" — opaque, un-actionable — so the engineer
# self-runs the gate to discover the real failures, which is exactly the
# loop that wedged BL-0006 for 8h. This regex parses Playwright's own
# failure-summary block to recover the per-test node-ids:
#
#     3 failed
#       [chromium] › tests/search.spec.ts:11:1 › Search page ... ──────────
#       [chromium] › tests/search.spec.ts:24:1 › Smart views ... ──────────
#     7 passed (3.3m)
#
#   - `\[[^\]]+\]`  matches any project label ([chromium]/[firefox]/[webkit]/…)
#   - `›`           is U+203A (Playwright's separator); inner `›` in a title
#                   is captured intact because the title group runs to EOL.
#   - location is `<path>:<line>:<col>`; the trailing fill is U+2500 (`─`).
PLAYWRIGHT_SUITE_NODEID = "tests/playwright::e2e_suite"
_PLAYWRIGHT_FAIL_RE = re.compile(
    r"\[[^\]]+\]\s*›\s*(?P<loc>[^\s›]+:\d+:\d+)\s*›\s*(?P<title>.+?)\s*(?:─|$)",
    re.MULTILINE,
)


def _extract_playwright_failures(raw_tail: str) -> list[dict]:
    """A39: expand the single synthetic ``tests/playwright::e2e_suite``
    regression into the real per-test Playwright failures parsed from the
    runner tail, so the engineer retry gets actionable test names.

    Returns a list of ``{location, title, nodeid}`` dicts, de-duplicated by
    nodeid in first-seen order. The Playwright failure summary is printed
    once per retry attempt, so the same failing test recurs in the tail;
    de-dup unions them. Returns ``[]`` when nothing parses (caller then
    keeps the opaque suite marker rather than dropping the regression).
    """
    if not raw_tail:
        return []
    seen: set[str] = set()
    out: list[dict] = []
    for m in _PLAYWRIGHT_FAIL_RE.finditer(raw_tail):
        location = m.group("loc").strip()
        title = m.group("title").strip().rstrip("─").strip()
        nodeid = f"tests/playwright::{location}"
        if nodeid in seen:
            continue
        seen.add(nodeid)
        out.append({"location": location, "title": title, "nodeid": nodeid})
    return out


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


async def _run_capture(cmd: list[str], cwd: Path, timeout: int = 1800,
                       env: dict[str, str] | None = None) -> tuple[int, str, str]:
    """Run cmd, capturing stdout/stderr. If env is given, merge it into the
    inherited process environment (caller-supplied keys win)."""
    proc_env: dict[str, str] | None
    if env:
        proc_env = os.environ.copy()
        proc_env.update(env)
    else:
        proc_env = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=proc_env,
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


async def _run_tests(cwd: Path, cmd: list[str], *,
                     compose_project: str | None = None) -> TestSet:
    # If pytest is the runner and the user hasn't pinned `-v`, add it so we
    # get parseable per-test verdicts.
    effective = list(cmd)
    if effective and effective[0] == "pytest" and "-v" not in effective and "--verbose" not in effective:
        effective.append("-v")
    # M2-1: when a compose_project name is supplied, pass it via the standard
    # docker-compose env var so containers spawned by the test_cmd carry a
    # predictable prefix that closure_check (Move 2) can scan for.
    env: dict[str, str] | None = None
    if compose_project:
        env = {"COMPOSE_PROJECT_NAME": compose_project}
    exit_code, stdout, stderr = await _run_capture(effective, cwd, env=env)
    passed, failed = _parse_pytest(stdout, stderr)
    # Last 300 lines so docker-compose cleanup at the end of a gate run
    # doesn't push real test failure output (Playwright summary, pytest
    # traceback) out of the captured tail.
    tail = (stdout + "\n" + stderr).splitlines()[-300:]
    return TestSet(passed=passed, failed=failed, raw_exit=exit_code, raw_tail="\n".join(tail))


async def _git(args: list[str], cwd: Path) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "git", *args, cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return proc.returncode or 0, (out + err).decode(errors="replace")


# ── Simple per-BL gate (operator directive 2026-06-06) ───────────────────────
# The per-BL gate runs ONLY the tests the BL itself added/changed — the
# engineer's unit tests for that BL — NOT the full regression suite and NOT
# Playwright. Whole-feature E2E + all-API + the one full-suite regression
# checkpoint live at the acceptance phase (end of sprint). This removes the
# diff-blind full-suite-per-BL gate that manufactured false reds on correctly-
# scoped backend BLs (see DESIGN_SHORTCOMINGS A55; supersedes per-BL A28–A31).

def _bl_test_files(changed: list[str]) -> list[str]:
    """The unit-test files a BL touched: python test files under a tests/ dir
    whose filename is test_*.py or *_test.py. (Playwright e2e specs under
    frontend are deliberately excluded — E2E is an acceptance-phase concern.)"""
    out: list[str] = []
    for f in changed:
        f = f.strip()
        if not f or not f.endswith(".py"):
            continue
        name = f.rsplit("/", 1)[-1]
        if "tests/" in f and (name.startswith("test_") or name.endswith("_test.py")):
            out.append(f)
    return out


async def run_bl_tests(repo_root: Path, agent_branch: str, base_ref: str,
                       *, run_id: str | None = None, timeout: int = 1800) -> dict:
    """Run ONLY the BL's own tests (the test files its commits added/changed),
    scoped to a db-only stack — no full suite, no Playwright.

    Returns a verdict dict shaped like ``run_gate`` so the per-BL flows consume
    it unchanged. ``kind`` ∈ {green, failed, no_tests, skipped, error}.
    """
    cfg = repo_config_svc.load(repo_root)
    has_cfg = (repo_root / repo_config_svc.CONFIG_FILENAME).exists()
    has_art = (repo_root / pick_artifact_dir(repo_root)).exists()
    if not has_cfg and not has_art and cfg.agent_branch == "main":
        return {"ok": True, "kind": "skipped", "reason": "greenfield",
                "command": [], "failing_tests": [], "regressions": [],
                "new_failures": [], "post_tail": ""}

    code, out = await _git(["diff", "--name-only", f"{base_ref}...{agent_branch}"], cwd=repo_root)
    if code != 0:
        code, out = await _git(["diff", "--name-only", f"{base_ref}..{agent_branch}"], cwd=repo_root)
    if code != 0:
        return {"ok": False, "kind": "error", "reason": f"git diff failed: {out.strip()[:200]}",
                "failing_tests": [], "regressions": [], "new_failures": [], "post_tail": ""}

    bl_tests = _bl_test_files([l for l in out.splitlines() if l.strip()])
    if not bl_tests:
        return {"ok": False, "kind": "no_tests",
                "reason": ("this BL added/changed no unit tests — doctrine requires "
                           "comprehensive per-BL unit tests; the engineer must add them"),
                "failing_tests": [], "regressions": [], "new_failures": [],
                "post_tail": "", "command": []}

    use_compose = (repo_root / "compose.yml").exists() and (repo_root / "compose.gate.yml").exists()
    wt_id = uuid.uuid4().hex[:8]
    wt = repo_root.parent / ".gate-worktrees" / f"bl-{wt_id}"
    wt.parent.mkdir(parents=True, exist_ok=True)
    base_proj = _compose_project_prefix(run_id)
    proj = f"{base_proj}-bl-{wt_id}" if base_proj else f"blgate-{wt_id}"
    compose = ["docker", "compose", "-f", "compose.yml", "-f", "compose.gate.yml", "-p", proj]
    cmd: list[str] = []
    try:
        code, msg = await _git(["worktree", "add", "--detach", str(wt), agent_branch], cwd=repo_root)
        if code != 0:
            return {"ok": False, "kind": "error", "reason": f"bl worktree add failed: {msg.strip()[:200]}",
                    "failing_tests": [], "regressions": [], "new_failures": [], "post_tail": ""}
        if use_compose:
            await _run_capture(compose + ["up", "-d", "db"], wt, timeout=300)
            for _ in range(30):
                _c, _h, _e = await _run_capture(compose + ["ps", "db", "--format", "{{.Health}}"], wt, timeout=30)
                if "healthy" in _h:
                    break
                await asyncio.sleep(2)
            await _run_capture(compose + ["run", "--rm", "prestart"], wt, timeout=600)
            rels = [f[len("backend/"):] if f.startswith("backend/") else f for f in bl_tests]
            inner = ("uv pip install --quiet pytest-timeout && pytest -v --timeout=120 "
                     "--timeout-method=signal " + " ".join(shlex.quote(r) for r in rels))
            cmd = compose + ["run", "--rm", "--no-deps",
                             "-v", f"{wt}/backend/tests:/app/backend/tests:ro",
                             "backend", "bash", "-c", inner]
            exit_code, stdout, stderr = await _run_capture(cmd, wt, timeout=timeout)
        else:
            binary = (cfg.test_cmd or detect_test_command(repo_root) or ["pytest"])[0]
            cmd = [binary, "-v", *bl_tests]
            exit_code, stdout, stderr = await _run_capture(cmd, wt, timeout=timeout)

        passed, failed = _parse_pytest(stdout, stderr)
        tail = "\n".join((stdout + "\n" + stderr).splitlines()[-300:])
        # Exit code is authoritative for pytest (0 = all passed). The parsed
        # node-ids are for NAMING failures in the retry prompt; when they don't
        # parse (e.g. a path prefix the parser doesn't anchor), fall back to the
        # BL test files so the engineer still gets actionable detail.
        if exit_code == 0:
            kind, ok, reason = "green", True, f"BL unit tests green ({len(passed)} passed)"
        else:
            kind, ok = "failed", False
            reason = (f"{len(failed)} BL unit-test failure(s)" if failed
                      else f"BL unit tests failed (exit={exit_code}); inspect tail")
        named = sorted(failed) if failed else (bl_tests if not ok else [])
        return {"ok": ok, "kind": kind, "reason": reason,
                "failing_tests": [{"nodeid": n} for n in named][:50],
                "regressions": named[:50], "new_failures": named[:50],
                "command": cmd, "post_tail": tail, "bl_test_files": bl_tests}
    finally:
        await _git(["worktree", "remove", "--force", str(wt)], cwd=repo_root)
        if use_compose:
            try:
                await _run_capture(compose + ["down", "-v", "--remove-orphans"], wt if wt.exists() else repo_root, timeout=120)
            except Exception:
                pass
            try:
                await volume_reaper_svc.reap(proj)
            except Exception:
                pass


async def run_gate(repo_root: Path, agent_branch: str, target_ref: str,
                   *, run_id: str | None = None, _allow_rerun: bool = True) -> dict:
    """Run the differential gate, with A49 non-determinism arbitration.

    Returns a dict suitable for the SSE log:

        {
          "ok": <bool>,
          "kind": "green" | "regressed" | "inconclusive" | "infra_fail"
                  | "skipped" | "error",
          "pre":  {n_passed, n_failed, exit_code},
          "post": {n_passed, n_failed, exit_code},
          "regressions": [<test nodeid>, ...],
          "new_failures": [<test nodeid>, ...],
          "command": ["pytest", "-v", ...],
          "reason": "<one-line summary>",
          "head_sha": <agent-branch HEAD>,        # for the same-SHA green memory
        }

    A49 arbitration (operator-approved, 2026-06-06): a `regressed`/`inconclusive`
    verdict whose only failures look transient (``_suspected_transient``) is NOT
    taken at face value:
      1. If the IDENTICAL agent-branch tree already produced a GREEN gate this
         run (same-SHA green memory), the red is gate non-determinism on byte-
         identical code → recovered to green.
      2. Otherwise the gate is RE-SAMPLED once (`_run_gate_once` again) and the
         re-run is authoritative: green re-run → flake recovered; red re-run →
         the failure reproduced → treated as a real failure.
    This never blind-flips a red to green, so a reproducible real regression is
    still caught. ``_allow_rerun=False`` disables the re-sample (used by tests).
    """
    result = await _run_gate_once(repo_root, agent_branch, target_ref, run_id=run_id)
    # A49 applies only to test verdicts; skipped/error/infra_fail pass through.
    if result.get("kind") not in ("green", "regressed", "inconclusive"):
        return result

    code, out = await _git(["rev-parse", "--verify", f"{agent_branch}^{{commit}}"],
                           cwd=repo_root)
    head_sha = out.strip() if code == 0 else None
    result["head_sha"] = head_sha

    if _suspected_transient(result):
        if _sha_was_green(run_id, head_sha):
            prior = result.get("reason", "")
            result["kind"] = "green"
            result["ok"] = True
            result["a49_recovered"] = "same-SHA green"
            result["reason"] = (
                "A49 recovered (identical tree already gated green this run); "
                f"transient red disregarded [was: {prior}]")
        elif _allow_rerun:
            rerun = await _run_gate_once(repo_root, agent_branch, target_ref,
                                         run_id=run_id)
            rerun["head_sha"] = head_sha
            rerun["reran"] = True
            if rerun.get("kind") == "green":
                rerun["a49_recovered"] = "re-run green"
                rerun["reason"] = (
                    "A49 recovered (re-run green; initial red was a transient "
                    f"flake) [initial: {result.get('reason', '')}]")
            else:
                rerun["a49_reran_reproduced"] = True
                rerun["reason"] = (
                    f"{rerun.get('reason', '')} "
                    "[A49: re-run reproduced the failure — treated as real, not a flake]")
            result = rerun

    if result.get("kind") == "green":
        _record_green_sha(run_id, head_sha)
    return result


async def _run_gate_once(repo_root: Path, agent_branch: str, target_ref: str,
                         *, run_id: str | None = None) -> dict:
    """One full differential gate pass (pre/post around a dry-run merge) in
    disposable worktrees. The A49 wrapper ``run_gate`` may call this twice to
    re-sample a suspected-transient red."""
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

    # A26: pre-flight disk check. The gate spawns two worktrees, builds two
    # docker stacks, and runs the test suite twice — each side can easily
    # consume 5–10 GB of transient image/volume/cache. When the docker
    # storage volume is near-full, ENOSPC fires mid-run and the gate emits
    # `tests/frontend::lint_typecheck_build FAILED` (or similar) which the
    # engineer agent then tries to "fix" with code edits. Surface the real
    # problem instead, before burning ~30 min on a doomed gate run.
    free = _free_gb(repo_root)
    if free < _MIN_FREE_GB:
        return {
            "ok": False, "kind": "infra_fail",
            "reason": (f"docker storage near-full: only {free:.1f} GB free on "
                       f"{repo_root} (need ≥{_MIN_FREE_GB:.1f} GB). Run "
                       "`docker system prune -a --volumes -f` then retry."),
            "command": test_cmd,
            "post_tail": "",
        }

    # Use a disposable worktree to avoid mutating the active checkout.
    wt_id = uuid.uuid4().hex[:8]
    wt_pre = repo_root.parent / ".gate-worktrees" / f"pre-{wt_id}"
    wt_post = repo_root.parent / ".gate-worktrees" / f"post-{wt_id}"
    wt_pre.parent.mkdir(parents=True, exist_ok=True)

    # M2-1: stable docker-compose project name prefix encoding the run_id
    # so closure_check can scan by name pattern. Two sub-names — pre/post —
    # because the gate runs the test_cmd twice in disposable worktrees.
    base_proj = _compose_project_prefix(run_id)
    pre_proj = f"{base_proj}-pre-{wt_id}" if base_proj else None
    post_proj = f"{base_proj}-post-{wt_id}" if base_proj else None

    try:
        code, msg = await _git(["worktree", "add", "--detach", str(wt_pre), target_ref], cwd=repo_root)
        if code != 0:
            return {"ok": False, "kind": "error", "reason": f"pre worktree add failed: {msg.strip()}", "command": test_cmd}
        pre = await _run_tests(wt_pre, test_cmd, compose_project=pre_proj)

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
        post = await _run_tests(wt_post, test_cmd, compose_project=post_proj)

        # A25b: before the regression/new-failure decision tree, check
        # whether the post-run tail carries an infrastructure-failure marker
        # (ENOSPC, OOMKilled, docker daemon error, postgres unreachable,
        # etc.). When it does, the gate failure is NOT a code regression
        # the engineer can fix — surface `kind=infra_fail` so the
        # orchestrator routes it to operator review rather than burning
        # retries on unfixable problems. This is distinct from `error`
        # (which means the gate itself couldn't run) — infra_fail means the
        # gate ran but the runtime crashed under it.
        infra = detect_infra_failure(post.raw_tail)
        if infra:
            # A48 fix #3: prefer the canonical disk-full line over the
            # cascade error (e.g. SQLAlchemy's PendingRollbackError). The
            # operator action is completely different from generic
            # ENOSPC — free space + prune volumes, not "fix the test."
            disk_full = extract_disk_full_reason(post.raw_tail)
            result: dict = {
                "ok": False, "kind": "infra_fail",
                "pre": pre.to_dict(), "post": post.to_dict(),
                "regressions": [], "new_failures": [],
                "command": test_cmd,
                "post_tail": post.raw_tail[-15000:],
            }
            if disk_full:
                result["reason"] = f"infra failure (host_disk_full): {disk_full[:200]}"
                result["infra_fail_reason"] = "host_disk_full"
            else:
                result["reason"] = f"infra failure: {infra[:200]}"
                result["infra_fail_reason"] = "other"
            return result

        # A test that was passing pre-merge but is now failing (or missing) is a regression.
        regressions = sorted(pre.passed - post.passed)
        new_failures = sorted(post.failed - pre.failed)

        # A39: when the opaque Playwright suite marker is among the failures,
        # expand it into the real per-test node-ids parsed from the tail.
        # Only fire when the marker is actually present so non-E2E gates pay
        # nothing; if extraction yields nothing the marker is left in place.
        playwright_failures: list[dict] = []
        if PLAYWRIGHT_SUITE_NODEID in regressions or PLAYWRIGHT_SUITE_NODEID in new_failures:
            playwright_failures = _extract_playwright_failures(post.raw_tail)

        def _expand_suite(nodes: list[str]) -> list[str]:
            if not playwright_failures or PLAYWRIGHT_SUITE_NODEID not in nodes:
                return nodes
            kept = [n for n in nodes if n != PLAYWRIGHT_SUITE_NODEID]
            return sorted(kept + [pf["nodeid"] for pf in playwright_failures])

        regressions = _expand_suite(regressions)
        new_failures = _expand_suite(new_failures)
        # Distinguish "tests ran clean" from "tests never ran". If post exited
        # non-zero but emitted no parseable results, the gate is inconclusive
        # (e.g. backend container down, missing fixture, import error) — that
        # is NOT 'green'.
        post_executed = bool(post.passed or post.failed)
        if regressions:
            kind, reason = "regressed", f"{len(regressions)} regression(s); post exit={post.raw_exit}"
        elif post.raw_exit != 0:
            # A21 (I-5 truthful aggregation): runner self-reported failure.
            # Even when no test regressed vs pre, a non-zero exit means the
            # suite did not complete cleanly — build error, infrastructure
            # failure, fixture crash, or a brand-new failure with no pre
            # counterpart. Never call this 'green'. If only new failures
            # appeared (none shared with pre), surface them as 'regressed';
            # otherwise it's 'inconclusive'.
            if new_failures:
                kind, reason = "regressed", f"{len(new_failures)} new failure(s); post exit={post.raw_exit}"
            else:
                kind, reason = "inconclusive", f"post suite did not exit clean (exit={post.raw_exit}, {len(post.passed)} passed, {len(post.failed)} failed); inspect post_tail"
        elif not post_executed:
            # Item #1 fix / A55 parity (2026-06-07): we reach here only when the
            # suite exited CLEAN (raw_exit == 0, checked above) yet emitted no
            # parseable per-test lines — e.g. a `-q` (quiet) test_cmd, or output
            # the parser can't anchor. pytest exit 0 == every collected test
            # passed (a collection error is exit 2; "no tests collected" is exit
            # 5 — neither is 0), so trust the exit code rather than blocking a
            # CORRECT change as `inconclusive`. Name-level differential gating is
            # unavailable in this case, but a clean exit is authoritative for
            # "nothing failed" (mirrors run_bl_tests, which is already
            # exit-code-authoritative).
            kind, reason = "green", ("post suite exited clean (exit=0) but emitted no "
                                     "parseable per-test lines; trusting exit code "
                                     "(A55 exit-code fallback)")
        else:
            kind, reason = "green", f"post suite green ({len(post.passed)} passed)"
        # A39: name a few real Playwright failures in the one-line reason so
        # the engineer retry prompt carries actionable test locations instead
        # of the opaque suite marker.
        if playwright_failures:
            names = ", ".join(pf["location"] for pf in playwright_failures[:4])
            more = "…" if len(playwright_failures) > 4 else ""
            reason = f"{reason} [playwright: {names}{more}]"
        # A49: annotate (never flip) when the failing tail shows transient
        # network/IO markers — gate non-determinism may have produced this red.
        transient_markers: list[str] = []
        if kind in ("regressed", "inconclusive"):
            transient_markers = detect_transient_markers(post.raw_tail)
            if transient_markers:
                reason = (f"{reason} [transient markers seen: "
                          f"{', '.join(transient_markers[:3])} — gate "
                          "non-determinism possible (A49); a standalone re-run may differ]")
        ok = (kind == "green")
        return {
            "ok": ok,
            "kind": kind,
            "pre": pre.to_dict(),
            "post": post.to_dict(),
            "regressions": regressions[:50],
            "new_failures": new_failures[:50],
            "failing_tests": playwright_failures[:50],
            "transient_markers": transient_markers,
            "command": test_cmd,
            "reason": reason,
            "post_tail": post.raw_tail[-15000:],
        }
    finally:
        for wt in (wt_pre, wt_post):
            await _git(["worktree", "remove", "--force", str(wt)], cwd=repo_root)
        # A48 fix #2 (2026-06-01): reap anonymous postgres-data volumes
        # left detached by the gate's compose down. Both pre and post
        # are scoped by their compose project label so Milvus, retrieval
        # cache, and other operator-owned volumes are never touched.
        # Best-effort: failures are returned in the ReapResult but never
        # raised; the gate result already returned above remains the
        # authoritative outcome.
        for proj in (pre_proj, post_proj):
            try:
                await volume_reaper_svc.reap(proj)
            except Exception:
                # Belt-and-suspenders: the reaper already swallows its
                # own errors into ReapResult.reason; this guard catches
                # any future regression that exposes them.
                pass
