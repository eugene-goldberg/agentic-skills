"""Closure-postcondition checks (M2-2 / I-3).

At run termination — any exit path — the orchestrator should be able to
ASSERT that the world is in the state cleanup intended, not HOPE for it.
This module provides the scan primitives. The orchestrator (M2-3) calls
``scan_all`` from its outer ``finally`` and emits a structured
``orchestrator.closure_violation`` event per survivor found.

What this module does NOT do:

- It does NOT reap the survivors. Reaping is operator-gated (a separate
  endpoint we may add later); the architectural posture is
  "report, don't auto-clean" so that an invariant violation is never
  silently swallowed.
- It does NOT scan resources the framework cannot tag with the run_id.
  Today that means: subprocess pgroups (need Move 3's ManagedSubprocess
  primitive to tag) and agent branches (need branch-name run_id
  embedding). Both are stubbed below and clearly marked deferred.

Closes ledger items A10 (orphan docker container accumulation) once M2-3
wires this in. A9 (gate subprocess pgroup leak) is sibling-class but
needs Move 3 to close.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from app.services.regression_gate import _compose_project_prefix


@dataclass
class Violation:
    """One closure-postcondition failure.

    ``kind`` is the resource class (e.g. ``docker_container``,
    ``gate_worktree``); ``resource`` is the identifier the operator
    would use to reap it; ``detail`` is freeform context for the
    SSE event consumer (timestamp, command, etc.).
    """
    kind: str
    resource: str
    detail: dict = field(default_factory=dict)


# ─── docker container scan (closes A10 once M2-3 wires this in) ────────────


async def scan_orphan_docker_containers(
    run_id: str,
    timeout: float = 10.0,
) -> list[Violation]:
    """Return Violations for any docker container whose COMPOSE_PROJECT_NAME
    prefix matches the M2-1 pattern for this run_id.

    Requires: M2-1 (gate sets COMPOSE_PROJECT_NAME=agentic-skills-<run_id>-...)
    is already landed and the gate has actually run at least once during the
    run. Containers from gate-less or pre-M2-1 runs carry no label and are
    correctly invisible to this scan.

    Idempotent + safe to call when docker is absent (best-effort; returns
    empty list and a single ``docker_unreachable`` violation).
    """
    prefix = _compose_project_prefix(run_id)
    if not prefix:
        return []
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "ps", "-a",
            "--filter", f"name={prefix}-",
            "--format", "{{.Names}}\t{{.Status}}\t{{.ID}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return [Violation(
            kind="closure_check_error",
            resource="docker_cli_missing",
            detail={"check": "scan_orphan_docker_containers"},
        )]
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return [Violation(
            kind="closure_check_error",
            resource="docker_ps_timeout",
            detail={"timeout_seconds": timeout, "check": "scan_orphan_docker_containers"},
        )]
    if proc.returncode != 0:
        return [Violation(
            kind="closure_check_error",
            resource="docker_ps_failed",
            detail={"exit_code": proc.returncode, "stderr": err.decode(errors="replace")[:500]},
        )]
    violations: list[Violation] = []
    for line in out.decode(errors="replace").splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        name, status, cid = parts
        violations.append(Violation(
            kind="docker_container",
            resource=name,
            detail={"id": cid, "status": status, "project_prefix": prefix},
        ))
    return violations


# ─── gate worktree directory scan ──────────────────────────────────────────


def scan_stale_gate_worktrees(repo_root: Path) -> list[Violation]:
    """Return Violations for any directory left in ``<repo>/../.gate-worktrees/``.

    The gate's own ``finally`` removes the disposable worktrees it creates.
    Anything left over here is either an interrupted gate that did not
    reach its cleanup, or a stale worktree from a previous run. Either way
    it is a closure-postcondition failure: the gate's exit code does not
    guarantee the directory is gone.

    Per-run filtering is not yet possible at this scan level because gate
    worktrees use ``<wt_id>`` (a fresh uuid per gate) for the directory
    name, not the run_id. A future structural fix would embed run_id in
    the path; until then we report ALL stale directories. M2-3 SHOULD only
    fire this scan at sprint-end (not for in-flight gates).
    """
    gate_dir = repo_root.parent / ".gate-worktrees"
    if not gate_dir.exists():
        return []
    violations: list[Violation] = []
    for child in gate_dir.iterdir():
        if not child.is_dir():
            continue
        violations.append(Violation(
            kind="gate_worktree",
            resource=str(child),
            detail={"basename": child.name},
        ))
    return violations


# ─── deferred scans (stubs, document the gaps) ─────────────────────────────


def scan_orphan_pgroup_children(run_id: str) -> list[Violation]:
    """DEFERRED. Closes A9 only after Move 3's ManagedSubprocess primitive
    lands and tags pgroups with the run_id. Without that tagging, this scan
    has no reliable way to identify which surviving children belong to which
    run. Returning an empty list is the correct behavior today; closure_check
    will not report false positives.
    """
    return []


def scan_orphan_agent_branches(repo_root: Path, run_id: str) -> list[Violation]:
    """DEFERRED. Agent branch names today are ``agent/<task_id>`` where
    task_id is a fresh uuid per worktree, not embedded with run_id. To
    close this scan we would either:
      (a) rename the branch convention to ``agent/<run_id>/<task_id>``, or
      (b) maintain an explicit run→branches index in disk state.
    Either is a structural change tracked separately; for now this stub
    returns no violations rather than producing false positives.
    """
    return []


# ─── ABL-0014 D9: acceptance-stack scan ───────────────────────────────────


async def scan_orphan_acceptance_containers(
    run_id: str,
    timeout: float = 10.0,
) -> list[Violation]:
    """Return Violations for any docker container whose
    ``COMPOSE_PROJECT_NAME`` matches the acceptance-agent convention
    ``acceptance-<run_id>`` (§E.1 Q7 + Q9). The acceptance agent's
    SKILLS.md prompt sets this; any survivor is an I-3 leak.

    Mirrors ``scan_orphan_docker_containers`` but uses the
    ``acceptance-<run_id>`` prefix. Reported under ``kind="acceptance_docker"``
    so closure_check.summary's by_kind histogram distinguishes the two
    classes of leak.
    """
    prefix = f"acceptance-{run_id}"
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "ps", "-a",
            "--filter", f"name={prefix}",
            "--format", "{{.Names}}\t{{.Status}}\t{{.ID}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return [Violation(
            kind="closure_check_error",
            resource="docker_cli_missing",
            detail={"check": "scan_orphan_acceptance_containers"},
        )]
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return [Violation(
            kind="closure_check_error",
            resource="docker_ps_timeout",
            detail={"timeout_seconds": timeout, "check": "scan_orphan_acceptance_containers"},
        )]
    if proc.returncode != 0:
        return [Violation(
            kind="closure_check_error",
            resource="docker_ps_failed",
            detail={"exit_code": proc.returncode, "stderr": err.decode(errors="replace")[:500],
                    "check": "scan_orphan_acceptance_containers"},
        )]
    violations: list[Violation] = []
    for line in out.decode(errors="replace").splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        name, status, cid = parts
        violations.append(Violation(
            kind="acceptance_docker",
            resource=name,
            detail={"id": cid, "status": status, "project_prefix": prefix},
        ))
    return violations


def scan_stale_acceptance_worktrees(repo_root: Path, run_id: str) -> list[Violation]:
    """Acceptance-agent worktrees are created via ``create_worktree`` with
    ``task_id=f"accept-{run_id}"``, landing at
    ``<repo>/../.agent-worktrees/accept-<run_id>``. ``_acceptance_flow``'s
    finally-block reaps these; anything left over is an I-1 leak.
    """
    wt_dir = repo_root.parent / ".agent-worktrees" / f"accept-{run_id}"
    if not wt_dir.exists():
        return []
    return [Violation(
        kind="acceptance_worktree",
        resource=str(wt_dir),
        detail={"basename": wt_dir.name},
    )]


def scan_stale_followup_worktrees(repo_root: Path, run_id: str) -> list[Violation]:
    """ABL-0015: auto-dispatch follow-up engineer worktrees are created via
    ``_engineer_flow`` with ``task_id=f"followup-{run_id}-{idx}"``, landing
    at ``<repo>/../.agent-worktrees/followup-<run_id>-<idx>``.
    ``_engineer_flow``'s finally-block reaps these (same path as every BL);
    anything left over is an I-1 leak. Globs because a sprint may dispatch
    more than one once the cost cap is lifted.
    """
    wt_root = repo_root.parent / ".agent-worktrees"
    if not wt_root.exists():
        return []
    return [
        Violation(
            kind="followup_worktree",
            resource=str(d),
            detail={"basename": d.name},
        )
        for d in sorted(wt_root.glob(f"followup-{run_id}-*"))
        if d.is_dir()
    ]


# ─── orchestrator entry point ──────────────────────────────────────────────


async def scan_all(repo_root: Path, run_id: str) -> list[Violation]:
    """Run every closure scan, in parallel where possible. Each scan
    surfaces its own errors as ``kind=closure_check_error`` violations
    rather than raising — so a broken scan never masks real violations
    from the other checks.
    """
    docker_task = asyncio.create_task(scan_orphan_docker_containers(run_id))
    accept_task = asyncio.create_task(scan_orphan_acceptance_containers(run_id))
    docker_v, accept_v = await asyncio.gather(
        docker_task, accept_task, return_exceptions=False,
    )
    # Sync scans are cheap; run inline.
    wt_v = scan_stale_gate_worktrees(repo_root)
    accept_wt_v = scan_stale_acceptance_worktrees(repo_root, run_id)
    followup_wt_v = scan_stale_followup_worktrees(repo_root, run_id)
    pgrp_v = scan_orphan_pgroup_children(run_id)
    br_v = scan_orphan_agent_branches(repo_root, run_id)
    return [*docker_v, *accept_v, *wt_v, *accept_wt_v, *followup_wt_v, *pgrp_v, *br_v]
