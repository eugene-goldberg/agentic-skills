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


PYTEST_RESULT_RE = re.compile(r"^(?P<file>tests?/[\w./-]+)::(?P<name>[\w.\[\]-]+)\s+(?P<verdict>PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)", re.MULTILINE)

# ─── Batch 2-1 / A39a: build/lint sentinel detection ────────────────────────
# The target's regression_gate.sh wrapper emits pseudo-test lines for its
# non-test steps (`tests/gate::build FAILED`,
# `tests/frontend::lint_typecheck_build FAILED`). When one of these fails,
# downstream tests never ran — so `pre.passed - post.passed` counts every
# baseline test as a "regression" (the documents_2 BL-0008 "161 regressions"
# incident). Detect the sentinel and classify honestly instead.
_BUILD_SENTINEL_FILES = ("tests/gate", "tests/frontend", "test/gate", "test/frontend")
_BUILD_SENTINEL_NAME_RE = re.compile(r"(?:build|lint|typecheck|compile)", re.IGNORECASE)


def _is_build_sentinel(nodeid: str) -> bool:
    file_part, _, name_part = nodeid.partition("::")
    if not name_part:
        return False
    return file_part in _BUILD_SENTINEL_FILES and bool(_BUILD_SENTINEL_NAME_RE.search(name_part))


def _extract_build_error(post_tail: str, sentinels: list[str]) -> str:
    """Slice the compiler/linter output that *precedes* the sentinel FAILED
    line — that block, not the container noise after it, is what the
    engineer needs. Falls back to the tail's last 2500 chars."""
    if not post_tail:
        return ""
    cut = len(post_tail)
    for s in sentinels:
        i = post_tail.find(s)
        if i != -1:
            cut = min(cut, i)
    return post_tail[:cut][-2500:].strip() or post_tail[-2500:].strip()


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


def classify_gate_outcome(pre: TestSet, post: TestSet, *, test_cmd: list) -> dict:
    """Batch 2-1 (A39a/b): the gate's pure decision tree — extracted from
    ``run_gate`` so classification is unit-testable against real-incident
    fixture tails.

    Result kinds (worst-first): ``infra_fail`` | ``build_fail`` |
    ``regressed`` | ``inconclusive`` | ``green``. Every result carries
    ``gate_failure_class ∈ {"infra","build","lint","test",None}`` so the
    fix-prompt builder and retry predicates can switch on failure class
    instead of guessing from free text.

    Invariant (A39b): ``kind == "regressed"`` ⟹ ``regressions`` ∪
    ``new_failures`` is non-empty. An empty union downgrades to
    ``inconclusive`` — a positive count with no identities is a parser
    bug and must never reach the engineer's fix prompt.
    """
    base = {
        "pre": pre.to_dict(),
        "post": post.to_dict(),
        "command": test_cmd,
        "post_tail": post.raw_tail[-15000:],
    }

    # A25b: infra markers (ENOSPC, OOM, docker daemon, pg unreachable...)
    # mean the runtime crashed under the suite — not engineer-fixable.
    infra = detect_infra_failure(post.raw_tail)
    if infra:
        # A48 fix #3: prefer the canonical disk-full line over the cascade.
        disk_full = extract_disk_full_reason(post.raw_tail)
        result = {
            **base,
            "ok": False, "kind": "infra_fail",
            "gate_failure_class": "infra",
            "regressions": [], "new_failures": [],
        }
        if disk_full:
            result["reason"] = f"infra failure (host_disk_full): {disk_full[:200]}"
            result["infra_fail_reason"] = "host_disk_full"
        else:
            result["reason"] = f"infra failure: {infra[:200]}"
            result["infra_fail_reason"] = "other"
        return result

    # A39a: a failed build/lint sentinel means downstream tests never ran.
    # pre.passed - post.passed would count the whole baseline as regressed
    # ("161 regressions"); classify as build_fail with the compiler/linter
    # block as the reason instead.
    sentinels = sorted(n for n in post.failed if _is_build_sentinel(n))
    if sentinels:
        cls = "lint" if all("lint" in n.lower() for n in sentinels) else "build"
        error_block = _extract_build_error(post.raw_tail, sentinels)
        return {
            **base,
            "ok": False, "kind": "build_fail",
            "gate_failure_class": cls,
            "regressions": [], "new_failures": [],
            "build_sentinels": sentinels,
            "build_error": error_block,
            "reason": (
                f"{cls} step failed ({', '.join(sentinels)}); "
                f"downstream tests not run — this is NOT a test regression"
            ),
        }

    # A test that was passing pre-merge but is now failing (or missing) is
    # a regression — but ONLY if the post suite actually executed
    # something. A differential comparison with an empty denominator is
    # the no-sentinel variant of the "161 regressions" lie: when the run
    # produced zero parseable results, "everything in pre regressed" is
    # noise, not signal (A39a residual, Batch 2-1).
    regressions = sorted(pre.passed - post.passed)
    new_failures = sorted(post.failed - pre.failed)
    post_executed = bool(post.passed or post.failed)
    if not post_executed:
        kind, cls = "inconclusive", "test"
        reason = (
            f"post suite produced no parseable results (exit={post.raw_exit}); "
            "differential comparison impossible — inspect post_tail; verify test_cmd"
        )
    elif regressions:
        kind, cls = "regressed", "test"
        reason = f"{len(regressions)} regression(s); post exit={post.raw_exit}"
    elif post.raw_exit != 0:
        # A21 (I-5): runner self-reported failure — never 'green'.
        if new_failures:
            kind, cls = "regressed", "test"
            reason = f"{len(new_failures)} new failure(s); post exit={post.raw_exit}"
        else:
            kind, cls = "inconclusive", "test"
            reason = (f"post suite did not exit clean (exit={post.raw_exit}, "
                      f"{len(post.passed)} passed, {len(post.failed)} failed); inspect post_tail")
    else:
        kind, cls = "green", None
        reason = f"post suite green ({len(post.passed)} passed)"

    # A39b invariant: regressed requires identities. Unreachable by
    # construction above, but guards any future refactor of the tree.
    if kind == "regressed" and not (regressions or new_failures):
        kind, cls = "inconclusive", "test"
        reason = ("regression count positive but no test identities parsed "
                  "(A39b parser invariant); inspect post_tail")

    return {
        **base,
        "ok": kind == "green",
        "kind": kind,
        "gate_failure_class": cls,
        "regressions": regressions[:50],
        "new_failures": new_failures[:50],
        "reason": reason,
    }


async def _git(args: list[str], cwd: Path) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "git", *args, cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return proc.returncode or 0, (out + err).decode(errors="replace")


# ─── Batch 5-2 (A29): PRE-baseline result cache ─────────────────────────────
#
# The PRE side of the gate re-runs the ENTIRE suite against target_ref for
# every gate invocation — even though target_ref only moves when a merge
# lands. At the measured 40–80 min per suite run that is ~50% of all gate
# wall-time after the first BL. Cache the PRE TestSet keyed on the exact
# (target_ref SHA, test_cmd) pair: any merge moves the SHA, so
# invalidation is automatic and a stale-green is structurally impossible
# from the key alone. TTL is a 24h backstop against environmental drift
# (docker image updates etc.) that the SHA can't see.

_PRE_CACHE_TTL_S = 24 * 3600
_PRE_CACHE_KEEP = 10  # opportunistic pruning: newest N files kept


def _pre_cache_dir(repo_root: Path) -> Path:
    return repo_root.parent / ".gate-cache"


def _pre_cache_path(repo_root: Path, target_sha: str, test_cmd: list) -> Path:
    import hashlib
    cmd_hash = hashlib.sha256(json.dumps(test_cmd).encode()).hexdigest()[:8]
    return _pre_cache_dir(repo_root) / f"pre-{target_sha[:12]}-{cmd_hash}.json"


def _pre_cache_load(repo_root: Path, target_sha: str, test_cmd: list) -> TestSet | None:
    import time
    p = _pre_cache_path(repo_root, target_sha, test_cmd)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError):
        return None
    if data.get("target_sha") != target_sha or data.get("test_cmd") != test_cmd:
        return None  # hash collision paranoia — full-key check
    if time.time() - float(data.get("created_at", 0)) > _PRE_CACHE_TTL_S:
        return None
    return TestSet(
        passed=set(data.get("passed") or []),
        failed=set(data.get("failed") or []),
        raw_exit=int(data.get("raw_exit", 0)),
        raw_tail=str(data.get("tail") or ""),
    )


def _pre_cache_store(repo_root: Path, target_sha: str, test_cmd: list,
                     pre: TestSet) -> None:
    """Best-effort. Only parseable, executed PRE runs are cacheable — an
    empty/broken baseline must be recomputed, never replayed."""
    import time
    if not (pre.passed or pre.failed):
        return
    try:
        d = _pre_cache_dir(repo_root)
        d.mkdir(parents=True, exist_ok=True)
        p = _pre_cache_path(repo_root, target_sha, test_cmd)
        p.write_text(json.dumps({
            "target_sha": target_sha,
            "test_cmd": test_cmd,
            "created_at": time.time(),
            "passed": sorted(pre.passed),
            "failed": sorted(pre.failed),
            "raw_exit": pre.raw_exit,
            "tail": pre.raw_tail[-2000:],
        }))
        # Opportunistic prune: keep the newest N cache files.
        files = sorted(d.glob("pre-*.json"), key=lambda f: f.stat().st_mtime,
                       reverse=True)
        for old in files[_PRE_CACHE_KEEP:]:
            try:
                old.unlink()
            except OSError:
                pass
    except (OSError, ValueError):
        pass


async def run_gate(repo_root: Path, agent_branch: str, target_ref: str,
                   *, run_id: str | None = None) -> dict:
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
    code, target_sha_out = await _git(["rev-parse", "--verify", target_ref], cwd=repo_root)
    if code != 0:
        return {"ok": False, "kind": "error", "reason": f"target ref {target_ref} not found", "command": test_cmd}
    target_sha = target_sha_out.strip()
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
        # A29 (Batch 5-2): PRE-baseline cache. On a hit we skip the entire
        # PRE worktree + docker stack + suite run (~50% of gate wall-time
        # after the first BL of a sprint). Keyed on the exact target SHA —
        # any merge moves the key, so a stale baseline is unreachable.
        pre_cache_hit = False
        pre = _pre_cache_load(repo_root, target_sha, test_cmd)
        if pre is not None:
            pre_cache_hit = True
        else:
            code, msg = await _git(["worktree", "add", "--detach", str(wt_pre), target_ref], cwd=repo_root)
            if code != 0:
                return {"ok": False, "kind": "error", "reason": f"pre worktree add failed: {msg.strip()}", "command": test_cmd}
            pre = await _run_tests(wt_pre, test_cmd, compose_project=pre_proj)
            # Cache only when the baseline itself is healthy: parseable
            # results AND no infra marker in its tail — a DiskFull/OOM
            # baseline must never be replayed as truth.
            if not detect_infra_failure(pre.raw_tail):
                _pre_cache_store(repo_root, target_sha, test_cmd, pre)

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

        # Batch 2-1 (A39a/b): the decision tree lives in
        # classify_gate_outcome — pure and unit-tested against the real
        # incident tails (161-fake-regressions, empty-regressions-with-
        # count, biome lint, DiskFull cascade).
        result = classify_gate_outcome(pre, post, test_cmd=test_cmd)
        result["pre_cache_hit"] = pre_cache_hit  # A29: every hit is auditable
        return result
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
