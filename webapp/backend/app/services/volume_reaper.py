"""A48 fix #2: per-BL anonymous docker volume reaper.

After each gate (and the acceptance compose stack), the test_cmd's own
`docker compose down` removes the containers and the *named* volumes
declared in the compose file. But anonymous volumes — typically the
postgres data volume that the postgres image declares with
`VOLUME /var/lib/postgresql/data` — become detached and persist on the
host indefinitely, labelled with `com.docker.compose.project=<project>`.

On Client_Portal (`run-20260531T211839Z-1f47e6`), 44 such anonymous
volumes had accumulated across prior sprints (8.24 GB reclaimable),
combining with fresh per-BL allocations to push the host past DiskFull
mid-sprint at BL-0003 QA gate. Manual `docker volume prune` recovered
the space; this reaper automates that targeted, project-scoped cleanup
at the end of each BL (and acceptance) so anonymous volumes never
outlive the run that created them.

Scope discipline:
- Filter is ``label=com.docker.compose.project=<project>``, which is
  the standard label compose attaches to volumes it provisions.
- Only UNUSED volumes are pruned (`docker volume prune` skips volumes
  attached to live containers). Even if a stack didn't tear down
  cleanly, the reaper leaves anything still in use alone.
- The filter avoids Milvus, retrieval cache volumes, or any other
  operator-owned volume that doesn't carry this run's project label.

Best-effort: a docker daemon hiccup or a malformed project name
returns silently with the bytes_reclaimed counter at 0. The reaper
never raises; the orchestrator never aborts a sprint over cleanup
hygiene.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

# Docker compose project names are constrained to lowercase
# alphanumeric + `-` + `_`. We re-validate here as a defense-in-depth
# guard against passing a junk filter to `docker volume prune` that
# could otherwise produce unpredictable matching behavior.
_PROJECT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

# Cap the reaper at ~15 s — a stuck `docker volume prune` should not
# extend bl.done wall time. The orchestrator emits the result either
# way (success or timeout).
DEFAULT_TIMEOUT_S = 15.0


@dataclass
class ReapResult:
    ok: bool
    project: str
    volumes_removed: int
    bytes_reclaimed: int
    reason: str  # human-readable; empty on success

    def to_event(self) -> dict:
        return {
            "ok": self.ok,
            "project": self.project,
            "volumes_removed": self.volumes_removed,
            "bytes_reclaimed": self.bytes_reclaimed,
            "reason": self.reason,
        }


# `docker volume prune` (with --filter label=...=...) emits a final
# "Total reclaimed space: 1.234GB" line plus a count of removed names
# above it. Parse defensively — different docker CLIs use slightly
# different separators.
_RECLAIMED_RE = re.compile(
    r"Total reclaimed space:\s*([0-9.]+)\s*([kKmMgGtT]?B)",
)
_SIZE_SUFFIXES = {
    "B": 1, "KB": 1024, "MB": 1024 ** 2,
    "GB": 1024 ** 3, "TB": 1024 ** 4,
}


def _parse_reclaimed_bytes(stdout: str) -> int:
    m = _RECLAIMED_RE.search(stdout)
    if not m:
        return 0
    try:
        n = float(m.group(1))
    except (TypeError, ValueError):
        return 0
    suffix = m.group(2).upper()
    return int(n * _SIZE_SUFFIXES.get(suffix, 1))


def _count_removed_volumes(stdout: str) -> int:
    """Count the names listed under "Deleted Volumes:" in docker's output.

    Modern docker prints one volume name per line; we count non-empty
    lines that appear between "Deleted Volumes:" and the "Total
    reclaimed" footer. Lenient: if the layout differs, we still report
    bytes_reclaimed accurately.
    """
    if "Deleted Volumes:" not in stdout:
        return 0
    body = stdout.split("Deleted Volumes:", 1)[1]
    body = body.split("Total reclaimed", 1)[0]
    return sum(1 for line in body.splitlines() if line.strip())


async def reap(
    compose_project: str | None,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> ReapResult:
    """Prune unused volumes whose `com.docker.compose.project` label
    equals ``compose_project``.

    Parameters
    ----------
    compose_project
        The compose project name whose anonymous volumes should be
        reaped. When ``None`` or empty, the reaper is a no-op
        (caller didn't set COMPOSE_PROJECT_NAME → there's nothing
        to scope a prune to safely).
    timeout_s
        Hard wall on the subprocess. Default 15s; the prune is
        I/O-bound on a typically small set of volumes.

    Returns
    -------
    A ``ReapResult``; on any failure (no docker, bad project name,
    timeout, non-zero exit) ``ok=False`` with a reason. The function
    never raises.
    """
    if not compose_project:
        return ReapResult(
            ok=True, project="",
            volumes_removed=0, bytes_reclaimed=0,
            reason="no compose_project supplied; reaper skipped",
        )
    if not _PROJECT_NAME_RE.match(compose_project):
        return ReapResult(
            ok=False, project=compose_project,
            volumes_removed=0, bytes_reclaimed=0,
            reason=(
                f"invalid project name {compose_project!r}; "
                "must match docker compose lowercase alphanumeric + -_"
            ),
        )

    label = f"com.docker.compose.project={compose_project}"
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "volume", "prune", "-f", "--filter", f"label={label}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_s,
        )
    except FileNotFoundError:
        return ReapResult(
            ok=False, project=compose_project,
            volumes_removed=0, bytes_reclaimed=0,
            reason="docker CLI not on PATH",
        )
    except asyncio.TimeoutError:
        return ReapResult(
            ok=False, project=compose_project,
            volumes_removed=0, bytes_reclaimed=0,
            reason=f"docker volume prune timed out after {timeout_s:.0f}s",
        )
    except OSError as exc:
        return ReapResult(
            ok=False, project=compose_project,
            volumes_removed=0, bytes_reclaimed=0,
            reason=f"<OSError: {exc}>",
        )

    if proc.returncode != 0:
        tail = err.decode("utf-8", "replace")[-300:].strip()
        return ReapResult(
            ok=False, project=compose_project,
            volumes_removed=0, bytes_reclaimed=0,
            reason=f"docker exit {proc.returncode}: {tail}",
        )

    stdout = out.decode("utf-8", "replace")
    return ReapResult(
        ok=True, project=compose_project,
        volumes_removed=_count_removed_volumes(stdout),
        bytes_reclaimed=_parse_reclaimed_bytes(stdout),
        reason="",
    )


async def reap_many(
    compose_projects: list[str | None],
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> list[ReapResult]:
    """Reap multiple compose projects sequentially.

    Sequential (not concurrent) on purpose: docker daemon contention
    on the prune endpoint is non-trivial, and the savings from
    parallelism are negligible (~50 ms × N projects, capped at
    timeout_s × N).
    """
    return [await reap(p, timeout_s=timeout_s) for p in compose_projects]
